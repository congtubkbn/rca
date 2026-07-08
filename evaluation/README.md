# RCA Quality Evaluation System

Lớp đánh giá chất lượng read-only cho pipeline RCA v6.

- **Spec (yêu cầu bắt buộc + tiêu chí nghiệm thu, có ID trace):**
  [`rca-evaluation-spec.md`](rca-evaluation-spec.md)
- **Thiết kế nền (lý do, kiến trúc, KPI):**
  [`rca-evaluation-framework.md`](rca-evaluation-framework.md)

## Luồng sử dụng nhanh

```bash
# Trên máy engineer — sau khi một run /rca đạt phase complete:
python evaluation/scripts/eval_extract.py /tmp/rca_state_<ts>.json
#   → .rca/eval/outbox/eval_<run_id>.json (đã ẩn danh, an toàn để sync)

# Run benchmark trên golden case:
python evaluation/scripts/eval_extract.py <state> \
    --golden evaluation/golden/cases/GC-001/case.json

# Trên máy tổng hợp (cron/CI, sau khi sync outbox từ các máy):
python evaluation/scripts/eval_ingest.py --db rca_eval.duckdb --outbox <outbox>
python evaluation/scripts/eval_judge.py  --db rca_eval.duckdb \
    --report <report.md> --record <eval_record.json>
python evaluation/scripts/eval_report.py --db rca_eval.duckdb \
    --out dashboard.md --gate    # exit 3 nếu KPI gate fail

# Ghi hồi tố khi fix xác nhận / case mở lại:
python evaluation/scripts/eval_ingest.py --db rca_eval.duckdb \
    --amend <run_id> --set rca_confirmed_by_fix=true
```

Hoặc dùng workflow `/rca-eval` (`.clinerules/workflows/rca-eval.md`) — entry
point tương tự `/rca`, gọi skill `3gpp-rca-evaluator`.

## Thành phần

| Đường dẫn | Vai trò |
|---|---|
| `rca-evaluation-spec.md` | Spec chính thức: FR/IN/AC/AU requirements, trust model, test plan, traceability |
| `rca-evaluation-framework.md` | Thiết kế đầy đủ: phase nào đo gì, so với manual, đo phân tán, tự động cập nhật, ngưỡng gate |
| `schemas/eval_record.schema.json` | Schema eval record (JSON Schema 2020-12) |
| `scripts/eval_extract.py` | State file → eval record (stdlib-only, chạy mọi máy) |
| `scripts/eval_ingest.py` | Outbox → DuckDB store, idempotent, `--amend` hồi tố |
| `scripts/eval_judge.py` | LLM-as-judge theo rubric 6 chiều (có/không API key) |
| `scripts/eval_report.py` | DuckDB → dashboard markdown + KPI gates |
| `golden/` | Format + quy tắc xây golden case set |

Yêu cầu: Python ≥ 3.10; `pip install duckdb` (chỉ máy tổng hợp;
`eval_extract.py` không cần dependency nào).
