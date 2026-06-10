# Runbook — Lab Day 10

## Symptom

Agent/RAG trả lời sai do dữ liệu bẩn hoặc stale. Ví dụ:

- Refund window trả lời “14 ngày” thay vì “7 ngày làm việc”.
- HR annual leave trả lời “10 ngày phép năm” thay vì “12 ngày phép năm” cho chính sách HR 2026.
- P1 escalation retrieve nhầm P2 “90 phút” thay vì P1 “10 phút”.
- Grading có `contains_expected=false`, `hits_forbidden=true`, hoặc `top1_doc_matches=false`.

---

## Detection

Các tín hiệu cần kiểm tra:

1. Pipeline halt:
   ```text
   PIPELINE_HALT: expectation suite failed (halt)
   ```
2. Expectation fail:
   ```text
   expectation[refund_no_stale_14d_window] FAIL
   expectation[hr_leave_no_stale_10d_annual] FAIL
   ```
3. Eval/grading fail:
   ```text
   GRADE_CHECK[gq_d10_06] FAIL
   ```
4. Freshness warning:
   ```text
   freshness_check=WARN
   ```

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `artifacts/logs/run_<run-id>.log` | Thấy `raw_records`, `cleaned_records`, `quarantine_records`, expectation status |
| 2 | Mở `artifacts/quarantine/quarantine_<run-id>.csv` | Biết record bị loại vì `unknown_doc_id`, stale HR, duplicate, invalid date |
| 3 | Chạy `python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv` | Xem `contains_expected`, `hits_forbidden`, `top1_doc_expected` |
| 4 | Chạy `python grading_run.py --out artifacts/eval/grading_run.jsonl` | Xác nhận 10 grading questions |
| 5 | Chạy `python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl` | Tất cả `GRADE_CHECK[...] OK` |
| 6 | Mở manifest | Kiểm tra run_id, raw/clean/quarantine count và collection name |

---

## Mitigation

1. Nếu expectation halt do stale refund:
   - Bật lại refund fix, không dùng `--no-refund-fix` trong run chuẩn.
   - Chạy:
     ```powershell
     python etl_pipeline.py run --run-id after-fix
     ```

2. Nếu HR trả về 10 ngày phép năm:
   - Kiểm tra rule `stale_hr_annual_leave_10d_content` trong `cleaning_rules.py`.
   - Đảm bảo expectation `hr_leave_no_stale_10d_annual` pass.

3. Nếu missing `access_control_sop`:
   - Kiểm tra `ALLOWED_DOC_IDS` và `contracts/data_contract.yaml` đã có `access_control_sop`.
   - Expectation `required_doc_ids_present_for_grading` phải OK.

4. Nếu retrieval nhầm P1 escalation:
   - Kiểm tra enrichment rule cho `Escalation P1` trong `cleaning_rules.py`.
   - Rerun pipeline để prune old vectors:
     ```powershell
     python etl_pipeline.py run --run-id after-fix
     ```

5. Sau mọi inject demo, luôn restore clean index:
   ```powershell
   python etl_pipeline.py run --run-id after-fix
   python grading_run.py --out artifacts/eval/grading_run.jsonl
   ```

---

## Prevention

- Giữ expectation halt cho các lỗi có thể làm grading/agent trả lời sai: stale refund 14 ngày, HR 10 ngày phép năm, missing required doc_id, duplicate chunk_id.
- Không silently drop record; ghi quarantine reason để audit.
- Embed idempotent bằng `chunk_id` và prune vector cũ để tránh stale context còn trong Chroma.
- Chạy `instructor_quick_check.py` trước khi nộp.
- Theo dõi freshness manifest; `WARN` hiện do timestamp format chưa parse được, cần chuẩn hóa `exported_at` nếu triển khai production.

---

## Run chuẩn đã xác nhận

```powershell
python etl_pipeline.py run --run-id after-fix
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
python grading_run.py --out artifacts/eval/grading_run.jsonl
python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
```

Kết quả: `PIPELINE_OK`, `cleaned_records=44`, `quarantine_records=203`, `GRADE_CHECK[gq_d10_01..10] OK`.
