# SPEC — Hệ Thống Đánh Giá Chất Lượng RCA (v1.0)

> **Trạng thái:** Draft for review · **Nguồn chuẩn:** file Markdown này
> (bản HTML nếu cần chỉ là render từ MD, không được sửa riêng).
> **Phạm vi:** lớp đánh giá chất lượng cho pipeline RCA v6.
> **Tài liệu thiết kế nền:** `rca-evaluation-framework.md` (lý do, kiến trúc);
> spec này là **yêu cầu bắt buộc + tiêu chí nghiệm thu**, mỗi yêu cầu có ID
> để trace vào code và test.

---

## 0. Mục tiêu / Phi mục tiêu

**Mục tiêu:** đo lường chất lượng mọi run RCA một cách (a) trung thực —
không thể bị làm đẹp số liệu, kể cả vô tình; (b) chính xác — số đo phản ánh
đúng chất lượng thật; (c) tự động — không có bước thủ công nào trên đường đi
của số liệu.

**Phi mục tiêu:** hệ đánh giá KHÔNG can thiệp, sửa chữa, hay tái thẩm định
kết quả RCA; không thay thế human review; không thu thập log thô hay dữ liệu
định danh cá nhân ra khỏi máy engineer.

## 1. Mô hình tin cậy (trust model) — nền của "trung thực"

Ba vai tách bạch, không vai nào được kiêm vai khác:

| Vai | Ai | Được làm | Cấm |
|---|---|---|---|
| **Bị đo** (pipeline) | các skill v6 + engineer | tạo state file, report | ghi bất kỳ dữ liệu eval nào |
| **Đo** (evaluator) | `eval_extract` / `eval_ingest` / `eval_report` | đọc state/report, ghi eval store | sửa state file, report; chọn lọc run |
| **Chấm** (judge) | LLM-judge / human reviewer | đọc report + eval record | truy vấn lại log/spec/code; biết nguồn gốc khi chấm mù |

Nguy cơ phải chống (threat model):

- **T1 Cherry-picking:** chỉ run đẹp mới được extract → số liệu ảo.
- **T2 Tampering:** record hoặc report bị sửa sau khi run xong.
- **T3 Self-grading contamination:** judge chấm trong cùng context với agent
  vừa chạy RCA, hoặc biết bài nào của agent/của người khi chấm mù.
- **T4 Overfit golden:** chỉnh skill theo đúng các case dùng để chấm điểm.
- **T5 Amend lạm dụng:** sửa hồi tố (`reopened`, `rca_confirmed_by_fix`)
  không dấu vết.
- **T6 Gate drift:** ngưỡng KPI bị nới âm thầm để "cho qua".

## 2. Yêu cầu chức năng (FR)

| ID | Yêu cầu | Triển khai |
|---|---|---|
| FR-1 | Mỗi run đạt trạng thái terminal (`complete` hoặc abort) PHẢI sinh đúng một eval record theo `schemas/eval_record.schema.json` | `eval_extract.py`; auto-trigger FR-8 |
| FR-2 | Record phải ẩn danh: machine/user id là salted hash; không chứa log thô, không chứa nội dung DB | `eval_extract.py` `_sha12` |
| FR-3 | Ingest phải idempotent theo `run_id` (re-sync không nhân đôi) và từ chối record sai schema | `eval_ingest.py` |
| FR-4 | Judge chấm đúng 6 chiều rubric, thang 1–5, mỗi điểm kèm rationale trích dẫn report | `eval_judge.py` + rubric |
| FR-5 | Dashboard phải hiển thị: KPI vs gate, xu hướng tuần, theo máy, phân bố class, điểm judge LLM-vs-human, hàng đợi human review | `eval_report.py` |
| FR-6 | Amend chỉ được sửa 2 trường hồi tố (`rca_confirmed_by_fix`, `reopened`) và PHẢI để lại audit trail | `eval_ingest.py --amend` + bảng `eval_amendments` |
| FR-7 | Golden benchmark so khớp 3 tầng: class (L1), file (L2), function (L3), + top-event recall | `eval_extract.py --golden` |
| FR-8 | Khi `/rca` đạt `complete`, workflow tự chạy extract — không chờ engineer nhớ | bước auto-extract trong `.clinerules/workflows/rca.md` |

