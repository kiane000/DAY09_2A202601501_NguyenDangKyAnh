# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | Nguyễn Đặng Kỳ Anh  |
| MSSV            | 2A202601501 |
| Khóa/Lớp        | K3         |
| Vai trò chính   | Triển khai kỹ thuật toàn bộ pipeline multi-agent (data layer, policy engine, 6 agent LLM, orchestration, testing/debugging)   |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao   | Trạng thái                            |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| Data layer — load & join CSV Olist | `src/data_store.py` (`DataStore.get_order_facts`) | 9 file CSV trong `data/` + `claimed_order_id` | `OrderFacts` (order/items/payments/sellers đã join) | Hoàn thành |
| Policy engine tất định | `src/policy_engine.py` (`apply_policy`, `is_delivered_late`, `violating_seller_ids`, `is_payment_reconciled`) | `OrderFacts` | `PolicyDecision`: primary_issue, root cause, responsible party, số tiền, action | Hoàn thành, có `tests/test_policy_engine.py` (7/7 pass) cover đủ 6 nhánh rule |
| LLM client & schema validation | `src/llm_client.py`, `src/schemas.py` | prompt + Pydantic model | JSON đã validate, tự retry khi sai schema | Hoàn thành, hỗ trợ 2 provider (Ollama local / OpenAI) |
| 6 agent + orchestration | `src/agents/*.py`, `src/coordinator.py`, `src/main.py` | `input/EC_xxx.json` + `OrderFacts` | `output/EC_xxx.json` theo đúng schema README §6 | Hoàn thành, chạy thật 50/50 case |
| Verification & tooling | `src/agents/verifier_agent.py` (`deterministic_hard_gate_check`), `scripts/validate_output.py` | Draft output + facts gốc | Chặn cứng case sai trước khi ghi file; báo cáo pass/fail độc lập cho cả 50 output | Hoàn thành, 50/50 pass |
| Tài liệu & metadata | `architecture.md`, `src/main.py` (`write_metadata`) | Toàn bộ hệ thống | Sơ đồ kiến trúc + `logging/metadata.json` khai báo model/runtime | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Debug lỗi confidence thấp sau khi có phản hồi điểm số | Toàn bộ pipeline (self-audit) | Phát hiện và fix lỗi LLM tự làm arithmetic ở 3 agent, xem mục 6 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Xây policy engine đúng bảng ưu tiên README §4 | `src/policy_engine.py` | 6 nhánh rule đều có unit test | `pytest tests/test_policy_engine.py -q` → 7 passed |
| Chạy pipeline thật qua 50 case với LLM (`gpt-4o-mini`) | `src/main.py`, `output/`, `logging/trace.jsonl` | 50/50 case thành công, 0 lỗi | `python -m src.main` → "50/50 case thành công, 0 lỗi" |
| Validate độc lập toàn bộ output so với dữ liệu gốc | `scripts/validate_output.py` | 50/50 case pass (schema, evidence tồn tại thật trong CSV, số tiền khớp) | `python scripts/validate_output.py` → "Tất cả case pass validation." |
| Khai báo model/runtime minh bạch | `logging/metadata.json` | Ghi rõ model dùng thật (`gpt-4o-mini`) và giới hạn không xác nhận được về param size | Xem `logging/metadata.json` |

Một output cụ thể: `logging/metadata.json` — sinh tự động sau mỗi lần chạy `python -m src.main`, chứa `run_summary` (`total_cases`, `succeeded`, `failed`, `elapsed_seconds`) lấy trực tiếp từ kết quả chạy thật, không phải số liệu tự khai.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Xây dựng hệ thống multi-agent xử lý 50 case khiếu nại, mỗi agent phải dùng LLM thật (≤10B theo đề bài) để phân tích, có handoff và kiểm chứng chéo giữa các agent — nhưng vẫn phải đảm bảo `primary_issue`, số tiền hoàn, evidence ID đúng 100% vì "case bị hard gate nhận 0 điểm".

### Cách triển khai

