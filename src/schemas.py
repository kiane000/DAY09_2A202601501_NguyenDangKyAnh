"""Pydantic models mirroring the output schema in README §6, with the caps
and format rules from README §5/§6 enforced as validators."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PRIMARY_ISSUES = (
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
)

ROOT_CAUSE_CODES = (
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
)

RESOLUTION_ACTIONS = (
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
)

PARTY_TYPES = ("platform", "seller", "logistics_provider")

EVIDENCE_PATTERNS = [
    re.compile(r"^order:[^:]+$"),
    re.compile(r"^item:[^:]+:\d+$"),
    re.compile(r"^payment:[^:]+:\d+$"),
    re.compile(r"^seller:[^:]+$"),
    re.compile(r"^policy:[A-Z_]+$"),
]


def is_valid_evidence_id(evidence_id: str) -> bool:
    return any(p.match(evidence_id) for p in EVIDENCE_PATTERNS)


class Assessment(BaseModel):
    primary_issue: Literal[PRIMARY_ISSUES]
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0.0, le=1.0)


class AffectedEntities(BaseModel):
    order_ids: list[str] = Field(default_factory=list, max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=5)
    payment_ids: list[str] = Field(default_factory=list, max_length=5)


class RankedCause(BaseModel):
    cause_code: Literal[ROOT_CAUSE_CODES]
    rank: int = Field(ge=1)


class ResponsibleParty(BaseModel):
    party_type: Literal[PARTY_TYPES]
    party_id: str


class RootCauseAnalysis(BaseModel):
    ranked_causes: list[RankedCause] = Field(default_factory=list, max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(default_factory=list, max_length=3)


class FinancialResolution(BaseModel):
    currency: str
    item_total_brl: float
    freight_total_brl: float
    payment_total_brl: float
    recommended_refund_brl: float


class CaseOutput(BaseModel):
    case_id: str
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[Literal[RESOLUTION_ACTIONS]] = Field(
        default_factory=list, max_length=5
    )

    @field_validator("evidence_ids")
    @classmethod
    def _validate_evidence_ids(cls, value: list[str]) -> list[str]:
        for eid in value:
            if not is_valid_evidence_id(eid):
                raise ValueError(f"invalid evidence id format: {eid}")
        return value
