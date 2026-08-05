"""Deterministic implementation of the EC_POLICY_V1 priority table (README §4).

This is the single source of truth for primary_issue / responsible party /
refund amount / resolution action. LLM agents may reason about and narrate
these facts, but the numbers written to output/ always come from here.
"""
from dataclasses import dataclass, field
from typing import Optional

from src.data_store import OrderFacts

RECONCILE_TOLERANCE_BRL = 0.10

RESOLUTION_ACTION = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}

ROOT_CAUSE_CODE = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}

CASE_STATUS = {
    "canceled_order_paid": "action_required",
    "unavailable_order_paid": "action_required",
    "late_delivery_seller": "action_required",
    "late_delivery_logistics": "action_required",
    "valid_split_payment": "no_action",
    "unsupported_late_claim": "no_action",
}


@dataclass
class ResponsibleParty:
    party_type: str
    party_id: str


@dataclass
class PolicyDecision:
    primary_issue: str
    case_status: str
    root_cause_code: str
    responsible_parties: list = field(default_factory=list)  # list[ResponsibleParty]
    item_total_brl: float = 0.0
    freight_total_brl: float = 0.0
    payment_total_brl: float = 0.0
    recommended_refund_brl: float = 0.0
    resolution_actions: list = field(default_factory=list)
    violating_seller_ids: list = field(default_factory=list)
    confidence: float = 0.9
    matched_rule: bool = True
    rationale: str = ""


def _round2(value: float) -> float:
    return round(value + 1e-9, 2)


def apply_policy(facts: OrderFacts) -> PolicyDecision:
    order = facts.order
    item_total = _round2(sum(i.price for i in facts.items))
    freight_total = _round2(sum(i.freight_value for i in facts.items))
    payment_total = _round2(sum(p.payment_value for p in facts.payments))
    merch_total = _round2(item_total + freight_total)

    base = dict(
        item_total_brl=item_total,
        freight_total_brl=freight_total,
        payment_total_brl=payment_total,
    )

    if order is None:
        return _make(
            "unsupported_late_claim",
            base,
            responsible_parties=[],
            refund=0.0,
            confidence=0.3,
            matched_rule=False,
            rationale="claimed_order_id không tồn tại trong orders.csv.",
        )

    # Rule 1: canceled_order_paid
    if order.order_status == "canceled" and payment_total > 0:
        return _make(
            "canceled_order_paid",
            base,
            responsible_parties=[ResponsibleParty("platform", "OLIST_PLATFORM")],
            refund=payment_total,
            confidence=0.97,
            rationale="order_status=canceled và tổng payment > 0.",
        )

    # Rule 2: unavailable_order_paid
    if order.order_status == "unavailable" and payment_total > 0:
        return _make(
            "unavailable_order_paid",
            base,
            responsible_parties=[ResponsibleParty("platform", "OLIST_PLATFORM")],
            refund=payment_total,
            confidence=0.97,
            rationale="order_status=unavailable và tổng payment > 0.",
        )

    delivered_late = (
        order.order_delivered_customer_date is not None
        and order.order_estimated_delivery_date is not None
        and order.order_delivered_customer_date > order.order_estimated_delivery_date
    )

    if delivered_late and facts.items:
        carrier_date = order.order_delivered_carrier_date
        violating_sellers = sorted(
            {
                item.seller_id
                for item in facts.items
                if carrier_date is not None
                and item.shipping_limit_date is not None
                and carrier_date > item.shipping_limit_date
            }
        )

        if violating_sellers:
            # Rule 3: late_delivery_seller
            return _make(
                "late_delivery_seller",
                base,
                responsible_parties=[
                    ResponsibleParty("seller", sid) for sid in violating_sellers[:3]
                ],
                refund=freight_total,
                confidence=0.93,
                violating_seller_ids=violating_sellers,
                rationale=(
                    "Giao sau estimated date; carrier nhận hàng sau shipping_limit_date "
                    f"của seller {violating_sellers}."
                ),
            )

        # Rule 4: late_delivery_logistics
        return _make(
            "late_delivery_logistics",
            base,
            responsible_parties=[ResponsibleParty("logistics_provider", "LOGISTICS_PROVIDER")],
            refund=freight_total,
            confidence=0.9,
            rationale=(
                "Giao sau estimated date nhưng carrier đã nhận hàng không muộn hơn "
                "shipping_limit_date của mọi seller."
            ),
        )

    payment_reconciled = abs(payment_total - merch_total) <= RECONCILE_TOLERANCE_BRL

    # Rule 5: valid_split_payment
    if len(facts.payments) >= 2 and payment_reconciled:
        return _make(
            "valid_split_payment",
            base,
            responsible_parties=[],
            refund=0.0,
            confidence=0.92,
            rationale=(
                f">=2 payment rows ({len(facts.payments)}); payment_total {payment_total} "
                f"khớp item+freight {merch_total} trong sai số {RECONCILE_TOLERANCE_BRL}."
            ),
        )

    # Rule 6: unsupported_late_claim
    if not delivered_late and payment_reconciled:
        return _make(
            "unsupported_late_claim",
            base,
            responsible_parties=[],
            refund=0.0,
            confidence=0.88,
            rationale="Đơn giao không muộn hơn estimated date và payment khớp tổng item+freight.",
        )

    # Fallback: no rule matched cleanly (should not occur on the official 50 cases).
    return _make(
        "unsupported_late_claim",
        base,
        responsible_parties=[],
        refund=0.0,
        confidence=0.4,
        matched_rule=False,
        rationale="Không khớp rõ ràng bất kỳ rule nào trong bảng ưu tiên; fallback bảo thủ.",
    )


def _make(
    primary_issue: str,
    base: dict,
    *,
    responsible_parties,
    refund: float,
    confidence: float,
    matched_rule: bool = True,
    violating_seller_ids=None,
    rationale: str = "",
) -> PolicyDecision:
    return PolicyDecision(
        primary_issue=primary_issue,
        case_status=CASE_STATUS[primary_issue],
        root_cause_code=ROOT_CAUSE_CODE[primary_issue],
        responsible_parties=responsible_parties,
        item_total_brl=base["item_total_brl"],
        freight_total_brl=base["freight_total_brl"],
        payment_total_brl=base["payment_total_brl"],
        recommended_refund_brl=_round2(refund),
        resolution_actions=[RESOLUTION_ACTION[primary_issue]],
        violating_seller_ids=violating_seller_ids or [],
        confidence=confidence,
        matched_rule=matched_rule,
        rationale=rationale,
    )
