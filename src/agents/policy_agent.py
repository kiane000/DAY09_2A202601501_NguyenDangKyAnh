from pydantic import BaseModel, Field

from src.agents.base import Agent
from src.agents.delivery_agent import DeliveryFindings
from src.agents.order_seller_agent import OrderSellerFindings
from src.agents.payment_agent import PaymentFindings
from src.schemas import PRIMARY_ISSUES

POLICY_TABLE_TEXT = """
Áp dụng theo đúng thứ tự ưu tiên sau (chọn rule đầu tiên khớp điều kiện):
1. canceled_order_paid: order_status = canceled VÀ tổng payment > 0.
2. unavailable_order_paid: order_status = unavailable VÀ tổng payment > 0.
3. late_delivery_seller: giao sau estimated date VÀ carrier nhận hàng sau shipping_limit_date của seller đó.
4. late_delivery_logistics: giao sau estimated date VÀ carrier nhận hàng không muộn hơn shipping_limit_date.
5. valid_split_payment: có từ 2 payment row trở lên; tổng payment khớp tổng item+freight (sai số 0.10 BRL).
6. unsupported_late_claim: đơn giao không muộn hơn estimated date và payment khớp.
""".strip()

SYSTEM_PROMPT = (
    "Bạn là Policy Agent, áp dụng chính sách EC_POLICY_V1 để phân loại khiếu nại. "
    "Bạn nhận được: nội dung khiếu nại của khách hàng, và các phát hiện (facts) đã được "
    "Order & Seller Agent, Payment Agent, Delivery Agent xác nhận từ dữ liệu thật. "
    "Chỉ được chọn primary_issue trong đúng 6 giá trị của bảng luật, áp dụng đúng thứ tự ưu tiên. "
    "Không tự bịa thêm sự kiện ngoài các facts được cung cấp. "
    "Chỉ trả lời bằng một JSON object hợp lệ, không thêm chữ nào khác."
)

RESPONSE_SCHEMA_HINT = (
    "Schema JSON bắt buộc: "
    '{"primary_issue": một trong ' + str(list(PRIMARY_ISSUES)) + ", "
    '"confidence": float trong [0,1], "rationale": string (1-3 câu tiếng Việt)}'
)


class PolicyClassification(BaseModel):
    primary_issue: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class PolicyAgent(Agent):
    name = "policy_agent"

    def run(
        self,
        case_id: str,
        customer_message: str,
        order_seller: OrderSellerFindings,
        payment: PaymentFindings,
        delivery: DeliveryFindings,
    ) -> PolicyClassification:
        user_prompt = (
            f"{POLICY_TABLE_TEXT}\n\n{RESPONSE_SCHEMA_HINT}\n\n"
            f"customer_message: {customer_message}\n"
            f"order_seller_findings: {order_seller.model_dump()}\n"
            f"payment_findings: {payment.model_dump()}\n"
            f"delivery_findings: {delivery.model_dump()}\n"
        )
        return self.call_llm(case_id, SYSTEM_PROMPT, user_prompt, PolicyClassification)
