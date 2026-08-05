from pydantic import BaseModel, Field

from src.agents.base import Agent
from src.data_store import OrderFacts
from src.schemas import CaseOutput, is_valid_evidence_id

SYSTEM_PROMPT = (
    "Bạn là Verifier Agent, bước kiểm chứng cuối cùng trước khi ghi kết quả ra file. "
    "Bạn nhận được draft kết quả (JSON) và các facts gốc đã trích xuất từ dữ liệu. "
    "Nhiệm vụ: phát hiện bất thường/hallucination — ví dụ evidence_id không khớp facts, "
    "primary_issue không phù hợp với facts, số tiền vô lý. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"is_valid": bool, "issues": [string mô tả từng vấn đề phát hiện được, rỗng nếu không có], '
    '"summary": string (1 câu tiếng Việt)}'
)


class VerifierReview(BaseModel):
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    summary: str = ""


class VerifierAgent(Agent):
    name = "verifier_agent"

    def run(self, case_id: str, draft: CaseOutput, facts: OrderFacts) -> VerifierReview:
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"draft_output: {draft.model_dump()}\n"
            f"order_status: {facts.order.order_status if facts.order else None}\n"
            f"item_count: {len(facts.items)}\n"
            f"payment_count: {len(facts.payments)}\n"
            f"seller_ids: {list(facts.sellers.keys())}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, VerifierReview)


def deterministic_hard_gate_check(draft: CaseOutput, facts: OrderFacts) -> list[str]:
    """Ground-truth assertions independent of any LLM. Returns a list of
    violation descriptions; empty list means the draft is safe to write."""
    problems: list[str] = []

    valid_order_ids = {facts.order.order_id} if facts.order else set()
    valid_item_ids = {f"{i.order_id}:{i.order_item_id}" for i in facts.items}
    valid_seller_ids = set(facts.sellers.keys())
    valid_payment_ids = {f"{p.order_id}:{p.payment_sequential}" for p in facts.payments}

    ae = draft.affected_entities
    if len(ae.order_ids) > 5 or len(ae.item_ids) > 5 or len(ae.seller_ids) > 5 or len(ae.payment_ids) > 5:
        problems.append("affected_entities vượt quá 5 phần tử ở một entity set")
    if set(ae.order_ids) - valid_order_ids:
        problems.append(f"order_ids không khớp facts: {set(ae.order_ids) - valid_order_ids}")
    if set(ae.item_ids) - valid_item_ids:
        problems.append(f"item_ids không khớp facts: {set(ae.item_ids) - valid_item_ids}")
    if set(ae.seller_ids) - valid_seller_ids:
        problems.append(f"seller_ids không khớp facts: {set(ae.seller_ids) - valid_seller_ids}")
    if set(ae.payment_ids) - valid_payment_ids:
        problems.append(f"payment_ids không khớp facts: {set(ae.payment_ids) - valid_payment_ids}")

    if len(draft.evidence_ids) > 10:
        problems.append("evidence_ids vượt quá 10 phần tử")
    for eid in draft.evidence_ids:
        if not is_valid_evidence_id(eid):
            problems.append(f"evidence_id sai định dạng: {eid}")
            continue
        kind, _, rest = eid.partition(":")
        if kind == "order" and rest not in valid_order_ids:
            problems.append(f"evidence_id order không tồn tại: {eid}")
        elif kind == "item" and rest not in valid_item_ids:
            problems.append(f"evidence_id item không tồn tại: {eid}")
        elif kind == "payment" and rest not in valid_payment_ids:
            problems.append(f"evidence_id payment không tồn tại: {eid}")
        elif kind == "seller" and rest not in valid_seller_ids:
            problems.append(f"evidence_id seller không tồn tại: {eid}")

    if len(draft.root_cause_analysis.ranked_causes) > 3:
        problems.append("ranked_causes vượt quá 3")
    if len(draft.root_cause_analysis.responsible_parties) > 3:
        problems.append("responsible_parties vượt quá 3")
    if len(draft.resolution_actions) > 5:
        problems.append("resolution_actions vượt quá 5")
    if not (0.0 <= draft.assessment.confidence <= 1.0):
        problems.append("confidence ngoài [0,1]")

    item_total = round(sum(i.price for i in facts.items) + 1e-9, 2)
    freight_total = round(sum(i.freight_value for i in facts.items) + 1e-9, 2)
    payment_total = round(sum(p.payment_value for p in facts.payments) + 1e-9, 2)
    fr = draft.financial_resolution
    if abs(fr.item_total_brl - item_total) > 0.01:
        problems.append(f"item_total_brl sai: draft={fr.item_total_brl} expected={item_total}")
    if abs(fr.freight_total_brl - freight_total) > 0.01:
        problems.append(f"freight_total_brl sai: draft={fr.freight_total_brl} expected={freight_total}")
    if abs(fr.payment_total_brl - payment_total) > 0.01:
        problems.append(f"payment_total_brl sai: draft={fr.payment_total_brl} expected={payment_total}")

    if not facts.items and (ae.item_ids or ae.seller_ids):
        problems.append("order không có item nhưng item_ids/seller_ids không rỗng")

    return problems
