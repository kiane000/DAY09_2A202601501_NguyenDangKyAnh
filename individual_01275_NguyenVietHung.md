# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | Nguyễn Việt Hùng  |
| MSSV            | 2A202601275 |
| Khóa/Lớp        | K3         |
| Vai trò chính   | Data layer (load & join 9 CSV Olist), policy engine tất định (rule-based, nguồn sự thật cho primary_issue/số tiền/root cause), schema validation, và verification tooling (hard gate + validate độc lập). Nhóm 2 người, chia module với Nguyễn Đặng Kỳ Anh (LLM client, 6 agent, orchestration/coordinator — xem `individual_01501_NguyenDangKyAnh.md`).    |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao   | Trạng thái                            |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| Data layer — load & join CSV Olist | `src/data_store.py` (`DataStore.get_order_facts`) | 9 file CSV trong `data/` + `claimed_order_id` | `OrderFacts` (order/items/payments/sellers đã join) | Hoàn thành |
| Policy engine tất định | `src/policy_engine.py` (`apply_policy`, `is_delivered_late`, `violating_seller_ids`, `is_payment_reconciled`) | `OrderFacts` | `PolicyDecision`: primary_issue, root cause, responsible party, số tiền, action | Hoàn thành, có `tests/test_policy_engine.py` (7/7 pass) cover đủ 6 nhánh rule |
| Schema validation | `src/schemas.py` | `CaseOutput` draft | Pydantic model validate đúng README §6 (cap 5/10/3/3/5, confidence ∈[0,1], regex evidence ID) | Hoàn thành |
| Verification & tooling | `src/agents/verifier_agent.py` (`deterministic_hard_gate_check`), `scripts/validate_output.py` | Draft output + facts gốc | Chặn cứng case sai trước khi ghi file; báo cáo pass/fail độc lập cho cả 50 output | Hoàn thành, 50/50 pass |

Phần `src/llm_client.py`, 6 agent (`src/agents/order_seller_agent.py`, `payment_agent.py`, `delivery_agent.py`, `policy_agent.py`), `src/coordinator.py`, `src/main.py`, `architecture.md` do Nguyễn Đặng Kỳ Anh phụ trách — xem `individual_01501_NguyenDangKyAnh.md`.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Thêm 3 hàm tất định `is_delivered_late`, `violating_seller_ids`, `is_payment_reconciled` vào `policy_engine.py` theo yêu cầu của Kỳ Anh, để 6 agent LLM nhận sẵn boolean/list thay vì tự so sánh raw timestamp/số tiền | 6 agent LLM của Kỳ Anh (`src/agents/*.py`) | 3 case từng có `agrees: false` (EC_012, EC_018, EC_039) hết hiện tượng lệch, `pytest tests/test_policy_engine.py` vẫn 7/7 pass sau khi thêm — chi tiết ở `individual_01501_NguyenDangKyAnh.md` mục 6 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Xây policy engine đúng bảng ưu tiên README §4 | `src/policy_engine.py` | 6 nhánh rule đều có unit test | `pytest tests/test_policy_engine.py -q` → 7 passed |
| Validate độc lập toàn bộ output so với dữ liệu gốc | `scripts/validate_output.py` | 50/50 case pass (schema, evidence tồn tại thật trong CSV, số tiền khớp) | `python scripts/validate_output.py` → "Tất cả case pass validation." |
| Load & join dữ liệu Olist thành `OrderFacts` | `src/data_store.py` (`DataStore.get_order_facts`) | Join đúng `order_id`/`seller_id` cho toàn bộ 50 `claimed_order_id`, không lỗi parse ngày (`pd.to_datetime(..., errors="coerce")` trả `None` thay vì raise khi thiếu ngày) | `python scripts/validate_output.py` chạy được hết 50 case mà không crash ở bước load facts |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

