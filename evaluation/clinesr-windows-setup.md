# Cài đặt hệ đánh giá RCA cho ClineSR (Samsung) — VS Code trên Windows

> Đối tượng: máy engineer chạy **ClineSR extension** (fork Cline của Samsung)
> trong **VS Code trên Windows**, model **Gauss**. Mục tiêu: sau **mỗi** lần
> chạy `/rca`, máy tự động có đủ record + điểm judge + báo cáo coverage trong
> outbox để upload lên dashboard — **không có bước thủ công nào** (spec AU-1).

---

## 0. Yêu cầu

- Python ≥ 3.10 trong PATH (`python --version`; nếu chỉ có launcher, thay
  `python` bằng `py -3` ở mọi lệnh/tasks bên dưới).
- Máy user **không cần** cài package nào (mọi script phía user là
  stdlib-only). Chỉ máy tổng hợp cần `pip install duckdb` (tuỳ chọn).
- Workspace là bản clone repo này, mở trong VS Code.

## 1. Biến môi trường (đặt 1 lần, System/User Environment Variables)

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `RCA_EVAL_SALT` | **Có** | Salt ẩn danh **chung của team** — cùng salt thì cùng máy luôn ra cùng `machine_id`. Ví dụ: `rca-team-modem-2026` |
| `RCA_EVAL_SYNC_DIR` | Nên | Thư mục sync tới máy tổng hợp. UNC path dùng được: `\\fileserver\rca-eval` (hoặc thư mục OneDrive/NAS được mount) |
| `RCA_STATE_DIRS` | Không | Thư mục chứa state file ngoài `%TEMP%`, phân tách bằng `;` |
| `RCA_JUDGE_API_URL` | Không | Endpoint Gauss OpenAI-compatible (`.../v1/chat/completions`) nếu team có gateway — bật judge tự động hoàn toàn |
| `RCA_JUDGE_API_KEY` / `RCA_JUDGE_MODEL` | Không | Key + tên model cho endpoint trên (mặc định model: `gauss`) |

Lưu ý Windows: state file nằm ở `%TEMP%\rca_state_*.json` (pipeline ghi
"platform equivalent" của `/tmp`) — `eval_sweep.py` mặc định quét đúng
`%TEMP%` qua `tempfile.gettempdir()`, không cần cấu hình gì thêm.

## 2. Bốn tầng tự động — bật càng nhiều càng tốt (chạy trùng vô hại)

Mọi tầng đều gọi về cùng một lệnh idempotent:
`python evaluation\scripts\eval_sweep.py --make-prompts --quiet`

### Tầng 1 — Workflow `/rca` (có sẵn, không cần cài)
Bước cuối của workflow `/rca` tự chạy extract + sweep khi run đạt
`complete`/abort (spec FR-8). Đây là tầng chính nhưng **không được là tầng
duy nhất** — nếu user đóng task ClineSR giữa chừng thì tầng này không chạy.

### Tầng 2 — Hook ClineSR (nếu bản ClineSR của bạn hỗ trợ Hooks)
Nếu ClineSR build của bạn kế thừa tính năng **Hooks** của Cline upstream
(kiểm tra: Settings → Features → Hooks, hoặc tài liệu nội bộ ClineSR):

- Gắn hook ở sự kiện *sau khi task kết thúc* (tên sự kiện tuỳ bản build,
  thường là `TaskCompleted`/`TaskCancelled` hoặc tương đương), command:
  ```
  python <workspace>\evaluation\hooks\rca_eval_hook.py
  ```
- Hook wrapper này **không bao giờ** fail/block task (nuốt mọi lỗi, exit 0,
  log về `.rca\eval\hook.log`).
- Nếu bản ClineSR không có Hooks → bỏ qua tầng này, tầng 3+4 đã đủ đảm bảo.

### Tầng 3 — VS Code task tự chạy khi mở workspace (khuyến nghị, luôn làm)
Đã có sẵn `.vscode/tasks.json` trong repo với task
**"RCA eval sweep (auto on folder open)"** (`"runOn": "folderOpen"`).
Lần đầu mở workspace, VS Code hỏi *"Allow automatic tasks?"* → chọn
**Allow**. Từ đó mỗi lần mở VS Code, mọi run tồn đọng (kể cả run bị bỏ dở
>24h) được extract bù.

