from typing import Literal

from pydantic import BaseModel

from src.agents.base import Agent
from src.data_store import OrderFacts
from src.policy_engine import is_delivered_late

SYSTEM_PROMPT = (
    "Bạn là Delivery Agent trong hệ thống xử lý khiếu nại thương mại điện tử Olist. "
    "Bạn được cung cấp sẵn 'delivered_late_verified' — kết quả so sánh order_delivered_customer_date "
    "với order_estimated_delivery_date đã được HỆ THỐNG tính chính xác bằng code, không phải do bạn "
    "tự so sánh. TUYỆT ĐỐI giữ nguyên giá trị này trong trường delivered_late của output. "
    "Việc của bạn: chọn late_cause dựa trên delivered_late_verified và sellers_late_handoff (nếu "
    "delivered_late_verified=false thì late_cause='not_late'; nếu true và sellers_late_handoff không "
    "rỗng thì 'seller_handoff'; nếu true và sellers_late_handoff rỗng thì 'logistics') và viết summary. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"delivered_late": bool — PHẢI COPY Y NGUYÊN delivered_late_verified, '
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
        delivered_late_verified = is_delivered_late(order)
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"order_delivered_customer_date: {order.order_delivered_customer_date if order else None}\n"
            f"order_estimated_delivery_date: {order.order_estimated_delivery_date if order else None}\n"
            f"order_delivered_carrier_date: {order.order_delivered_carrier_date if order else None}\n"
            f"delivered_late_verified (đã tính sẵn bằng code, PHẢI copy y nguyên): "
            f"{delivered_late_verified}\n"
            f"sellers_late_handoff (từ Order & Seller Agent, đã kiểm chứng): {sellers_late_handoff}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, DeliveryFindings)