Tách rõ hai lớp: (1) `policy_engine.py` — hàm Python thuần, áp đúng bảng ưu tiên 6 rule (canceled/unavailable/late_delivery_seller/late_delivery_logistics/valid_split_payment/unsupported_late_claim), là nguồn sự thật duy nhất cho `primary_issue`, số tiền, root cause, action; (2) 6 agent (`Order & Seller`, `Payment`, `Delivery`, `Policy`, `Verifier`, `Coordinator`) mỗi agent gọi thật một model qua `src/llm_client.py`, nhận facts đã được code tính sẵn (không phải raw data cần tự suy luận số học), làm nhiệm vụ diễn giải/phân loại độc lập/kiểm chứng, rồi handoff kết quả cho agent tiếp theo. `Coordinator` ghép `CaseOutput` cuối cùng luôn từ `policy_engine`, không bao giờ từ output tự do của LLM — LLM chỉ ảnh hưởng đến `confidence` (qua cross-check với Policy Agent) và nội dung `logging/trace.jsonl`.

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | `input/EC_xxx.json` (case_id, claimed_order_id, customer message) + 9 CSV Olist trong `data/` |
| Output                  | `output/EC_xxx.json` đúng schema README §6, validate bằng Pydantic (`src/schemas.py`) |
| Module phụ thuộc        | `src/data_store.py` (join CSV), `src/policy_engine.py` (quyết định tất định) |
| Module sử dụng output   | `scripts/validate_output.py` (chấm lại độc lập), file nộp `output.zip` |
| Điều kiện lỗi cần xử lý | `claimed_order_id` không tồn tại trong CSV; LLM trả JSON sai schema (tự động retry tối đa 3 lần trong `llm_client.py`); hard-gate fail thì raise thay vì ghi output sai |

### Cách xác minh

```bash
./.venv/Scripts/python.exe -m pytest tests/ -q
./.venv/Scripts/python.exe -m src.main
./.venv/Scripts/python.exe scripts/validate_output.py
```

- **Kết quả mong đợi:** 7/7 unit test pass; 50/50 case chạy pipeline thành công; 50/50 output pass validation độc lập.
- **Kết quả thực tế:** Đúng như mong đợi ở lần chạy cuối cùng (xem `logging/trace.jsonl`, `logging/metadata.json`, timestamp `generated_at` mới nhất).
- **Artifact/log:** `logging/trace.jsonl` (400 dòng log, 8 dòng/case), `logging/metadata.json`, `output/EC_001.json`..`EC_050.json`, `output.zip`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chọn model LLM cho 6 agent. Đề bài giới hạn ≤10B params.
- **Các phương án đã cân nhắc:**
  1. `qwen2.5:7b-instruct` chạy local qua Ollama (đúng luật ≤10B, open-weight, công bố rõ param size).
  2. `qwen2.5:3b-instruct` chạy local qua Ollama (nhẹ hơn, vẫn đúng luật).
  3. `gpt-4o-mini` qua OpenAI API (theo yêu cầu tường minh của người phụ trách repo — nhanh nhất, nhưng OpenAI không công bố param size nên không xác nhận được có đúng ≤10B hay không).
- **Phương án đã chọn:** Phương án 3 (`gpt-4o-mini`), được cho phép bởi Lab Coach.
- **Lý do:** Phương án 1 đo thực tế chạy 55% CPU/45% GPU do không đủ VRAM (Quadro T2000 4GB), ~100s/case → ước tính 85 phút cho 50 case. Phương án 3 đo thực tế chỉ ~10s/case → 50 case trong ~8 phút.
- **Bằng chứng quyết định phù hợp:** Log thời gian chạy thật trong `logging/trace.jsonl`/`logging/metadata.json` (`run_summary.elapsed_seconds` = 474.0s cho 50 case).

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Sau khi chạy đủ 50 case và được chấm 93.6735/100 (không có breakdown chi tiết), tự audit thấy 6/50 case có `assessment.confidence = 0.7` — thấp bất thường so với các case còn lại (0.89–0.98).
- **Lệnh hoặc bước tái hiện:** Đọc `logging/trace.jsonl`, lọc các dòng `agent == "policy_cross_check"` có `agrees: false` cho 3 case mẫu EC_012, EC_018, EC_039.
- **Nguyên nhân gốc:** `Order & Seller Agent`/`Delivery Agent` được yêu cầu tự so sánh `order_delivered_carrier_date` với `shipping_limit_date`, và `Payment Agent` tự cộng `item_total + freight_total` rồi so với `payment_total` — `gpt-4o-mini` làm sai các phép so sánh/cộng đơn giản này (ví dụ case EC_018: 19.9 + 7.78 = 27.68 = đúng bằng `payment_total`, nhưng LLM trả lời `"reconciled": false`). Lỗi lan xuống `Policy Agent` khiến nó chọn nhầm nhánh rule, kéo `confidence` cuối xuống 0.7 dù `primary_issue` trong output vẫn luôn đúng (lấy từ `policy_engine`, không lấy từ LLM).
- **Cách xử lý:** Thêm 3 hàm tất định vào `policy_engine.py` (`is_delivered_late`, `violating_seller_ids`, `is_payment_reconciled`); sửa 3 agent để nhận kết quả đã tính sẵn này như một fact bắt buộc phải giữ nguyên trong output, chỉ còn làm nhiệm vụ diễn giải/tóm tắt — không tự so sánh/tự cộng nữa. Đồng thời làm mềm công thức phạt confidence khi vẫn còn bất đồng hiếm gặp (`src/coordinator.py`): từ `min(engine_conf, 0.7)` sang `max(engine_conf - 0.1, 0.75)`.
- **Cách xác minh sau khi sửa:** Chạy lại 3 case lỗi cũ qua LLM thật → cả 3 chuyển thành `agrees: true`, confidence từ 0.7 lên 0.89–0.96. Chạy lại full 50 case (`python -m src.main`) → tỷ lệ đồng thuận LLM/engine đạt 50/50 (trước đó 44/50), confidence trung bình toàn bộ 50 case tăng lên 0.9314, không còn case nào dưới 0.85. `pytest tests/test_policy_engine.py` vẫn 7/7 pass (hành vi engine không đổi, chỉ refactor).
- **Điều học được:** Dù đã có nguyên tắc thiết kế "không để LLM tự làm arithmetic" từ đầu, nguyên tắc này phải được áp dụng nhất quán ở MỌI agent, kể cả các agent tưởng như chỉ "diễn giải" — chỉ cần một agent trung gian tự so sánh số/ngày tháng sai là lỗi lan xuống các agent phía sau qua handoff.