### Tầng 4 — Windows Task Scheduler (chốt chặn cuối, mỗi giờ)
Chạy 1 lần trong PowerShell/CMD (sửa đường dẫn workspace):

```bat
schtasks /Create /TN "RCA-Eval-Sweep" /SC HOURLY ^
  /TR "python C:\work\rca\evaluation\scripts\eval_sweep.py --make-prompts --quiet" ^
  /ST 09:00 /F
```

Với 4 tầng này, coverage M-70 = 100% không phụ thuộc việc model Gauss có
"nhớ" chạy bước extract hay user có mở VS Code đúng lúc hay không.

## 3. Chấm điểm judge trên Gauss (rubric 6 chiều J-1…J-6)

Hai đường, chọn theo hạ tầng:

**A. Có Gauss gateway (OpenAI-compatible):** đặt `RCA_JUDGE_API_URL`
(+key/model). `eval_judge.py` sẽ gọi thẳng Gauss và ghi
`scores_<run_id>.json` vào `.rca\eval\scores\` — tự động hoàn toàn, có thể
gọi ngay trong sweep định kỳ của máy tổng hợp.

**B. Không có gateway — agent-as-judge trong ClineSR (mặc định):**
1. `eval_sweep.py --make-prompts` đã tạo sẵn prompt tự đóng gói tại
   `.rca\eval\scores\pending_prompts\judge_prompt_<run_id>.md` cho mọi run
   chưa có điểm.
2. Mở một **task ClineSR MỚI** (bắt buộc — phiên mới, không phải phiên vừa
   chạy RCA, chống self-grading, spec IN-4) và gõ: `/rca-eval judge-pending`.
3. Agent (Gauss) đọc từng prompt, chấm đúng format JSON của rubric, lưu qua
   `eval_judge.py --load-scores` với `judge_model` = tên model Gauss đang
   dùng. Điểm nằm ở `.rca\eval\scores\scores_<run_id>.json`.

## 4. Dữ liệu rời máy & upload dashboard

Chỉ 3 loại file JSON ẩn danh rời máy (không log thô, không tên người/máy —
spec FR-2):

```
.rca\eval\outbox\eval_<run_id>.json        ← record đo lường
.rca\eval\scores\scores_<run_id>.json      ← điểm judge 6 chiều
.rca\eval\coverage\coverage_<machine>_<ts>.json ← chứng cứ coverage
```

`eval_sweep.py` tự copy 3 loại này sang `RCA_EVAL_SYNC_DIR` (copy-if-absent,
re-sync an toàn). Trên **máy tổng hợp** (hoặc CI, cron mỗi giờ):

```bat
python evaluation\scripts\eval_dashboard.py ^
  --records \\fileserver\rca-eval\outbox ^
  --scores  \\fileserver\rca-eval\scores ^
  --coverage \\fileserver\rca-eval\coverage ^
  --out dashboard.html --json dashboard_data.json --gate
```

- `dashboard.html` — dashboard tự chứa (mở bằng browser/publish nội bộ),
  hiển thị đủ KPI M-xx, RQS, gate, trend, per-machine, hàng chờ review.
- `dashboard_data.json` — payload máy-đọc-được để đẩy lên hệ dashboard
  khác (Grafana/web nội bộ) nếu cần.
- `--gate` exit 3 khi gate fail → dùng làm regression gate trong CI.
- (Tuỳ chọn, cần duckdb) `eval_ingest.py`/`eval_report.py` vẫn dùng được
  song song cho truy vấn SQL — nguồn số liệu là cùng các file record.

## 5. Checklist nghiệm thu sau khi cài (mỗi máy user)

1. Chạy tay `python evaluation\scripts\eval_sweep.py` → in
   `coverage 100%`, file `coverage_latest.json` xuất hiện.
2. Chạy một `/rca` đến complete → `outbox\eval_*.json` tự xuất hiện,
   không cần gõ thêm lệnh nào.
3. Đóng VS Code giữa một run khác → mở lại VS Code → sweep folderOpen
   extract bù (kiểm tra `coverage_latest.json` mới).
4. `/rca-eval judge-pending` trong task mới → `scores_*.json` xuất hiện.
5. Kiểm tra `RCA_EVAL_SYNC_DIR` có đủ 3 loại file.
6. Trên máy tổng hợp: dashboard build được, machine_id của máy mới xuất
   hiện ở bảng Per-machine với Coverage = 100%.
