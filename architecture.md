# Kiến trúc hệ thống Multi-Agent Dispute Resolution

## 1. Tổng quan

Hệ thống gồm 6 agent, mỗi agent gọi cùng một model local `qwen2.5:7b-instruct` (≤10B tham số, chạy qua Ollama) cho phần suy luận riêng của mình. Việc **truy xuất dữ liệu và mọi phép tính số học/ID luôn do code Python (pandas) đảm nhiệm** — LLM không bao giờ tự cộng tiền hay tự bịa ID; vai trò của LLM là diễn giải facts, phân loại độc lập và kiểm chứng chéo, đúng tinh thần "ưu tiên dữ liệu có thể kiểm chứng" của đề bài.

```mermaid
flowchart TB
    IN["input/EC_xxx.json"] --> DS["data_store.py\n(load 9 CSV, join theo claimed_order_id)"]
    DS --> PE["policy_engine.py\n(deterministic — nguồn sự thật)"]

    subgraph AGENTS["6 Agent (mỗi agent gọi qwen2.5:7b-instruct qua Ollama)"]
        OSA["Order & Seller Agent"]
        PA["Payment Agent"]
        DA["Delivery Agent"]
        POA["Policy Agent"]
        VA["Verifier Agent"]
        COORD["Coordinator Agent"]
    end

    DS --> OSA
    PE --> PA
    DS --> PA
    DS --> DA
    OSA -->|handoff: sellers_late_handoff| DA
    OSA -->|handoff| POA
    PA -->|handoff| POA
    DA -->|handoff| POA
    POA -->|primary_issue độc lập + confidence| COORD

    COORD --> DRAFT["Draft CaseOutput\n(ghép từ policy_engine — không phải từ LLM)"]
    DRAFT --> VA
    VA -->|LLM review bất thường| GATE["deterministic_hard_gate_check()\n(assertion cứng, không qua LLM)"]
    GATE -->|pass| OUT["output/EC_xxx.json"]
    GATE -->|fail| ERR["raise — case bị chặn, không ghi file sai"]

    AGENTS -.->|mỗi lời gọi LLM| TRACE["logging/trace.jsonl"]
```

## 2. Vai trò từng agent

| Agent | Đọc dữ liệu gì | Việc LLM thực sự làm | Việc code (không qua LLM) đảm bảo |
| --- | --- | --- | --- |
| **Order & Seller Agent** | `orders`, `order_items`, `sellers` (qua `data_store`) | Liệt kê `seller_ids_involved` từ items, viết tóm tắt diễn giải | `policy_engine.violating_seller_ids()` tính sẵn danh sách seller bàn giao trễ (so sánh `shipping_limit_date`), đưa vào prompt như fact đã kiểm chứng — agent **copy nguyên**, không tự so sánh timestamp |
| **Payment Agent** | `order_payments` + tổng đã tính sẵn bởi code | Suy ra `looks_like_valid_split_payment` từ fact có sẵn, viết tóm tắt | `policy_engine.is_payment_reconciled()` tính sẵn kết quả đối chiếu (sai số 0.10 BRL) và `sum()` các tổng tiền — agent **copy nguyên** `reconciled`, không tự cộng |
| **Delivery Agent** | `orders` (mốc thời gian) + handoff từ Order & Seller Agent | Chọn `late_cause` (seller/logistics/not_late) dựa trên fact có sẵn, viết tóm tắt | `policy_engine.is_delivered_late()` tính sẵn kết quả so sánh ngày giao — agent **copy nguyên** `delivered_late`, không tự so sánh |
| **Policy Agent** | Handoff từ 3 agent trên (nay đều dựa trên fact đã kiểm chứng) + nội dung khiếu nại khách hàng + bảng luật `EC_POLICY_V1` | Tự phân loại `primary_issue` + `confidence` + rationale, **độc lập** với engine | `policy_engine.apply_policy()` áp đúng bảng ưu tiên README §4 làm **nguồn sự thật cho `primary_issue` cuối cùng**; nếu LLM lệch kết quả, hệ thống hạ `confidence` (không crater xuống mức cứng) nhưng vẫn giữ kết quả engine |
| **Verifier Agent** | Draft `CaseOutput` + facts gốc | Rà soát bất thường/hallucination (evidence lạ, số liệu vô lý) | `deterministic_hard_gate_check()` chặn cứng: evidence ID đúng định dạng & tồn tại thật trong CSV, cap độ dài list (5/10/3/3/5), `confidence` ∈ [0,1], số tiền khớp giá trị tính lại từ CSV |
| **Coordinator Agent** | Toàn bộ output của 5 agent trên | Tổng hợp bản tóm tắt nội bộ (ghi vào `logging/trace.jsonl`, không thuộc schema output) | Điều phối tuần tự, ghép `CaseOutput` cuối cùng hoàn toàn từ `policy_engine` + facts, ghi file `output/EC_xxx.json` |

