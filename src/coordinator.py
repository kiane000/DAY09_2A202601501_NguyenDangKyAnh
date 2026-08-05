import json
from pathlib import Path

from pydantic import BaseModel

from src import config
from src.agents.base import Agent
from src.agents.delivery_agent import DeliveryAgent
from src.agents.order_seller_agent import OrderSellerAgent
from src.agents.payment_agent import PaymentAgent
from src.agents.policy_agent import PolicyAgent
from src.agents.verifier_agent import VerifierAgent, deterministic_hard_gate_check
from src.data_store import DataStore, OrderFacts
from src.policy_engine import apply_policy
from src.schemas import (
    AffectedEntities,
    Assessment,
    CaseOutput,
    FinancialResolution,
    RankedCause,
    ResponsibleParty,
    RootCauseAnalysis,
)
from src.tracer import Tracer

SYNTHESIS_SYSTEM_PROMPT = (
    "Bạn là Coordinator Agent, tổng hợp kết luận cuối cùng từ các agent chuyên trách "
    "(Order & Seller, Payment, Delivery, Policy, Verifier) thành một bản tóm tắt ngắn cho hồ sơ nội bộ. "
    "Không tự thêm sự kiện mới ngoài dữ liệu đã cho. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)
SYNTHESIS_SCHEMA_HINT = (
    'Schema JSON bắt buộc: {"case_summary": string (2-3 câu tiếng Việt tóm tắt vụ việc và '
    'kết luận), "confidence_note": string (1 câu giải thích vì sao confidence ở mức đó)}'
)


class CoordinatorSynthesis(BaseModel):
    case_summary: str = ""
    confidence_note: str = ""


class CoordinatorAgent(Agent):
    name = "coordinator"


class Coordinator:
    def __init__(self, data_store: DataStore, tracer: Tracer):
        self.data_store = data_store
        self.tracer = tracer
        self.order_seller_agent = OrderSellerAgent(tracer)
        self.payment_agent = PaymentAgent(tracer)
        self.delivery_agent = DeliveryAgent(tracer)
        self.policy_agent = PolicyAgent(tracer)
        self.verifier_agent = VerifierAgent(tracer)
        self.coordinator_agent = CoordinatorAgent(tracer)

    def run_case(self, input_path: Path) -> CaseOutput:
        case_input = json.loads(input_path.read_text(encoding="utf-8"))
        case_id = case_input["case_id"]
        claimed_order_id = case_input["customer_request"]["claimed_order_id"]
        customer_message = case_input["customer_request"]["message"]

        facts = self.data_store.get_order_facts(claimed_order_id)
        decision = apply_policy(facts)

        order_seller_findings = self.order_seller_agent.run(case_id, facts)
        payment_findings = self.payment_agent.run(
            case_id, facts, decision.item_total_brl, decision.freight_total_brl,
            decision.payment_total_brl,
        )
        delivery_findings = self.delivery_agent.run(
            case_id, facts, order_seller_findings.sellers_late_handoff
        )
        policy_classification = self.policy_agent.run(
            case_id, customer_message, order_seller_findings, payment_findings, delivery_findings
        )

        agrees = policy_classification.primary_issue == decision.primary_issue
        if agrees:
            final_confidence = round(
                min(1.0, max(0.0, (decision.confidence + policy_classification.confidence) / 2)), 2
            )
        else:
            # decision.confidence is calibrated per matched rule and backed by
            # policy_engine (validated deterministic ground truth), so a lone
            # LLM disagreement is treated as a soft flag, not proof of real
            # ambiguity — reduce confidence but don't crater it.
            final_confidence = round(max(decision.confidence - 0.1, 0.75), 2)
        self.tracer.log(
            case_id=case_id,
            agent="policy_cross_check",
            engine_primary_issue=decision.primary_issue,
            llm_primary_issue=policy_classification.primary_issue,
            agrees=agrees,
            final_confidence=final_confidence,
        )

        draft = self._assemble_output(case_id, facts, decision, final_confidence)

        verifier_review = self.verifier_agent.run(case_id, draft, facts)
        hard_gate_problems = deterministic_hard_gate_check(draft, facts)
        if hard_gate_problems:
            # Should be unreachable since `draft` is built deterministically from
            # `decision`/`facts`, but kept as a hard safety net before writing output.
            raise RuntimeError(f"{case_id}: hard gate violations {hard_gate_problems}")

        self.coordinator_agent.call_llm(
            case_id,
            SYNTHESIS_SYSTEM_PROMPT,
            (
                f"{SYNTHESIS_SCHEMA_HINT}\n\n"
                f"policy_decision: {decision.rationale}\n"
                f"verifier_review: {verifier_review.model_dump()}\n"
                f"final_output: {draft.model_dump()}\n"
            ),
            CoordinatorSynthesis,
        )

        self.tracer.log(
            case_id=case_id,
            agent="coordinator",
            step="final",
            hard_gate_passed=True,
            verifier_is_valid=verifier_review.is_valid,
            verifier_issues=verifier_review.issues,
            output_path=str((config.OUTPUT_DIR / f"{case_id}.json").as_posix()),
        )

        output_path = config.OUTPUT_DIR / f"{case_id}.json"
        output_path.write_text(
            json.dumps(draft.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return draft

    def _assemble_output(
        self, case_id: str, facts: OrderFacts, decision, final_confidence: float
    ) -> CaseOutput:
        order = facts.order
        order_ids = [order.order_id] if order else []
        item_ids = [f"{i.order_id}:{i.order_item_id}" for i in facts.items][:5]
        seller_ids = sorted({i.seller_id for i in facts.items})[:5]
        payment_ids = [f"{p.order_id}:{p.payment_sequential}" for p in facts.payments][:5]

        evidence_candidates = []
        if order:
            evidence_candidates.append(f"order:{order.order_id}")
        evidence_candidates += [f"item:{i.order_id}:{i.order_item_id}" for i in facts.items]
        evidence_candidates += [f"payment:{p.order_id}:{p.payment_sequential}" for p in facts.payments]
        evidence_candidates += [f"seller:{sid}" for sid in seller_ids]
        evidence_ids = evidence_candidates[:9]
        evidence_ids.append(f"policy:{decision.root_cause_code}")
        evidence_ids = evidence_ids[:10]

        return CaseOutput(
            case_id=case_id,
            assessment=Assessment(
                primary_issue=decision.primary_issue,
                case_status=decision.case_status,
                confidence=final_confidence,
            ),
            affected_entities=AffectedEntities(
                order_ids=order_ids, item_ids=item_ids, seller_ids=seller_ids, payment_ids=payment_ids
            ),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=[RankedCause(cause_code=decision.root_cause_code, rank=1)],
                responsible_parties=[
                    ResponsibleParty(party_type=p.party_type, party_id=p.party_id)
                    for p in decision.responsible_parties
                ],
            ),
            evidence_ids=evidence_ids,
            financial_resolution=FinancialResolution(
                currency=config.CURRENCY,
                item_total_brl=decision.item_total_brl,
                freight_total_brl=decision.freight_total_brl,
                payment_total_brl=decision.payment_total_brl,
                recommended_refund_brl=decision.recommended_refund_brl,
            ),
            resolution_actions=decision.resolution_actions,
        )
