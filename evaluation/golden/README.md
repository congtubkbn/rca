# Golden Case Set — Benchmark chuẩn cho RCA Agent

Golden case = một bug UE **đã đóng, root cause đã được xác nhận bằng fix**,
đóng gói lại thành case benchmark chạy được nhiều lần.

## Cấu trúc một case

```
evaluation/golden/cases/<case_id>/
  case.json          # nhãn chuẩn (theo case_template.json)
  logs.duckdb        # snapshot DuckDB với UE_3gpp_signaling_log + UE_Trace_log
                     # (hoặc logs.duckdb.path trỏ tới share nội bộ nếu DB quá lớn)
  notes.md           # bối cảnh: bug ticket, ai fix, tại sao nhãn là chuẩn
```

`case.json` theo `case_template.json` cùng thư mục. Các trường nhãn:

- `engineer_description` — mô tả đầu vào VERBATIM sẽ đưa cho agent (và cho
  dev đối chứng). Không được chứa gợi ý root cause.
- `top_event` — top event chuẩn (để đo candidate recall ở Checkpoint A).
- `root_cause.root_cause_class` — một trong: VALUE_DISCREPANCY, ABSENCE,
  TIMER_EXPIRY, MULTI_CAUSE.
- `root_cause.implementation_location` — `file:function` chuẩn (đo L2/L3).
- `root_cause.function` — tên function (đo function_match).
- `causal_chain_summary` — tóm tắt chuỗi nhân quả chuẩn, dùng cho judge/human
  đối chiếu, không dùng để match tự động.
- `manual_baseline` — kết quả đối chứng dev thủ công (thời gian phút, đúng/sai
  theo L1/L2/L3, người chấm) — điền sau khi chạy đối chứng.

## Quy tắc xây set (để đánh giá nghiêm ngặt, không tự lừa mình)

1. **Tối thiểu 20 case**, phủ đủ 4 root_cause_class và các RAT/procedure
   chính (HO, RACH, attach, reestablishment...). Thiếu phủ = KPI vô nghĩa.
2. **Case mới không được dùng để chỉnh skill** trước khi vào set (tránh
   overfit): sửa skill dựa trên case nào thì case đó bị loại khỏi set chấm
   điểm chính thức, chuyển sang set dev.
3. Nhãn chuẩn phải được **xác nhận bằng fix đã hoạt động**, không phải "ý
   kiến của một dev".
4. Log snapshot phải **đóng băng** — mọi lần chạy benchmark dùng đúng cùng
   dữ liệu.
5. Chạy benchmark ở 2 chế độ và ghi riêng:
   - `assisted`: engineer thật thao tác checkpoint (đo hệ người+agent).
   - `unassisted`: auto-confirm mọi khuyến nghị của agent (đo agent trần).

## Chạy một case

```bash
# 1. Chạy pipeline /rca với engineer_description của case trên logs.duckdb
# 2. Khi phase = complete:
python evaluation/scripts/eval_extract.py /tmp/rca_state_<ts>.json \
    --golden evaluation/golden/cases/<case_id>/case.json
# 3. Ingest + judge + report như run thường
```
