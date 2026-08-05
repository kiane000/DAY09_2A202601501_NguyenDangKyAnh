import pandas as pd
import pytest

from src.data_store import ItemRecord, OrderFacts, OrderRecord, PaymentRecord, SellerRecord
from src.policy_engine import apply_policy

ORDER_ID = "order-1"
SELLER_A = "seller-a"
SELLER_B = "seller-b"


def _order(**overrides) -> OrderRecord:
    defaults = dict(
        order_id=ORDER_ID,
        customer_id="cust-1",
        order_status="delivered",
        order_purchase_timestamp=pd.Timestamp("2018-01-01 10:00:00"),
        order_approved_at=pd.Timestamp("2018-01-01 10:30:00"),
        order_delivered_carrier_date=pd.Timestamp("2018-01-03 09:00:00"),
        order_delivered_customer_date=pd.Timestamp("2018-01-10 12:00:00"),
        order_estimated_delivery_date=pd.Timestamp("2018-01-15 00:00:00"),
    )
    defaults.update(overrides)
    return OrderRecord(**defaults)


def _item(seller_id=SELLER_A, shipping_limit_date=None, price=100.0, freight=15.0, item_id=1):
    return ItemRecord(
        order_id=ORDER_ID,
        order_item_id=item_id,
        product_id="prod-1",
        seller_id=seller_id,
        shipping_limit_date=shipping_limit_date or pd.Timestamp("2018-01-05 00:00:00"),
        price=price,
        freight_value=freight,
    )


def _payment(seq=1, value=115.0):
    return PaymentRecord(
        order_id=ORDER_ID, payment_sequential=seq, payment_type="credit_card",
        payment_installments=1, payment_value=value,
    )


def _facts(order, items=None, payments=None):
    items = items or []
    payments = payments or []
    sellers = {i.seller_id: SellerRecord(i.seller_id, "00000", "city", "SP") for i in items}
    return OrderFacts(order=order, items=items, payments=payments, sellers=sellers)


def test_canceled_order_paid():
    facts = _facts(_order(order_status="canceled"), items=[_item()], payments=[_payment(value=115.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "canceled_order_paid"
    assert d.case_status == "action_required"
    assert d.root_cause_code == "ORDER_CANCELED_AFTER_PAYMENT"
    assert d.responsible_parties[0].party_type == "platform"
    assert d.responsible_parties[0].party_id == "OLIST_PLATFORM"
    assert d.recommended_refund_brl == 115.0
    assert d.resolution_actions == ["issue_full_refund"]


def test_unavailable_order_paid():
    facts = _facts(_order(order_status="unavailable"), items=[_item()], payments=[_payment(value=115.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "unavailable_order_paid"
    assert d.root_cause_code == "ORDER_UNAVAILABLE_AFTER_PAYMENT"
    assert d.recommended_refund_brl == 115.0


def test_late_delivery_seller():
    # carrier picked up AFTER the item's shipping_limit_date -> seller's fault.
    order = _order(order_delivered_customer_date=pd.Timestamp("2018-01-20 00:00:00"))
    item = _item(shipping_limit_date=pd.Timestamp("2018-01-02 00:00:00"))
    facts = _facts(order, items=[item], payments=[_payment(value=115.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "late_delivery_seller"
    assert d.root_cause_code == "SELLER_HANDOFF_AFTER_LIMIT"
    assert d.responsible_parties[0].party_type == "seller"
    assert d.responsible_parties[0].party_id == SELLER_A
    assert d.recommended_refund_brl == d.freight_total_brl == 15.0
    assert d.resolution_actions == ["refund_freight"]


def test_late_delivery_logistics():
    # carrier picked up BEFORE the item's shipping_limit_date -> logistics fault.
    order = _order(order_delivered_customer_date=pd.Timestamp("2018-01-20 00:00:00"))
    item = _item(shipping_limit_date=pd.Timestamp("2018-01-09 00:00:00"))
    facts = _facts(order, items=[item], payments=[_payment(value=115.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "late_delivery_logistics"
    assert d.root_cause_code == "CARRIER_DELIVERED_AFTER_ESTIMATE"
    assert d.responsible_parties[0].party_type == "logistics_provider"
    assert d.responsible_parties[0].party_id == "LOGISTICS_PROVIDER"
    assert d.recommended_refund_brl == 15.0


def test_valid_split_payment():
    order = _order(order_delivered_customer_date=pd.Timestamp("2018-01-14 00:00:00"))
    item = _item(shipping_limit_date=pd.Timestamp("2018-01-09 00:00:00"))
    facts = _facts(order, items=[item], payments=[_payment(1, 60.0), _payment(2, 55.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "valid_split_payment"
    assert d.case_status == "no_action"
    assert d.root_cause_code == "MULTIPLE_PAYMENTS_RECONCILED"
    assert d.responsible_parties == []
    assert d.recommended_refund_brl == 0.0
    assert d.resolution_actions == ["explain_valid_split_payment"]


def test_unsupported_late_claim():
    order = _order(order_delivered_customer_date=pd.Timestamp("2018-01-14 00:00:00"))
    item = _item(shipping_limit_date=pd.Timestamp("2018-01-09 00:00:00"))
    facts = _facts(order, items=[item], payments=[_payment(value=115.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "unsupported_late_claim"
    assert d.case_status == "no_action"
    assert d.root_cause_code == "DELIVERY_WITHIN_ESTIMATE"
    assert d.responsible_parties == []
    assert d.recommended_refund_brl == 0.0
    assert d.resolution_actions == ["reject_late_refund"]


def test_multi_seller_only_violating_seller_named():
    order = _order(order_delivered_customer_date=pd.Timestamp("2018-01-20 00:00:00"))
    item_a = _item(seller_id=SELLER_A, shipping_limit_date=pd.Timestamp("2018-01-02 00:00:00"), item_id=1)
    item_b = _item(seller_id=SELLER_B, shipping_limit_date=pd.Timestamp("2018-01-09 00:00:00"), item_id=2)
    facts = _facts(order, items=[item_a, item_b], payments=[_payment(value=230.0)])
    d = apply_policy(facts)
    assert d.primary_issue == "late_delivery_seller"
    assert d.violating_seller_ids == [SELLER_A]