## 3. Yêu cầu trung thực / integrity (IN)

| ID | Yêu cầu | Chống nguy cơ | Triển khai |
|---|---|---|---|
| IN-1 | **Coverage toàn phần:** extract là bước tự động của workflow tại terminal, chạy cho CẢ run abort. Coverage audit định kỳ: đếm `rca_state_*.json` trên máy vs số record đã nộp; thiếu = incident | T1 | FR-8; mục 6 quy trình |
| IN-2 | **Tamper-evidence:** record nhúng `sha256` của state file và report tại thời điểm extract; ingest lưu hash; re-extract từ state file gốc phải tái tạo được record khớp hash | T2 | khối `integrity` trong record + cột trong `eval_runs` |
| IN-3 | **Đo không chạm bài đo:** mọi script eval mở state/report chế độ đọc; skill evaluator bị cấm ghi vào state file (HARD constraint trong SKILL.md) | T2 | evaluator skill |
| IN-4 | **Judge cách ly:** judge chạy context mới, input CHỈ gồm report + record; không lịch sử hội thoại của run; khi so agent-vs-manual, bài chấm phải che nguồn gốc (blind) | T3 | `eval_judge.py` (prompt tự đóng gói); quy trình chấm mù mục 6 |
| IN-5 | **Judge phải được hiệu chuẩn:** trước khi điểm judge được tính vào KPI chính thức, tương quan judge-vs-human (Spearman) trên ≥10 run phải ≥ 0.6; hiệu chuẩn lại mỗi khi đổi model/prompt judge | T3 | quy trình mục 6; bảng `eval_judge_scores` chứa cả human để đối chiếu |
| IN-6 | **Chống overfit golden:** case đã được dùng để debug/chỉnh skill bị loại khỏi set chấm chính thức (chuyển sang dev set); ghi rõ trong `notes.md` của case | T4 | quy tắc `golden/README.md` |
| IN-7 | **Amend có dấu vết:** mọi amend ghi một dòng vào `eval_amendments` (run_id, trường, giá trị cũ→mới, thời điểm); không UPDATE đè không vết | T5 | `eval_ingest.py` |
| IN-8 | **Gate versioned + fail-closed:** ngưỡng KPI nằm trong code (`GATES` của `eval_report.py`), đổi ngưỡng = đổi code = phải qua PR review; `--gate` fail trả exit ≠ 0, CI đỏ | T6 | `eval_report.py` |
| IN-9 | **Provenance là gate cứng:** run có keyword `verified=false` không bao giờ được tính là run chất lượng đạt, bất kể điểm judge | T2/T3 | gate `provenance_pass = 1.0` |

## 4. Yêu cầu chính xác (AC)

| ID | Yêu cầu |
|---|---|
| AC-1 | Nhãn golden phải được xác nhận bằng fix đã hoạt động (không phải ý kiến); log snapshot đóng băng theo case |
| AC-2 | Mọi metric tự động phải **định nghĩa tất định** (deterministic) từ state file — cùng state file luôn cho cùng record (trừ timestamp extract). Metric cần phán đoán (mechanism đúng?, chain mạch lạc?) thuộc về judge/human, không được mã hoá thành heuristic mờ trong extract |
| AC-3 | So sánh agent-vs-manual phải cùng đầu vào (cùng mô tả engineer, cùng DB), cùng thước đo, chấm mù |
| AC-4 | KPI online (agreement rate…) chỉ được diễn giải là proxy; kết luận "agent đạt/không đạt" chính thức phải dựa golden set + human review, nêu rõ trong dashboard |
| AC-5 | `duration_s` (gồm thời gian chờ user) và `active_duration_s` (giờ máy làm việc) phải tách bạch; so với manual dùng `active_duration_s` |

## 5. Yêu cầu tự động (AU)

