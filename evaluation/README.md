# RCA Quality Evaluation System

Lớp đánh giá chất lượng read-only cho pipeline RCA v6, chạy tự động trên
fleet máy user **ClineSR (Samsung) + VS Code Windows, model Gauss**.

- **Tiêu chí chấm điểm (metric catalog M-xx/J-x, điểm tổng hợp RQS, gate):**
  [`criteria/rca-agent-scoring-criteria.md`](criteria/rca-agent-scoring-criteria.md)
- **Spec (yêu cầu bắt buộc + tiêu chí nghiệm thu, có ID trace):**
  [`rca-evaluation-spec.md`](rca-evaluation-spec.md)
- **Thiết kế nền (lý do, kiến trúc, KPI):**
  [`rca-evaluation-framework.md`](rca-evaluation-framework.md)
- **Cài đặt máy user ClineSR/Windows (4 tầng tự động + Gauss judge):**
  [`clinesr-windows-setup.md`](clinesr-windows-setup.md)

## Đường đi số liệu (không bước thủ công — spec AU-1)

```
Máy engineer (ClineSR/Gauss, Windows)
  /rca xong → auto extract + sweep ──┐   (4 tầng trigger: workflow, hook
  mở VS Code → folderOpen sweep ─────┤    ClineSR, tasks.json, Task Scheduler)
  Task Scheduler mỗi giờ → sweep ────┘
        │  .rca/eval/outbox/eval_<run>.json      (record ẩn danh)
        │  .rca/eval/scores/scores_<run>.json    (điểm judge Gauss/human)
        │  .rca/eval/coverage/coverage_*.json    (chứng cứ coverage 100%)
        ▼  sync (RCA_EVAL_SYNC_DIR: UNC share / git / S3)
Máy tổng hợp (cron/CI)
  eval_dashboard.py → dashboard.html + dashboard_data.json (+ --gate cho CI)
  (tuỳ chọn duckdb) eval_ingest.py / eval_judge.py / eval_report.py → SQL store
```

## Luồng lệnh nhanh

```bash
# Máy engineer — tự động, nhưng chạy tay được bất kỳ lúc nào:
python evaluation/scripts/eval_sweep.py --make-prompts      # extract bù + queue judge + sync
python evaluation/scripts/eval_score.py <record>            # RQS 0-100 của một run

# Chấm judge (phiên ClineSR MỚI — spec IN-4): /rca-eval judge-pending
# hoặc tự động nếu có Gauss gateway:
RCA_JUDGE_API_URL=https://<gauss-gw>/v1/chat/completions \
python evaluation/scripts/eval_judge.py --report <report> --record <record>

# Benchmark trên golden case:
python evaluation/scripts/eval_extract.py <state> \
    --golden evaluation/golden/cases/GC-001/case.json

# Máy tổng hợp — dashboard (stdlib-only, không cần duckdb):
python evaluation/scripts/eval_dashboard.py \
    --records <share>/outbox --scores <share>/scores --coverage <share>/coverage \
    --out dashboard.html --json dashboard_data.json --gate   # exit 3 nếu gate fail

# (tuỳ chọn) SQL store + amend hồi tố:
python evaluation/scripts/eval_ingest.py --db rca_eval.duckdb --outbox <outbox>
python evaluation/scripts/eval_ingest.py --db rca_eval.duckdb \
    --amend <run_id> --set rca_confirmed_by_fix=true
```

Hoặc dùng workflow `/rca-eval` (`.clinerules/workflows/rca-eval.md`) — các
mode: mặc định / `golden` / `judge` / `judge-pending` / `sweep` /
`dashboard` / `aggregate` / `amend`.

## Thành phần

| Đường dẫn | Vai trò |
|---|---|
| `criteria/rca-agent-scoring-criteria.md` | Tiêu chí chấm điểm chi tiết: metric M-xx/J-x, RQS, grade, gate |
| `rca-evaluation-spec.md` | Spec chính thức: FR/IN/AC/AU requirements, trust model, test plan, traceability |
| `rca-evaluation-framework.md` | Thiết kế đầy đủ: phase nào đo gì, so với manual, đo phân tán |
| `clinesr-windows-setup.md` | Cài đặt máy user ClineSR/Windows/Gauss (4 tầng tự động) |
| `schemas/eval_record.schema.json` | Schema eval record (JSON Schema 2020-12) |
| `scripts/eval_extract.py` | State file → eval record (stdlib-only) |
| `scripts/eval_sweep.py` | Coverage guarantor: quét máy, extract bù, queue judge, sync (stdlib-only) |
| `scripts/eval_score.py` | Record (+điểm judge) → scorecard RQS 0-100 (stdlib-only) |
| `scripts/eval_judge.py` | Judge rubric 6 chiều: Gauss gateway / Claude / agent-as-judge; điểm ra file |
| `scripts/eval_dashboard.py` | Records → dashboard.html tự chứa + dashboard_data.json + gate (stdlib-only) |
| `scripts/eval_ingest.py` | Outbox → DuckDB store, idempotent, `--amend` hồi tố (cần duckdb) |
| `scripts/eval_report.py` | DuckDB → dashboard markdown + KPI gates (cần duckdb) |
| `hooks/rca_eval_hook.py` | Entry point hook ClineSR (fire-and-forget, không bao giờ block task) |
| `../.vscode/tasks.json` | Task VS Code tự sweep khi mở workspace |
| `golden/` | Format + quy tắc xây golden case set |

Yêu cầu: Python ≥ 3.10. Máy user: **không cần dependency nào**.
Máy tổng hợp: `pip install duckdb` chỉ khi dùng SQL store (tuỳ chọn).