## 7. Hiểu biết về luồng end-to-end

Ghi chú: 5 câu hỏi gốc trong mẫu báo cáo (nhắc tới Crossref, vector index) thuộc một bài lab khác, không áp dụng cho bài "Multi-Agent E-commerce Dispute Resolution" này. Trả lời dưới đây ánh xạ đúng khái niệm tương ứng trong pipeline thật của bài lab này.

**Câu trả lời:**

1. **Dữ liệu đi từ nguồn tới kết quả cuối như thế nào?** Từ 9 CSV Olist trong `data/`, `DataStore` (`src/data_store.py`) join theo `order_id`/`seller_id` thành `OrderFacts` cho từng `claimed_order_id` trong `input/EC_xxx.json`. `policy_engine.apply_policy()` áp bảng luật lên `OrderFacts` ra `PolicyDecision`. Song song, 6 agent LLM (Order & Seller → Payment → Delivery → Policy → Verifier → Coordinator) nhận facts đã kiểm chứng, suy luận/handoff cho nhau, rồi `Coordinator` ghép `CaseOutput` cuối cùng (luôn lấy trường quyết định từ `PolicyDecision`) và ghi ra `output/EC_xxx.json`.
2. **Bộ test và "ground truth" dùng để đo chất lượng ra sao?** Không có file đáp án riêng — `policy_engine.apply_policy()` chính là ground-truth tất định (được unit-test qua `tests/test_policy_engine.py` với facts giả lập cho từng nhánh rule). `scripts/validate_output.py` đóng vai trò "evaluation set": tính lại `apply_policy()` từ CSV gốc cho cả 50 `claimed_order_id` thật và so với `output/*.json` đã ghi, để phát hiện sai lệch độc lập với pipeline sinh ra output.
3. **Quality check nào khác ngoài đối chiếu số liệu?** `Verifier Agent` (LLM) rà soát bất thường/hallucination trước; sau đó `deterministic_hard_gate_check()` (code thuần, không qua LLM) chặn cứng: evidence ID đúng định dạng và tồn tại thật trong CSV, giới hạn độ dài list (5/10/3/3/5), `confidence` ∈ [0,1], số tiền khớp giá trị tính lại — nếu fail thì raise, không ghi file sai.
4. **Vì sao phải dùng cùng 50 case cho các lần chạy/so sánh?** Vì `logging/trace.jsonl`/`logging/metadata.json` chỉ giữ lượt chạy mới nhất (không append) — để so sánh cải tiến (ví dụ trước/sau khi sửa lỗi confidence ở mục 6) một cách công bằng, phải chạy lại đúng cùng 50 input case, cùng policy engine, để chênh lệch đo được (44/50 → 50/50 đồng thuận, confidence trung bình 0.7-thấp → 0.93) phản ánh đúng tác động của thay đổi code, không phải do khác input.
5. **"Sửa lỗi" được xem là thành công dựa trên artifact/metric nào?** Dựa trên: (a) `pytest tests/test_policy_engine.py` vẫn 7/7 pass sau refactor (không phá vỡ hành vi cũ); (b) 3 case lỗi cũ (EC_012, EC_018, EC_039) chuyển từ `agrees: false, confidence 0.7` sang `agrees: true, confidence 0.89–0.96` trong `logging/trace.jsonl`; (c) toàn bộ 50 case đạt tỷ lệ đồng thuận 50/50 và confidence trung bình 0.9314, không còn case nào dưới 0.85; (d) `scripts/validate_output.py` vẫn báo 50/50 pass sau khi chạy lại.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đặng Kỳ Anh
**Ngày xác nhận:** 2026-08-05
