from pydantic import BaseModel

from src.agents.base import Agent
from src.data_store import OrderFacts
from src.policy_engine import is_payment_reconciled

SYSTEM_PROMPT = (
    "Bạn là Payment Agent trong hệ thống xử lý khiếu nại thương mại điện tử Olist. "
    "Bạn được cung cấp sẵn 'reconciled_verified' — kết quả đối chiếu tổng payment với tổng "
    "item+freight đã được HỆ THỐNG tính chính xác bằng code (sai số 0.10 BRL), không phải do bạn "
    "tự cộng. TUYỆT ĐỐI giữ nguyên giá trị này trong trường reconciled của output — không tự tính "
    "lại. Việc của bạn: suy ra looks_like_valid_split_payment (đúng khi payment_count >= 2 VÀ "
    "reconciled_verified = true) và viết summary diễn giải. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"payment_count": int, "reconciled": bool — PHẢI COPY Y NGUYÊN reconciled_verified, '
    '"looks_like_valid_split_payment": bool, "summary": string (1-2 câu tiếng Việt)}'
)


class PaymentFindings(BaseModel):
    payment_count: int
    reconciled: bool
    looks_like_valid_split_payment: bool
    summary: str = ""


class PaymentAgent(Agent):
    name = "payment_agent"

    def run(
        self,
        case_id: str,
        facts: OrderFacts,
        item_total: float,
        freight_total: float,
        payment_total: float,
    ) -> PaymentFindings:
        payments_desc = [
            {"payment_sequential": p.payment_sequential, "payment_value": p.payment_value}
            for p in facts.payments
        ]
        reconciled_verified = is_payment_reconciled(payment_total, round(item_total + freight_total, 2))
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"item_total_brl (đã tính sẵn): {item_total}\n"
            f"freight_total_brl (đã tính sẵn): {freight_total}\n"
            f"payment_total_brl (đã tính sẵn): {payment_total}\n"
            f"payments: {payments_desc}\n"
            f"reconciled_verified (đã tính sẵn bằng code, PHẢI copy y nguyên): {reconciled_verified}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, PaymentFindings)
