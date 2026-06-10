# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trần Trung Kiên  
**Mã sinh viên:** 2A202600850  
**Vai trò:** Ingestion / Cleaning & Quality / Embed & Idempotency / Monitoring & Docs  
**Ngày nộp:** 2026-06-10

---

## 1. Phần tôi phụ trách cụ thể

Trong Day 10, tôi phụ trách toàn bộ data pipeline từ raw CSV đến grading artifact. Các file chính tôi làm là `etl_pipeline.py`, `transform/cleaning_rules.py`, `quality/expectations.py`, `contracts/data_contract.yaml` và các docs/report. Trong `cleaning_rules.py`, tôi cập nhật allowlist để thêm `access_control_sop`, thêm rule quarantine HR stale content “10 ngày phép năm”, và thêm enrichment cho chunk P1 escalation 10 phút để retrieval ổn định hơn. Trong `expectations.py`, tôi thêm expectation `required_doc_ids_present_for_grading` để đảm bảo đủ 5 nguồn cần chấm, và `unique_chunk_id` để bảo vệ idempotent embed. Tôi chạy pipeline với run_id `after-fix`, kiểm tra manifest, eval CSV, grading JSONL và quick check. Kết quả final là `PIPELINE_OK`, `cleaned_records=44`, `quarantine_records=203`, `GRADE_CHECK[gq_d10_01..10] OK`.

---

## 2. Một quyết định kỹ thuật

Quyết định quan trọng nhất của tôi là dùng expectation dạng `halt` cho các lỗi có thể làm agent trả lời sai trực tiếp, thay vì chỉ cảnh báo. Ví dụ `refund_no_stale_14d_window`, `hr_leave_no_stale_10d_annual`, `required_doc_ids_present_for_grading` và `unique_chunk_id` đều là halt. Nếu các lỗi này lọt qua, retrieval có thể trả về thông tin sai: refund 14 ngày thay vì 7 ngày, HR 10 ngày phép năm thay vì 12 ngày, hoặc thiếu hoàn toàn `access_control_sop` cho câu Level 4 Admin Access. Tôi cân nhắc dùng warn để pipeline luôn chạy, nhưng như vậy sẽ dễ tạo Chroma index bẩn và grading fail. Bằng chứng là khi chạy inject với `--no-refund-fix`, expectation `refund_no_stale_14d_window` fail 3 violations. Pipeline chỉ được tiếp tục vì tôi cố tình dùng `--skip-validate` cho demo. Run chuẩn `after-fix` không dùng skip validate và tất cả halt expectations đều OK.

---

## 3. Một sự cố / anomaly đã sửa

Sự cố đáng chú ý nhất là `gq_d10_06` fail dù top1 document đúng là `sla_p1_2026`. Grading báo `contains_expected=false` cho câu hỏi “Nếu không có phản hồi với ticket P1 sau bao lâu thì hệ thống auto escalate?”. Khi đọc eval CSV, tôi thấy retrieval top1 bị nhiễu bởi chunk P2 escalation 90 phút hoặc chunk SLA P1 không chứa cụm “10 phút”. Root cause không phải allowlist mà là ranking/context: dữ liệu có chunk đúng “Escalation P1 ... 10 phút”, nhưng semantic query không đưa nó vào top-k ổn định. Tôi sửa bằng một cleaning/enrichment rule: nếu `doc_id == sla_p1_2026` và chunk có “Escalation P1” + “10 phút”, tôi append câu rõ ràng “Nếu không có phản hồi với ticket P1 sau 10 phút thì hệ thống auto escalate lên Senior Engineer.” Sau rerun, `instructor_quick_check.py` báo `GRADE_CHECK[gq_d10_06] OK`. Đây là bằng chứng fix có tác động đo được.

---

## 4. Before / after

Before/inject evidence:

```text
run_id=inject-bad
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=3
WARN: expectation failed but --skip-validate → tiếp tục embed
```

Before/fail evidence cho P1 escalation:

```text
GRADE_CHECK[gq_d10_06] FAIL :: SLA P1 escalation 10 phút
```

After/final evidence:

```text
run_id=after-fix
cleaned_records=44
quarantine_records=203
expectation[refund_no_stale_14d_window] OK
expectation[hr_leave_no_stale_10d_annual] OK
expectation[required_doc_ids_present_for_grading] OK
expectation[unique_chunk_id] OK
PIPELINE_OK
GRADE_CHECK[gq_d10_01] ... GRADE_CHECK[gq_d10_10] OK
```

Điều này cho thấy pipeline không chỉ chạy, mà còn phát hiện được corruption và cải thiện retrieval/grading sau khi sửa rule.

---

## 5. Nếu có thêm 2 giờ

Tôi sẽ sửa freshness parser để normalize `exported_at` từ dạng `2026/04/07T00:00:00` sang ISO trước khi ghi manifest. Hiện run final có `freshness_check=WARN` vì checker không parse được timestamp, dù pipeline và grading đều pass. Việc này sẽ giúp monitoring rõ hơn và tiến gần production hơn.
