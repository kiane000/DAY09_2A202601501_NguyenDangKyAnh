from pydantic import BaseModel, Field

from src.agents.base import Agent
from src.data_store import OrderFacts

SYSTEM_PROMPT = (
    "Bạn là Order & Seller Agent trong hệ thống xử lý khiếu nại thương mại điện tử Olist. "
    "Nhiệm vụ: đọc dữ liệu order/item/seller đã được truy xuất sẵn (không được bịa thêm dữ liệu) "
    "và xác định seller nào đã bàn giao hàng cho carrier sau shipping_limit_date của chính họ. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"order_status": string, "seller_ids_involved": [string], '
    '"sellers_late_handoff": [string liệt kê các seller_id bàn giao trễ], '
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
        user_prompt = (
            f"{RESPONSE_SCHEMA_HINT}\n\n"
            f"order_status: {order.order_status if order else 'UNKNOWN'}\n"
            f"order_delivered_carrier_date: {order.order_delivered_carrier_date if order else None}\n"
            f"items: {items_desc}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, OrderSellerFindings)