`tests/test_policy_engine.py` cover 7 case: 6 nhánh rule chính của bảng ưu tiên (`canceled_order_paid`, `unavailable_order_paid`, `late_delivery_seller`, `late_delivery_logistics`, `valid_split_payment`, `unsupported_late_claim`) cộng thêm 1 case biên `test_multi_seller_only_violating_seller_named` — đảm bảo khi một order có nhiều seller thì chỉ seller nào thực sự giao hàng cho carrier sau `shipping_limit_date` của chính mình mới bị liệt vào `violating_seller_ids`/`responsible_parties`, chứ không đổ lỗi hàng loạt cho mọi seller trong đơn. `scripts/validate_output.py` phát hiện được 4 loại lỗi độc lập với pipeline sinh output: sai `primary_issue`/`case_status` so với `apply_policy()` tính lại từ CSV gốc, sai số tiền (`item_total_brl`/`freight_total_brl`/`payment_total_brl`/`recommended_refund_brl`) lệch quá 0.01, evidence ID không tồn tại thật trong facts (order/item/payment/seller), và case rơi vào nhánh fallback (`matched_rule=False`) cần review tay.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline dùng LLM để phân tích và diễn giải khiếu nại, nhưng đề bài chấm cứng: case nào bị hard gate (evidence sai, số tiền sai, schema sai) thì nhận 0 điểm, bất kể phần diễn giải của LLM hay đến đâu. Nếu để LLM tự quyết định `primary_issue`/số tiền hoàn/root cause thì kết quả không tất định — cùng một case chạy hai lần có thể ra hai đáp án khác nhau, và không kiểm chứng lại được. Phần tôi phụ trách giải quyết đúng vấn đề này: xây một "nguồn sự thật tất định" (`policy_engine.py`) hoàn toàn không qua LLM, áp thẳng bảng ưu tiên 6 rule của README §4 lên facts đã join từ CSV gốc (`data_store.py`), rồi kiểm chứng độc lập (hard gate lúc ghi file + `validate_output.py` sau khi ghi) rằng mọi con số/evidence trong output thực sự khớp với facts đó — để LLM chỉ còn vai trò diễn giải/tóm tắt cho con người đọc, không phải nguồn quyết định.

### Cách triển khai

`apply_policy()` nhận một `OrderFacts` (đã join order/items/payments/sellers) và chạy qua các rule theo đúng thứ tự ưu tiên trong README §4, return ngay khi khớp rule đầu tiên (không đánh giá tiếp các rule sau): (1) `order_status == "canceled"` và đã thanh toán → hoàn toàn bộ, platform chịu trách nhiệm; (2) tương tự với `order_status == "unavailable"`; (3)-(4) nếu giao hàng trễ hơn `order_estimated_delivery_date` (`is_delivered_late`) thì kiểm tra tiếp có seller nào giao cho carrier trễ hơn `shipping_limit_date` của chính mình không (`violating_seller_ids`) — có thì lỗi seller, không thì lỗi logistics, cả hai đều chỉ hoàn phí ship; (5) nếu có ≥2 dòng payment và tổng khớp `item_total + freight_total` trong sai số 0.10 BRL (`is_payment_reconciled`) thì đây là split payment hợp lệ, không phải lỗi; (6) còn lại (giao đúng hạn, tiền khớp) thì khiếu nại trễ giao hàng không có cơ sở, từ chối hoàn tiền. Nếu `claimed_order_id` không có trong `orders.csv` thì rơi vào nhánh fallback với `confidence` thấp (0.3) và cờ `matched_rule=False` để hệ thống biết đây là case cần review tay chứ không phải quyết định chắc chắn. Hai lớp kiểm chứng riêng biệt: `deterministic_hard_gate_check()` chạy ngay trước khi ghi file, so draft output với facts gốc (affected_entities, evidence_ids, cap độ dài list, số tiền tính lại) và raise nếu sai — chặn cứng, không cho ghi case sai ra `output/`; `scripts/validate_output.py` chạy sau, độc lập hoàn toàn với pipeline (tự load lại CSV, tự gọi `apply_policy()` lần nữa), so từng file `output/*.json` với kết quả tính lại đó để phát hiện cả những lỗi có thể lọt qua hard gate (ví dụ do code pipeline và code hard gate vô tình dùng chung một chỗ sai).

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | `OrderFacts` (từ `data_store.py`) cho `policy_engine`; `output/*.json` + CSV gốc cho `validate_output.py` |
| Output                  | `PolicyDecision` (primary_issue, root cause, số tiền, action); báo cáo pass/fail cho `validate_output.py` |
| Module phụ thuộc        | `pandas` (đọc/parse CSV, so sánh `Timestamp`); không phụ thuộc `llm_client.py` hay bất kỳ agent nào — đây là điểm cố ý trong thiết kế |
| Module sử dụng output   | `src/agents/policy_agent.py`, `src/coordinator.py` (do Kỳ Anh xây, gọi `policy_engine` làm nguồn sự thật) |
| Điều kiện lỗi cần xử lý | `claimed_order_id` không tồn tại trong `orders.csv` → `facts.order = None`, `apply_policy()` không được raise mà phải trả về nhánh fallback có `matched_rule=False` để pipeline biết đây là case không chắc chắn; order tồn tại nhưng không có item row nào (`facts.items` rỗng) → `is_delivered_late` vẫn tính được nhưng `violating_seller_ids` phải trả `[]` thay vì lỗi, và fallback về nhánh `late_delivery_logistics`/`unsupported_late_claim`; ngày tháng thiếu/rỗng trong CSV (`order_delivered_customer_date`, `shipping_limit_date`, …) → `data_store.py` parse bằng `pd.to_datetime(..., errors="coerce")` rồi convert `NaT` thành `None` (`_none_if_nat`) để các hàm so sánh ngày không bao giờ nhận `NaT` (so sánh với `NaT` luôn `False`, dễ gây sai lệch âm thầm nếu không xử lý). |

