from typing import Literal

from pydantic import BaseModel

from src.agents.base import Agent
from src.data_store import OrderFacts

SYSTEM_PROMPT = (
    "Bạn là Delivery Agent trong hệ thống xử lý khiếu nại thương mại điện tử Olist. "
    "Nhiệm vụ: so sánh order_delivered_customer_date với order_estimated_delivery_date để xác định "
    "đơn có giao trễ hay không, và nếu trễ thì nguyên nhân nghiêng về seller (bàn giao trễ cho carrier) "
    "hay logistics (carrier nhận đúng hạn nhưng giao trễ). Chỉ dùng dữ liệu được cung cấp, không suy diễn thêm. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"delivered_late": bool, '
    '"late_cause": "seller_handoff" | "logistics" | "not_late" | "unknown", '
    '"summary": string (1-2 câu tiếng Việt)}'
)


class DeliveryFindings(BaseModel):
    delivered_late: bool
    late_cause: Literal["seller_handoff", "logistics", "not_late", "unknown"]
    summary: str = ""


class DeliveryAgent(Agent):
    name = "delivery_agent"

    def run(self, case_id: str, facts: OrderFacts, sellers_late_handoff: list[str]) -> DeliveryFindings:
        order = facts.order
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"order_delivered_customer_date: {order.order_delivered_customer_date if order else None}\n"
            f"order_estimated_delivery_date: {order.order_estimated_delivery_date if order else None}\n"
            f"order_delivered_carrier_date: {order.order_delivered_carrier_date if order else None}\n"
            f"sellers_late_handoff (từ Order & Seller Agent): {sellers_late_handoff}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, DeliveryFindings)
