# Bộ Tiêu Chí Chấm Điểm Agent RCA (v1.0) — RCA Agent Scoring Criteria

> **Trạng thái:** chuẩn chấm điểm chính thức, dùng chung cho mọi máy chạy
> ClineSR (Samsung, VS Code trên Windows, model Gauss).
> **Quan hệ tài liệu:** spec yêu cầu hệ thống ở `../rca-evaluation-spec.md`;
> thiết kế nền ở `../rca-evaluation-framework.md`. Tài liệu này định nghĩa
> **từng metric, công thức, trọng số, và điểm tổng hợp RQS** — mọi con số trên
> dashboard phải trace được về một ID trong tài liệu này.
> **Thực thi:** `scripts/eval_score.py` (tính RQS), `scripts/eval_dashboard.py`
> (KPI đội), `scripts/eval_judge.py` (điểm judge). Sửa tiêu chí = sửa file này
> + code tương ứng, qua PR review (chống gate drift, spec IN-8).

---

## 1. Chuẩn tham chiếu — đánh giá agent theo 5 trục chuẩn

Tiêu chí bám theo 5 trục đánh giá agent tiêu chuẩn, ánh xạ vào ngữ cảnh RCA:

| Trục chuẩn agent-eval | Trong hệ RCA | Nhóm metric |
|---|---|---|
| **Task success** — agent có hoàn thành đúng nhiệm vụ? | Root cause đúng (golden L1/L2/L3), run complete, không bị mở lại | M-50…M-53, M-01, M-60 |
| **Groundedness / faithfulness** — mọi khẳng định có bằng chứng? | Keyword provenance, spec/code anchoring, evidence rigor | M-40, M-30, J-4 |
| **Efficiency** — chi phí thời gian/bước hợp lý? | Duration, active duration, số iteration, refine loop | M-03, M-04, M-33, M-12 |
| **Human-agent agreement** — người vận hành có tin khuyến nghị? | Agreement rate Checkpoint B, rank-1 acceptance Checkpoint A | M-20, M-10 |
| **Safety / integrity** — số liệu trung thực, hành vi trong giới hạn | Coverage 100%, tamper-evidence hash, termination-boundary | M-70, M-71, spec IN-* |

## 2. Bốn lớp đo — dữ liệu lấy từ đâu

| Lớp | Khi nào có | Nguồn | Ai tính |
|---|---|---|---|
| **L-A Deterministic per-run** | mọi run, ngay khi terminal | state file → eval record | `eval_extract.py` (tự động, hook/sweep) |
| **L-B Judge (rubric 6 chiều)** | sau run, phiên ClineSR **mới** (Gauss) hoặc API | report + record | `eval_judge.py` + agent-as-judge |
| **L-C Golden benchmark** | run trên golden case | record + `golden/cases/*` | `eval_extract.py --golden` |
| **L-D Retrospective** | khi fix xác nhận / case mở lại | ticket hệ bug | `eval_ingest.py --amend` |

Máy user (ClineSR/Windows) chỉ cần L-A + L-B; L-C/L-D chạy trên máy tổng hợp.

## 3. Catalog metric — định nghĩa tất định

Quy ước: `direction` ↑ = càng cao càng tốt, ↓ = càng thấp càng tốt.
`per-run` = tính cho từng run; `fleet` = trung bình/tỷ lệ trên tập run
(dashboard). Mọi công thức chỉ dùng trường có trong
`schemas/eval_record.schema.json` — cùng record luôn cho cùng điểm (spec AC-2).

### 3.1 Nhóm hoàn thành & hiệu quả (Phase 0→4)

| ID | Metric | Công thức / nguồn | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-01 | completion_rate | `count(outcome=complete) / count(*)` | fleet | ↑ | ≥ 0.85 |
| M-02 | abort_rate | `count(outcome=aborted) / count(*)` | fleet | ↓ | ≤ 0.10 |
| M-03 | duration_min | `duration_s / 60` (gồm chờ user) | per-run | ↓ | median ≤ 60 |
| M-04 | active_duration_min | `active_duration_s / 60` (chỉ giờ máy) | per-run | ↓ | median ≤ 30 |
| M-05 | iterations_traversed | `final_root_cause.iterations_traversed` | per-run | — | 2–5 điển hình |

### 3.2 Nhóm Checkpoint A — chất lượng xếp hạng top event (Phase 2)

| ID | Metric | Công thức | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-10 | rank1_acceptance | `checkpoint_a.rank1_accepted` (per-run bool); fleet = tỷ lệ true | cả hai | ↑ | ≥ 0.60 (gate) |
| M-11 | selected_rank | `checkpoint_a.selected_rank` | per-run | ↓ | 1 |
| M-12 | refine_loops | số decision `action=refine` trước confirm (từ `decisions.log`) | per-run | ↓ | ≤ 1 |
| M-13 | candidate_recall (golden) | `golden.top_event_in_candidates` | per-run | ↑ | true |

### 3.3 Nhóm Checkpoint B — human-agent agreement (Phase 3.x)