## 3. Luồng xử lý 1 case

1. `Coordinator` đọc `input/EC_xxx.json`, lấy `claimed_order_id`.
2. `data_store.get_order_facts()` join `orders` + `order_items` + `order_payments` + `sellers` theo `order_id`/`seller_id`.
3. `policy_engine.apply_policy(facts)` tính `primary_issue`, `responsible_parties`, `root_cause_code`, các tổng tiền, `resolution_actions` — đây là **nguồn sự thật**.
4. `Order & Seller Agent` → `Payment Agent` → `Delivery Agent` chạy tuần tự, mỗi agent nhận facts liên quan + (với Delivery Agent) handoff từ Order & Seller Agent.
5. `Policy Agent` nhận handoff từ 3 agent trên, tự phân loại độc lập; kết quả được đối chiếu với `policy_engine` — nếu khớp thì `confidence` cuối là trung bình của 2 nguồn, nếu lệch thì hạ `confidence` và ghi cảnh báo vào `logging/trace.jsonl` (không đổi `primary_issue`).
6. `Coordinator` ghép `CaseOutput` từ kết quả `policy_engine` (không từ output tự do của LLM).
7. `Verifier Agent` review bằng LLM, sau đó `deterministic_hard_gate_check()` chạy assertion cứng; nếu fail thì case bị chặn (raise) thay vì ghi output sai.
8. Ghi `output/EC_xxx.json`; mọi lời gọi LLM (input, output, model, latency, số lần retry) được ghi vào `logging/trace.jsonl`.

## 4. Vì sao tách "nguồn sự thật tất định" khỏi "suy luận LLM"

Bảng luật README §4 là một cây điều kiện tất định (so sánh `order_status`, timestamp, tổng payment) — hoàn toàn có thể tính đúng 100% bằng code. Vì **case bị hard gate nhận 0 điểm**, thiết kế ưu tiên độ chính xác tuyệt đối cho các phần có thể kiểm chứng (affected_entities, financial_resolution, evidence_ids, root_cause, resolution_actions — 80% trọng số), đồng thời vẫn bắt mỗi agent gọi LLM thật cho đúng yêu cầu "phân công, handoff, kiểm chứng giữa các agent" thay vì gộp toàn bộ xử lý vào một prompt duy nhất.

**Bài học rút ra khi audit `logging/trace.jsonl` thực tế:** ở phiên bản đầu, `Order & Seller Agent`/`Delivery Agent`/`Payment Agent` được giao tự so sánh raw timestamp và tự cộng tiền trong prompt — dù `primary_issue` cuối cùng vẫn luôn đúng (lấy từ `policy_engine`), việc này khiến `gpt-4o-mini` thỉnh thoảng tính sai (ví dụ 19.9 + 7.78 = 27.68 nhưng LLM báo "không khớp"), lan xuống Policy Agent khiến nó chọn nhầm rule và kéo `confidence` xuống thấp một cách không cần thiết ở 6/50 case. Đã sửa: các agent này giờ nhận thẳng kết quả so sánh/tính toán **đã làm sẵn bằng code** (`policy_engine.violating_seller_ids()`, `is_payment_reconciled()`, `is_delivered_late()`) như fact bắt buộc phải giữ nguyên trong output, LLM chỉ còn việc diễn giải/tổng hợp — đúng tinh thần "không để LLM tự làm arithmetic" đã đề ra nhưng chưa áp dụng triệt để ở vòng đầu. Sau khi sửa: tỷ lệ đồng thuận Policy Agent với engine đạt 50/50 case, confidence trung bình tăng từ mức có 6 case ở 0.7 lên toàn bộ ≥0.89 (trung bình 0.93).

## 5. Giới hạn model

Mỗi agent dùng chung một model, khai báo cứng trong `src/config.py` (`MODEL_NAME`, `LLM_PROVIDER`) và lặp lại trong `logging/metadata.json`. Hệ thống hỗ trợ 2 provider qua `src/llm_client.py` (chọn bằng `config.LLM_PROVIDER`):

- **Ollama local** (`qwen2.5:7b-instruct` hoặc `qwen2.5:3b-instruct`) — open-weight, công bố rõ số tham số, đảm bảo đúng giới hạn ≤10B của lưu ý #1 README.
- **OpenAI `gpt-4o-mini`** — dùng theo yêu cầu tường minh của người dùng để tăng tốc độ chạy, được cho phép bởi Lab Coach.
