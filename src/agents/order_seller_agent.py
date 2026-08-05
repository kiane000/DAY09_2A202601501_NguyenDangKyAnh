from pydantic import BaseModel, Field

from src.agents.base import Agent
from src.data_store import OrderFacts
from src.policy_engine import violating_seller_ids

SYSTEM_PROMPT = (
    "Bạn là Order & Seller Agent trong hệ thống xử lý khiếu nại thương mại điện tử Olist. "
    "Bạn được cung cấp sẵn 'sellers_late_handoff_verified' — danh sách seller_id đã được HỆ THỐNG "
    "tính toán chính xác bằng code (so sánh shipping_limit_date với ngày carrier nhận hàng), không "
    "phải do bạn tự suy luận. TUYỆT ĐỐI giữ nguyên danh sách này trong trường sellers_late_handoff "
    "của output — không tự tính lại, không thêm/bớt seller. Việc của bạn chỉ là liệt kê "
    "seller_ids_involved từ items và viết summary diễn giải. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"order_status": string, "seller_ids_involved": [string], '
    '"sellers_late_handoff": [string — PHẢI COPY Y NGUYÊN sellers_late_handoff_verified], '
    '"summary": string (1-2 câu tiếng Việt giải thích)}'
)


class OrderSellerFindings(BaseModel):
    order_status: str
    seller_ids_involved: list[str] = Field(default_factory=list)
    sellers_late_handoff: list[str] = Field(default_factory=list)
    summary: str = ""


class OrderSellerAgent(Agent):
    name = "order_seller_agent"

    def run(self, case_id: str, facts: OrderFacts) -> OrderSellerFindings:
        order = facts.order
        items_desc = [
            {
                "order_item_id": item.order_item_id,
                "seller_id": item.seller_id,
                "shipping_limit_date": str(item.shipping_limit_date),
            }
            for item in facts.items
        ]
        verified_late_sellers = violating_seller_ids(order, facts.items)
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"order_status: {order.order_status if order else 'UNKNOWN'}\n"
            f"order_delivered_carrier_date: {order.order_delivered_carrier_date if order else None}\n"
            f"items: {items_desc}\n"
            f"sellers_late_handoff_verified (đã tính sẵn bằng code, PHẢI copy y nguyên): "
            f"{verified_late_sellers}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, OrderSellerFindings)
