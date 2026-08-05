from pydantic import BaseModel

from src.agents.base import Agent
from src.data_store import OrderFacts

SYSTEM_PROMPT = (
    "Bạn là Payment Agent trong hệ thống xử lý khiếu nại thương mại điện tử Olist. "
    "Nhiệm vụ: đối chiếu tổng các payment row với tổng (item price + freight) đã được tính sẵn "
    "bằng code (đừng tự cộng lại, chỉ dùng số liệu được cung cấp), sai số cho phép là 0.10 BRL. "
    "Xác định có phải tình huống 'valid_split_payment' hay không (>=2 payment row và khớp tổng). "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"payment_count": int, "reconciled": bool, '
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
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"item_total_brl (đã tính sẵn): {item_total}\n"
            f"freight_total_brl (đã tính sẵn): {freight_total}\n"
            f"payment_total_brl (đã tính sẵn): {payment_total}\n"
            f"payments: {payments_desc}\n"
            "sai số reconciliation cho phép: 0.10 BRL"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, PaymentFindings)
