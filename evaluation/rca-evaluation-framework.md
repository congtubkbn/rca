# Khung Đánh Giá Chất Lượng RCA Agent (v6) — RCA Quality Evaluation Framework

> Mục tiêu: đánh giá **chặt chẽ, có thể tái lập** chất lượng và hiệu quả của
> agent RCA (pipeline v6) so với dev phân tích thủ công, đo được trên nhiều
> user / máy chạy phân tán, và tự động cập nhật kết quả đánh giá kèm lớp
> AI-review + human-review có kiểm soát.

---

## 1. Nền tảng: state file là bản ghi telemetry sẵn có

Pipeline v6 đã được thiết kế theo hướng **mọi thứ đi qua state file**
(`/tmp/rca_state_<ts>.json`). Điều này nghĩa là ta KHÔNG cần thêm
instrumentation vào từng skill — một run hoàn chỉnh đã tự ghi lại:

| Dữ liệu có sẵn trong state file | Dùng để đo |
|---|---|
| `meta.started_at / finished_at`, `*_at` từng phase/iteration | Thời gian từng phase, tổng thời gian → so với manual |
| `phase2_ecf.top_event_candidates[]` + `user_confirmation.selected_rank` | Độ chính xác xếp hạng top event (Checkpoint A) |
| `user_decisions[]` (agent_recommendation vs action, `overrode_recommendation`) | **Agreement rate** — tỷ lệ engineer đồng ý với khuyến nghị agent |
| `fta_iterations[]` (tree, pruned, base_events, rejected, open_items, termination_signals) | Chất lượng cây FTA, độ sâu, hiệu quả pruning |
| `phase3_root_cause_chain.final_root_cause` (`root_cause_class`, `implementation_location`) | Độ chính xác root cause so với golden label |
| `keyword_provenance_audit[]` (`verified`) | Tính nghiêm ngặt bằng chứng (anti-hallucination) |
| `high_disagreement_run`, `user_override_count` | Cờ định tuyến run vào hàng chờ review |
| `termination_reason`, phase = `complete` vs abort | Tỷ lệ hoàn thành / abort |

**Nguyên tắc thiết kế số 1:** evaluation là lớp *read-only* trên state file.
Không skill nào trong pipeline bị sửa hành vi vì evaluation; đánh giá không
được làm méo hành vi được đánh giá.

---

## 2. Đánh giá ở những phase / step nào

Đánh giá theo đúng ranh giới phase của pipeline — mỗi gate là một điểm đo:

### 2.1 Phase 1 — Scoping
- **Scope precision** (offline, cần golden): procedure / RAT / layer / time
  window đúng so với nhãn chuẩn của case.
- **Ambiguity rate**: tỷ lệ run bị halt vì `ambiguities` không rỗng — đo chất
  lượng khai thác mô tả engineer.
- **Halt-and-fix time**: thời gian từ halt Phase 1 đến khi user bổ sung.

### 2.2 Phase 2 + Checkpoint A — Top event
- **Rank-1 acceptance rate**: % run mà user confirm candidate rank 1
  (`selected_rank == 1`, không override). Đây là proxy trực tiếp cho chất
  lượng xếp hạng của agent.
- **Candidate recall@k** (offline): top event chuẩn của golden case có nằm
  trong danh sách candidates không.
- **Refine-loop count**: số lần user phải `refine:` trước khi confirm.

### 2.3 Mỗi FTA iteration (Phase 3.x)
- **Spec-anchored ratio**: tỷ lệ iteration có `spec_anchored=true` /
  `spec_skeleton_returned_empty=false` (fallback nhiều = bằng chứng yếu hơn).
- **Pruning quality** (offline): nhánh bị prune có chứa root cause chuẩn
  không (pruning sai = lỗi nghiêm trọng nhất của FTA).
- **Base-event yield**: `len(base_events)` vs `len(rejected)` vs
  `len(open_items)` — iteration "open" nhiều nghĩa là coverage log kém hoặc
  Gate query kém.
- **Iteration duration**: thời gian mỗi vòng.

### 2.4 Checkpoint B — chất lượng khuyến nghị
- **Recommendation agreement rate**: % quyết định user KHÔNG override. Đây là
  KPI online quan trọng nhất vì có ở *mọi* run thật, không cần golden label.
- **Override outcome**: khi user override, nhánh user chọn có dẫn đến terminal
  được accept không → override "đúng" hay "sai" (đo xem agent thua người ở
  đâu).
- **Termination-signal precision**: khi controller khuyến nghị
  `accept_terminal` do signals, user có đồng ý không.

### 2.5 Phase 4 — tính nghiêm ngặt
- **Provenance pass rate**: % keyword `verified=true`; run fail provenance
  audit là lỗi chất lượng hạng A.
- **Termination-boundary violations**: có chuỗi fix/remediation lọt vào báo
  cáo không (đã có validator trong finalize — đếm số lần nó bắt được).