| ID | Metric | Công thức | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-20 | agreement_rate | `1 − decisions.overrides / decisions.total` | cả hai | ↑ | ≥ 0.70 (gate) |
| M-21 | override_count | `decisions.overrides` | per-run | ↓ | 0–1 |
| M-22 | high_disagreement_rate | tỷ lệ run `high_disagreement_run=true` | fleet | ↓ | ≤ 0.15 |

### 3.4 Nhóm chất lượng cây FTA & bằng chứng (Phase 3.1–3.5)

Ký hiệu cho mỗi iteration i: `B_i = base_events_count`,
`R_i = rejected_count`, `O_i = open_items_count`.

| ID | Metric | Công thức | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-30 | spec_anchored_ratio | `count(iter.spec_anchored=true) / count(iter)` | per-run | ↑ | ≥ 0.8 |
| M-31 | fallback_rate | `count(iter.fallback_used≠null) / count(iter)` | per-run | ↓ | ≤ 0.2 |
| M-32 | base_event_yield | `Σ B_i / count(iter)` | per-run | ↑ | ≥ 1 |
| M-33 | open_item_ratio | `Σ O_i / Σ (B_i+R_i+O_i)` (0 nếu mẫu = 0) | per-run | ↓ | ≤ 0.3 |
| M-34 | iteration_duration_min | `iter.duration_s/60` từng vòng | per-run | ↓ | ≤ 15/vòng |

### 3.5 Nhóm groundedness — kỷ luật provenance (Phase 4)

| ID | Metric | Công thức | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-40 | provenance_pass_rate | `provenance.verified / provenance.total` | cả hai | ↑ | **= 1.0 (gate cứng, spec IN-9)** |

### 3.6 Nhóm task success — golden benchmark & hậu kiểm

| ID | Metric | Công thức | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-50 | golden_L1 (class) | `golden.class_match` | cả hai | ↑ | ≥ 0.80 (gate) |
| M-51 | golden_L2 (file) | `golden.file_match` | cả hai | ↑ | ≥ 0.60 (gate) |
| M-52 | golden_L3 (function) | `golden.function_match` (judge/human xác nhận) | cả hai | ↑ | ≥ 0.40 |
| M-53 | time_vs_manual | `median(active_duration agent) / median(manual)` | fleet | ↓ | ≤ 0.5 |
| M-60 | reopen_rate | tỷ lệ `amendments.reopened=true` trên run đã hậu kiểm | fleet | ↓ | ≤ 0.10 (gate) |
| M-61 | confirmed_by_fix_rate | tỷ lệ `rca_confirmed_by_fix=true` trên run đã hậu kiểm | fleet | ↑ | ≥ 0.70 |

### 3.7 Nhóm integrity — độ tin của chính số liệu

| ID | Metric | Công thức | Mức | Hướng | Mục tiêu |
|---|---|---|---|---|---|
| M-70 | coverage_rate | `records đã extract / state file terminal tìm thấy` (từ `eval_sweep.py`) | fleet/máy | ↑ | = 1.0 |
| M-71 | integrity_hash_present | record có `integrity.state_sha256` | per-run | ↑ | true |
| M-72 | judge_coverage | tỷ lệ run complete đã có điểm judge | fleet | ↑ | ≥ 0.9 |

### 3.8 Nhóm judge — rubric 6 chiều (thang 1–5)

Định nghĩa chi tiết + anchor điểm ở
`.cline/skills/3gpp-rca-evaluator/references/evaluation-rubric.md`.

| ID | Dimension | Đo cái gì |
|---|---|---|
| J-1 | scope_quality | Phase 1 scope chính xác, IS/IS-NOT có nghĩa |
| J-2 | top_event_quality | Candidate xếp hạng đúng, lý do loại có căn cứ |
| J-3 | tree_quality | Cây FTA well-formed, pruning có bằng chứng gate |
| J-4 | evidence_rigor | Mọi khẳng định trace được (log/spec/code) |
| J-5 | causal_chain_coherence | Chuỗi nhân quả liền mạch, terminal đúng nghĩa |
| J-6 | report_clarity | Kỹ sư ngoài cuộc đọc là hành động được |

Ràng buộc judge (spec IN-4/IN-5): chạy trong **phiên ClineSR mới** (không phải
phiên vừa chạy RCA — chống self-grading), chỉ đọc report + record, mỗi điểm
kèm rationale trích report. Bất kỳ chiều nào ≤ 2 → bắt buộc human review.

## 4. RQS — RCA Quality Score (0–100), điểm tổng hợp per-run

Điểm tổng hợp hiển thị trên dashboard cho từng run. Tính bởi
`eval_score.py::compute_scorecard(record, judge_scores)` — tất định, cùng
input luôn cho cùng điểm.

### 4.1 Thành phần & trọng số