### Cách xác minh

```bash
./.venv/Scripts/python.exe -m pytest tests/test_policy_engine.py -q
./.venv/Scripts/python.exe scripts/validate_output.py
```

- **Kết quả mong đợi:** 7/7 unit test của `policy_engine` (đủ 6 nhánh rule: canceled/unavailable/late_delivery_seller/late_delivery_logistics/valid_split_payment/unsupported_late_claim) pass; toàn bộ 50 output đã ghi ở `output/` pass validate độc lập (đúng schema `schemas.py`, evidence ID tồn tại thật trong CSV, số tiền khớp giá trị tính lại từ `policy_engine`).
- **Kết quả thực tế:** Đúng như mong đợi ở lần chạy cuối cùng — `pytest` báo `7 passed`; `validate_output.py` báo "Tổng số case input: 50; output hợp lệ hoàn toàn: 50" và "Tất cả case pass validation."
- **Artifact/log:** `tests/test_policy_engine.py`, output console của `scripts/validate_output.py`, `output/EC_001.json`..`EC_050.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Rule 5 (`valid_split_payment`) và rule 6 (`unsupported_late_claim`) cần so `payment_total_brl` (tổng các dòng `payment_value`) với `item_total_brl + freight_total_brl` để biết tiền đã thanh toán có khớp giá trị đơn hàng hay không (`is_payment_reconciled`). Vấn đề: đây là hai tổng được cộng từ nhiều dòng CSV khác nhau (nhiều item, nhiều payment record cho trường hợp trả góp/split payment), mỗi dòng gốc đã tự làm tròn 2 chữ số thập phân, nên cần quyết định dùng tiêu chí so sánh nào.
- **Các phương án đã cân nhắc:**
  1. So khớp tuyệt đối (`payment_total == merch_total`) — đơn giản, không có tham số phải chọn.
  2. Sai số theo phần trăm giá trị đơn hàng (ví dụ 0.5%) — sai số tự scale theo giá trị đơn.
  3. Sai số tuyệt đối cố định nhỏ (0.10 BRL), qua hàm `is_payment_reconciled(..., tolerance=RECONCILE_TOLERANCE_BRL)`.
- **Phương án đã chọn:** Phương án 3 — sai số tuyệt đối cố định 0.10 BRL.
- **Lý do:** Phương án 1 (so khớp tuyệt đối) rủi ro false negative: chỉ cần một dòng payment lệch 1 cent do làm tròn độc lập ở nguồn dữ liệu là toàn bộ case bị đẩy nhầm sang nhánh "chưa reconciled", dù về bản chất là hợp lệ. Phương án 2 (theo phần trăm) tạo ra hành vi không nhất quán giữa đơn rẻ và đơn đắt — với đơn giá trị nhỏ, sai số phần trăm co lại gần 0 và quay lại đúng vấn đề của phương án 1; với đơn giá trị lớn, sai số phần trăm có thể lớn hơn mức lệch làm tròn thực tế và che giấu lỗi số liệu thật. Phương án 3 khớp đúng bản chất vấn đề (lệch do làm tròn cent, không phải lệch tỉ lệ theo giá trị đơn) và giữ ngưỡng đủ chặt để không che giấu sai lệch tiền thật.
- **Bằng chứng quyết định phù hợp:** `scripts/validate_output.py` tính lại `apply_policy()` độc lập từ CSV gốc (dùng cùng hằng số `RECONCILE_TOLERANCE_BRL`) cho toàn bộ 50 case và so với `output/*.json` — kết quả "Tổng số case input: 50; output hợp lệ hoàn toàn: 50", nghĩa là không có case nào bị phân loại sai do ngưỡng 0.10 quá lỏng (che giấu lệch thật) hay quá chặt (từ chối nhầm case khớp thật); `tests/test_policy_engine.py::test_valid_split_payment` cũng cố định hành vi này bằng case có payment chia làm 2 dòng (60.0 + 55.0 = 115.0 khớp `item_total_brl + freight_total_brl`).

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Sau khi Kỳ Anh chạy đủ 50 case, anh ấy phát hiện 6/50 case có `assessment.confidence = 0.7` — thấp bất thường so với mặt bằng chung (0.89–0.98) — và báo lại cho tôi vì nghi ngờ liên quan tới cách các agent LLM tự so sánh dữ liệu thô lấy từ `data_store.py`.
- **Lệnh hoặc bước tái hiện:** Lọc `logging/trace.jsonl` các dòng `agent == "policy_cross_check"` có `agrees: false`, đối chiếu với 3 case mẫu (EC_012, EC_018, EC_039) và facts gốc lấy trực tiếp từ `DataStore.get_order_facts()` cho từng `claimed_order_id` đó.
- **Nguyên nhân gốc:** Trước đó, `policy_engine.py` chỉ có logic so sánh ngày/tổng tiền nằm gọn bên trong `apply_policy()`, các agent LLM của Kỳ Anh phải tự nhận `order_delivered_carrier_date`/`shipping_limit_date`/từng dòng `payment_value` dạng thô rồi tự so sánh/tự cộng lại để diễn giải — ví dụ case EC_018, `19.9 + 7.78 = 27.68` đúng bằng `payment_total`, nhưng LLM vẫn trả `"reconciled": false`. Đây là lỗi cấu trúc dữ liệu bàn giao (data contract), không phải lỗi logic trong `apply_policy()`: `apply_policy()` tự nó luôn tính đúng vì không qua LLM, nhưng vì các agent không được cho boolean/list đã tính sẵn nên chúng tự làm lại phép tính đó bằng LLM và có xác suất sai.
- **Cách xử lý:** Tách 3 phần logic so sánh vốn nằm ẩn trong `apply_policy()` thành 3 hàm độc lập, có tên và docstring rõ ràng, expose ra ngoài module: `is_delivered_late(order)`, `violating_seller_ids(order, items)`, `is_payment_reconciled(payment_total, merch_total, tolerance)` (xem `src/policy_engine.py` dòng 69–99). `apply_policy()` gọi lại đúng 3 hàm này thay vì so sánh inline như trước — hành vi không đổi, chỉ refactor để tách phần "tính toán tất định" thành đơn vị tái sử dụng được. Kỳ Anh sau đó sửa các agent (phần anh ấy phụ trách) để nhận kết quả 3 hàm này như fact bắt buộc giữ nguyên, không tự so sánh raw timestamp/số tiền nữa.
- **Cách xác minh sau khi sửa:** `pytest tests/test_policy_engine.py -q` vẫn 7/7 pass sau refactor (hành vi `apply_policy()` không đổi). Theo báo cáo của Kỳ Anh (`individual_01501_NguyenDangKyAnh.md` mục 6), sau khi các agent dùng 3 hàm này, 3 case mẫu chuyển từ `agrees: false` sang `agrees: true`, và tỷ lệ đồng thuận toàn bộ 50 case tăng từ 44/50 lên 50/50.
- **Điều học được:** Một hàm tất định đúng (`apply_policy()`) không đủ nếu dữ liệu bàn giao cho phần hạ nguồn (agent LLM) vẫn ở dạng thô buộc phải tự tính lại — phải chủ động expose kết quả trung gian đã tính sẵn dưới dạng hàm/giá trị rõ ràng, để ranh giới "phần nào LLM được suy luận, phần nào không" nằm ở data contract giữa hai module, chứ không chỉ ở tài liệu hay quy ước ngầm.

Nếu chưa xử lý xong: Không áp dụng — lỗi đã được xử lý và xác minh như trên.

## 7. Hiểu biết về luồng end-to-end
**Câu trả lời phản ánh đúng khái niệm tương ứng trong pipeline thật của bài lab này:**

1. **Dữ liệu đi từ CSV Olist đến kết quả cuối như thế nào?** `DataStore` (`src/data_store.py`) đọc 9 file CSV trong `data/` một lần khi khởi tạo, parse ngày tháng bằng `pd.to_datetime`. Với mỗi `claimed_order_id` lấy từ `input/EC_xxx.json`, `get_order_facts()` join order/items/payments/sellers theo `order_id`/`seller_id` thành một `OrderFacts`. `apply_policy()` (phần tôi phụ trách) chạy trên `OrderFacts` đó, áp bảng ưu tiên 6 rule, ra `PolicyDecision` — đây là nguồn duy nhất cho các trường quyết định (`primary_issue`, số tiền, root cause, action). Song song, 6 agent LLM (phần Kỳ Anh phụ trách) nhận `OrderFacts` cùng `PolicyDecision` đã tính sẵn để diễn giải/kiểm chứng chéo, rồi `Coordinator` ghép thành `CaseOutput`. Trước khi ghi ra `output/EC_xxx.json`, `deterministic_hard_gate_check()` (module tôi phụ trách) chặn lại nếu draft sai lệch với facts gốc.
2. **Bộ test và "ground truth" dùng để đo chất lượng ra sao?** Bài lab này không có file đáp án soạn sẵn — `apply_policy()` chính là ground truth tất định, được tôi cố định hành vi bằng `tests/test_policy_engine.py` (7 test: 6 nhánh rule chính + 1 case biên nhiều seller). `scripts/validate_output.py` đóng vai trò tập đánh giá: với mỗi case, tự load lại CSV, tự gọi `apply_policy()` một lần nữa từ đầu (không dùng lại state của pipeline đã chạy), rồi so với `output/*.json` đã ghi để phát hiện sai lệch.
3. **Quality check nào khác ngoài đối chiếu số liệu?** Hai lớp: `Verifier Agent` (LLM, `src/agents/verifier_agent.py`) rà soát bất thường/hallucination ở mức nội dung trước; sau đó `deterministic_hard_gate_check()` (code thuần, không qua LLM) kiểm tra định dạng — evidence ID đúng regex và tồn tại thật trong facts (order/item/payment/seller), độ dài các list không vượt cap (5 order/item/seller/payment ids, 10 evidence, 3 ranked cause, 3 responsible party, 5 resolution action theo `src/schemas.py`), `confidence` nằm trong [0,1], và số tiền trong draft khớp số tiền tính lại từ facts. Case nào fail bước này bị raise, không được ghi ra `output/`.
4. **Vì sao phải dùng cùng 50 case cho các lần chạy/so sánh?** Vì `apply_policy()` là hàm tất định — với cùng input CSV và cùng `claimed_order_id`, kết quả luôn giống nhau, nên nếu đổi tập case giữa hai lần so sánh thì không tách được thay đổi kết quả là do sửa code (agent, prompt, hay chính `policy_engine`) hay do đổi input. Giữ nguyên 50 case (`input/EC_001.json`..`EC_050.json`) là điều kiện để `scripts/validate_output.py` và `pytest` có cơ sở so sánh công bằng giữa các lần chạy, ví dụ để đo tác động của việc thêm 3 hàm tất định ở mục 6.
5. **"Sửa lỗi"/cải tiến được xem là thành công dựa trên artifact và metric nào?** Với phần tôi phụ trách: (a) `pytest tests/test_policy_engine.py -q` vẫn phải báo `7 passed` sau bất kỳ thay đổi nào ở `policy_engine.py` — nếu fail nghĩa là đã làm sai lệch nguồn sự thật; (b) `scripts/validate_output.py` phải báo "Tổng số case input: 50; output hợp lệ hoàn toàn: 50" và "Tất cả case pass validation." — đây là điều kiện cần trước khi đóng gói `output.zip`; (c) với thay đổi có ảnh hưởng chéo sang phần agent (như mục 6), tôi dựa thêm vào số liệu Kỳ Anh đo được ở `logging/trace.jsonl` (tỷ lệ đồng thuận LLM/engine, `confidence` trung bình) để xác nhận thay đổi ở `policy_engine.py` thực sự giải quyết được vấn đề phía hạ nguồn, không chỉ đúng về mặt unit test.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Việt Hùng
**Ngày xác nhận:** 2026-08-05