- **Completeness failures**: các HALT ở bước finalize.

### 2.6 Kết quả cuối (chỉ đo được với golden hoặc hậu kiểm)
- **Root-cause accuracy**, đo phân tầng — nghiêm ngặt dần:
  - L1: đúng `root_cause_class` (VALUE_DISCREPANCY / ABSENCE / …)
  - L2: đúng file (`implementation_location` cùng file với nhãn)
  - L3: đúng function/mechanism (LLM-judge + human xác nhận)
- **Causal-chain validity**: chuỗi nhân quả qua các iteration có mắt xích nào
  không được cross-reference hậu thuẫn không (LLM-judge chấm theo rubric).
- **Downstream validation** (mạnh nhất, chậm nhất): fix được thiết kế từ root
  cause đó có thực sự sửa được lỗi không → `rca_confirmed_by_fix` ghi hồi tố
  vào eval DB.

---

## 3. So sánh với manual dev

Hai chế độ, bắt buộc làm cả hai:

### 3.1 Offline benchmark (golden set) — thước đo chuẩn
1. Xây **golden case set** từ các bug đã đóng có root cause đã biết
   (tối thiểu ~20 case, phủ đủ root_cause_class và RAT/procedure). Format ở
   `evaluation/golden/`. Mỗi case gồm: mô tả engineer + DuckDB log snapshot +
   nhãn chuẩn (top event, root cause class, file, function, causal chain tóm
   tắt).
2. Chạy agent trên từng case (engineer thao tác checkpoint như thật, hoặc
   auto-confirm rank 1 cho chế độ "unassisted").
3. Đối chứng manual: dev có kinh nghiệm tương đương phân tích cùng case, cùng
   log, tính giờ.
4. So sánh trên cùng thước đo:

| Chiều đo | Agent | Manual |
|---|---|---|
| Root-cause accuracy L1/L2/L3 | từ eval record | từ kết luận dev |
| Time-to-root-cause | `finished - started` (trừ thời gian chờ user ở checkpoint) | bấm giờ |
| Evidence completeness | provenance audit + judge | chấm rubric mù |
| Report quality | LLM-judge + human rubric 1–5, chấm **mù** (không biết nguồn) | như nhau |

   Chấm mù (blind grading) là bắt buộc: reviewer nhận report đã che nguồn
   gốc agent/người.

### 3.2 Online (production) — không cần golden
Trên các run thật, không có nhãn chuẩn, dùng các proxy:
- **Agreement rate** tại Checkpoint A/B (mục 2.2, 2.4) — nếu engineer là
  người giỏi, đồng ý cao ⇒ agent gần trình người.
- **Time-to-accepted-root-cause** so với baseline lịch sử của đội (MTTR-phân
  tích trước khi có agent).
- **Re-open rate**: % run mà root cause về sau bị chứng minh sai (fix không
  ăn, case mở lại) — ghi hồi tố qua `eval_ingest.py --amend`.
- **Abort rate** và phân bố `termination_reason`.

---

## 4. Đo trên nhiều user / máy chạy phân tán

Kiến trúc thu thập **pull-nhẹ, push-file**, không cần server:

```
Máy engineer A ──┐
  run xong → eval_extract.py → eval_record JSON (.rca/eval/outbox/)
Máy engineer B ──┤            (đã ẩn danh hoá user/máy bằng salted hash)
                 │
        đồng bộ outbox (git branch riêng / thư mục share / S3 / scp)
                 ▼
        Máy tổng hợp (hoặc CI):
        eval_ingest.py  → rca_eval.duckdb  (bảng eval_runs, eval_iterations,
                                            eval_decisions, eval_judge_scores)
        eval_judge.py   → chấm rubric bằng LLM cho run mới
        eval_report.py  → dashboard markdown / HTML, cập nhật định kỳ
```

Điểm thiết kế:
- **Eval record là JSON phẳng, nhỏ** (schema ở `evaluation/schemas/`), tách
  khỏi state file đầy đủ (state file có thể chứa log nhạy cảm — chỉ record
  tổng hợp rời máy).
- **Ẩn danh có kiểm soát**: `machine_id = sha256(hostname + salt)[:12]`,
  `user_id = sha256(username + salt)[:12]`. Salt chung của team để cùng một
  máy luôn ra cùng id (so sánh được theo máy) nhưng không lộ danh tính ra
  ngoài team.
- **Idempotent ingest**: `run_id` là khóa; ingest lại không nhân đôi. Máy
  offline vài ngày rồi sync bù vẫn đúng.
- **DuckDB làm eval store** — nhất quán với stack sẵn có (log đã ở DuckDB),
  query phân tích trực tiếp bằng SQL.

---

## 5. Tự động cập nhật + AI review khi các máy đang chạy

### 5.1 Tự động hoá theo 3 tầng
1. **Per-run (trên máy engineer)**: workflow `/rca-eval` (hoặc bước cuối của
   finalize) gọi `eval_extract.py` ngay khi phase = `complete`. Chi phí ~0,
   không network.