| Thành phần | Nguồn | Công thức điểm thành phần (0–1) | Trọng số |
|---|---|---|---|
| C1 Completion | outcome | complete = 1; aborted/incomplete = 0 | 5 |
| C2 Provenance | M-40 | pass_rate (1.0 nếu không có keyword nào — không suy diễn) | 15 |
| C3 Top event | M-11 | rank 1 = 1.0; rank 2 = 0.6; rank 3 = 0.4; khác/restart = 0 | 10 |
| C4 Agreement | M-20 | agreement_rate | 15 |
| C5 Anchoring | M-30, M-31 | `0.7·spec_anchored_ratio + 0.3·(1−fallback_rate)` | 8 |
| C6 FTA efficiency | M-33 | `1 − open_item_ratio` | 7 |
| **Deterministic subtotal** | | | **60** |
| C7 Judge | J-1…J-6 | `mean(6 chiều) / 5` (thiếu chiều nào bỏ chiều đó khỏi mean) | 40 |
| **Tổng** | | | **100** |

### 4.2 Quy tắc thiếu dữ liệu & mũ giới hạn (cap)

1. **Thành phần null** (ví dụ run không có decision nào → C4 null): loại khỏi
   tổng và **chuẩn hoá lại trọng số** trên các thành phần còn lại, đánh dấu
   `components_missing` trong scorecard.
2. **Chưa có điểm judge**: RQS tính trên 60 điểm deterministic, chuẩn hoá về
   /100, gắn cờ `provisional=true` — dashboard hiển thị tách "provisional" và
   "final".
3. **Cap cứng:**
   - `provenance_pass_rate < 1.0` → RQS bị chặn trần **49** (grade F) — chuẩn
     groundedness không thoả thì mọi điểm khác vô nghĩa (spec IN-9).
   - `outcome = aborted` → không tính RQS (`rqs = null`), run vào hàng chờ
     human review.
   - Bất kỳ chiều judge ≤ 2 → chặn trần **69** (tối đa grade C) + bắt buộc
     human review.

### 4.3 Thang xếp loại

| Grade | RQS | Ý nghĩa vận hành |
|---|---|---|
| A | ≥ 85 | Chuẩn mực — dùng làm ví dụ đào tạo |
| B | 70–84 | Đạt, không cần can thiệp |
| C | 55–69 | Dùng được nhưng có khoảng trống — xem rationale judge |
| D | 40–54 | Yếu — bắt buộc human review |
| F | < 40 (hoặc dính cap provenance) | Không đạt — điều tra nguyên nhân |

## 5. Gate KPI cấp đội (fleet) — regression gate

Đồng bộ với `GATES` trong `eval_report.py` và `eval_dashboard.py` (spec IN-8:
đổi ngưỡng = đổi code = PR review):

| Gate | Metric | Ngưỡng |
|---|---|---|
| G-1 | M-20 agreement_rate | ≥ 0.70 |
| G-2 | M-10 rank1_acceptance | ≥ 0.60 |
| G-3 | M-40 provenance_pass | = 1.00 |
| G-4 | M-50 golden L1 | ≥ 0.80 |
| G-5 | M-51 golden L2 | ≥ 0.60 |
| G-6 | M-60 reopen_rate | ≤ 0.10 |
| G-7 | judge_overall (mean J-1…J-6, LLM) | ≥ 3.5 |
| G-8 | M-70 coverage_rate | = 1.00 |

Bất kỳ gate nào fail → `--gate` exit ≠ 0 → CI đỏ, thay đổi skill không được
merge (quy trình spec §6.4).

## 6. Quy tắc hàng chờ human review

Run vào hàng chờ khi **bất kỳ** điều nào đúng:
`high_disagreement_run` · `provenance < 1.0` · `outcome = aborted` ·
chiều judge ≤ 2 · RQS grade D/F · lấy mẫu ngẫu nhiên ~10% run còn lại.

## 7. Checklist "đủ thông tin để upload dashboard" (per-run)

Một run được coi là **upload-ready** khi outbox có đủ:

1. `eval_<run_id>.json` — record hợp lệ theo schema, có khối `integrity` với
   `state_sha256` (M-71);
2. `scores_<run_id>.json` — điểm judge 6 chiều (hoặc run nằm trong hàng chờ
   judge của sweep, sẽ được chấm ở phiên kế);
3. run xuất hiện trong `coverage_<machine>.json` mới nhất của `eval_sweep.py`
   với trạng thái `extracted`.

`eval_sweep.py` là cơ chế đảm bảo: quét mọi `rca_state_*.json` terminal trên
máy (kể cả run bị đóng task giữa chừng), extract phần còn thiếu, ghi báo cáo
coverage và (tuỳ chọn) copy sang thư mục sync. Không phụ thuộc model có nhớ
chạy bước extract hay không.

## 8. Traceability

| Nhóm tiêu chí | Thực thi |
|---|---|
| M-01…M-40 per-run + RQS (§4) | `scripts/eval_score.py` |
| Fleet KPI + gates (§5) + dashboard | `scripts/eval_dashboard.py`, `scripts/eval_report.py` |
| J-1…J-6 | `scripts/eval_judge.py` + rubric + `/rca-eval judge-pending` |
| M-70 coverage, checklist §7 | `scripts/eval_sweep.py` + hook/tasks ClineSR |
| M-50…M-61 | `eval_extract.py --golden`, `eval_ingest.py --amend` |