| ID | Yêu cầu |
|---|---|
| AU-1 | Đường đi số liệu **không có bước thủ công**: terminal → extract (tự động, FR-8) → sync outbox (cron/script đồng bộ) → ingest + judge + dashboard (cron/CI trên máy tổng hợp) |
| AU-2 | Máy tổng hợp chạy chu kỳ đề xuất: ingest mỗi giờ; judge cho run mới ngay sau ingest; dashboard rebuild sau judge; publish (commit vào repo hoặc share nội bộ) |
| AU-3 | Mọi bước tự động phải an toàn khi chạy lại (idempotent) và an toàn khi offline (record chờ ở outbox, không mất) |
| AU-4 | Human review là bước ngoài đường số liệu: hàng đợi được sinh tự động (dashboard), kết quả human nạp lại qua `--load-scores` — không chặn pipeline tự động |

## 6. Quy trình vận hành bắt buộc

1. **Coverage audit (IN-1), tần suất tuần:** trên mỗi máy, so
   `ls /tmp/rca_state_*.json` (hoặc %TEMP%) với record đã nộp
   (khớp theo `run_id` tái tính từ state file). Lệch → tìm nguyên nhân
   (workflow không chạy extract? máy chưa sync?) và ghi nhận.
2. **Chấm mù agent-vs-manual:** người trung gian thay report bằng bản đã
   xoá metadata nguồn gốc (đường dẫn, chữ ký pipeline), đánh mã ngẫu nhiên;
   reviewer chấm theo rubric; giải mã sau khi chấm xong.
3. **Hiệu chuẩn judge (IN-5):** mỗi quý hoặc khi đổi model/prompt: lấy 10+
   run có điểm human, chạy judge, tính Spearman; < 0.6 → sửa rubric/prompt,
   chưa dùng điểm judge vào gate.
4. **Thay đổi skill pipeline:** bắt buộc chạy lại golden set (unassisted
   mode) + `eval_report.py --gate` trước khi merge; gate fail = không merge.

## 7. Tiêu chí nghiệm thu (test plan)

| # | Kiểm tra | Đạt khi |
|---|---|---|
| V1 | Extract trên state file `complete` mẫu | record hợp lệ theo schema, `outcome=complete`, có khối `integrity` với 2 hash |
| V2 | Extract trên state file chưa terminal | record `outcome=incomplete`, exit code 2 |
| V3 | Ingest cùng record 2 lần | `eval_runs` có đúng 1 dòng cho run_id |
| V4 | Ingest record thiếu trường bắt buộc / sai version | bị từ chối, đếm vào `skipped` |
| V5 | Amend 1 trường | giá trị đổi + 1 dòng mới trong `eval_amendments` |
| V6 | Amend trường ngoài whitelist | bị từ chối |
| V7 | Judge không API key | sinh prompt file tự đóng gói (chứa rubric + record + report), `--load-scores` nạp được điểm human |
| V8 | Điểm judge ngoài [1,5] hoặc dimension lạ | bị loại, không vào DB |
| V9 | `eval_report.py --gate` với dữ liệu dưới ngưỡng | exit 3, nêu tên gate fail |
| V10 | Re-extract từ cùng state file | các trường metric giống hệt record cũ; `state_sha256` khớp |
| V11 | Run abort | vẫn sinh record, vào hàng đợi human review |

## 8. Traceability

| Yêu cầu | File thực thi |
|---|---|
| FR-1/2/7, IN-2, AC-2/5 | `evaluation/scripts/eval_extract.py`, `schemas/eval_record.schema.json` |
| FR-3/6, IN-7, AU-3 | `evaluation/scripts/eval_ingest.py` |
| FR-4, IN-4 | `evaluation/scripts/eval_judge.py`, `.cline/skills/3gpp-rca-evaluator/references/evaluation-rubric.md` |
| FR-5, IN-8/9 | `evaluation/scripts/eval_report.py` |
| FR-8, IN-1 | `.clinerules/workflows/rca.md` (bước auto-extract), `.clinerules/workflows/rca-eval.md` |
| IN-3 | `.cline/skills/3gpp-rca-evaluator/SKILL.md` (HARD constraints) |
| IN-6, AC-1 | `evaluation/golden/README.md` |
| Quy trình 6.x | mục 6 spec này (vận hành, không code) |

---

*Thay đổi spec này phải qua PR review. Phiên bản spec tăng khi thêm/sửa
yêu cầu có ID; code implement phải cập nhật bảng traceability tương ứng.*