2. **Định kỳ (máy tổng hợp / CI cron, ví dụ mỗi giờ hoặc mỗi đêm)**:
   `eval_ingest.py` quét outbox → `eval_judge.py` chấm run mới →
   `eval_report.py` sinh lại dashboard, commit vào repo hoặc publish nội bộ.
3. **Hồi tố**: khi fix được xác nhận / case bị mở lại, chạy
   `eval_ingest.py --amend run_id --set rca_confirmed_by_fix=true|false`.

### 5.2 AI review (LLM-as-judge) — có kỷ luật
- `eval_judge.py` chấm mỗi run theo rubric 6 chiều
  (`.cline/skills/3gpp-rca-evaluator/references/evaluation-rubric.md`):
  scope quality, top-event quality, tree quality, evidence rigor,
  causal-chain coherence, report clarity — thang 1–5, kèm rationale.
- Judge chỉ được đọc **report + eval record**, không được truy vấn lại log —
  nó chấm tính nhất quán và độ chặt của lập luận, không "làm lại RCA".
- **Hiệu chuẩn judge**: định kỳ lấy ≥10 run đã có điểm human, đo tương quan
  judge-vs-human (Spearman). Judge lệch ⇒ sửa rubric/prompt trước khi tin
  điểm judge.

### 5.3 Human review — theo hàng đợi có ưu tiên
Không review 100%; review theo lấy mẫu có định hướng:
- **Bắt buộc review**: run có `high_disagreement_run=true`; run fail
  provenance; run có judge score ≤ 2 ở bất kỳ chiều nào; run abort.
- **Lấy mẫu ngẫu nhiên**: ~10% run còn lại để giữ baseline không thiên lệch.
- Kết quả human review ghi ngược vào `eval_judge_scores`
  (`judge_model='human'`) — cùng bảng, so sánh trực tiếp với judge.

---

## 6. KPI tổng hợp & ngưỡng chất lượng (gate)

| KPI | Định nghĩa | Ngưỡng đề xuất ban đầu |
|---|---|---|
| Agreement rate (Checkpoint B) | 1 − overrides/decisions | ≥ 0.7 |
| Rank-1 acceptance (Checkpoint A) | % run confirm rank 1 | ≥ 0.6 |
| Provenance pass rate | keyword verified / total | = 1.0 (bắt buộc) |
| Golden accuracy L1 / L2 | đúng class / đúng file | ≥ 0.8 / ≥ 0.6 |
| Time-to-RCA vs manual | median agent / median manual | ≤ 0.5 |
| Re-open rate | root cause bị bác hậu kiểm | ≤ 0.1 |
| Judge overall | trung bình 6 chiều | ≥ 3.5, không chiều nào < 3 |

Ngưỡng là **regression gate**: mỗi lần sửa skill/prompt của pipeline, chạy
lại golden set; KPI tụt dưới ngưỡng ⇒ không merge thay đổi skill. Đây là
phần "nghiêm ngặt" — chất lượng agent được kiểm soát như kiểm soát code.

---

## 7. Thành phần đã triển khai trong repo

| Đường dẫn | Vai trò |
|---|---|
| `evaluation/schemas/eval_record.schema.json` | Schema chuẩn của eval record |
| `evaluation/scripts/eval_extract.py` | State file → eval record (chạy trên máy engineer) |
| `evaluation/scripts/eval_ingest.py` | Outbox → DuckDB `rca_eval.duckdb`, idempotent, hỗ trợ `--amend` |
| `evaluation/scripts/eval_judge.py` | LLM-judge theo rubric (Claude API; không có key thì xuất prompt để agent/người chấm) |
| `evaluation/scripts/eval_report.py` | DuckDB → dashboard markdown (KPI, xu hướng, theo máy, hàng đợi review) |
| `evaluation/golden/` | Format + template golden case |
| `.cline/skills/3gpp-rca-evaluator/` | Skill chạy đánh giá sau khi pipeline complete |
| `.clinerules/workflows/rca-eval.md` | Workflow `/rca-eval` — entry point đánh giá |

## 8. Lộ trình triển khai đề xuất

1. **Tuần 1–2**: bật `eval_extract` sau mỗi run trên mọi máy (tầng 1) — bắt
   đầu tích lũy agreement rate / duration ngay, chưa cần golden.
2. **Tuần 2–4**: dựng golden set 20 case từ bug lịch sử; chạy benchmark agent
   + đối chứng manual lần đầu → baseline chính thức.
3. **Tuần 4+**: bật cron ingest + judge + dashboard; hiệu chuẩn judge với
   human trên 10 run; chốt ngưỡng gate ở mục 6 theo số liệu thực.
4. **Liên tục**: mọi thay đổi skill đi kèm chạy lại golden set; dashboard là
   nguồn sự thật về chất lượng agent.
