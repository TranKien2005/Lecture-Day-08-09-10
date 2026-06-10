# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Day 10 Data Pipeline Lab  
**Thành viên:**

| Tên | Vai trò (Day 10) | MSSV |
|-----|------------------|------|
| Trần Trung Kiên | Ingestion / Cleaning & Quality / Embed & Idempotency / Monitoring & Docs | 2A202600850 |

**Ngày nộp:** 2026-06-10  
**Repo:** https://github.com/TranKien2005/Lecture-Day-08-09-10.git

---

## 1. Pipeline tổng quan

Nguồn raw là `data/raw/policy_export_dirty.csv`, mô phỏng export dirty từ nhiều hệ thống nguồn cho knowledge base CS + IT Helpdesk. Pipeline chính nằm ở `etl_pipeline.py`: ingest raw CSV, clean/quarantine bằng `transform/cleaning_rules.py`, validate bằng `quality/expectations.py`, embed cleaned rows vào ChromaDB collection `day10_kb`, ghi manifest và chạy freshness check. Run chính là `after-fix`.

**Lệnh chạy một dòng:**

```powershell
python etl_pipeline.py run --run-id after-fix; python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv; python grading_run.py --out artifacts/eval/grading_run.jsonl; python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
```

Kết quả run final:

```text
raw_records=247
cleaned_records=44
quarantine_records=203
embed_upsert count=44 collection=day10_kb
PIPELINE_OK
GRADE_CHECK[gq_d10_01..10] OK
```

---

## 2. Cleaning & expectation

### 2a. Bảng metric_impact

| Rule / Expectation mới | Trước | Sau / khi inject | Chứng cứ |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| `access_control_sop` allowlist | thiếu source, gq_d10_10 có nguy cơ fail | `required_doc_ids_present_for_grading OK`, gq_d10_10 OK | `cleaning_rules.py`, `grading_run.jsonl` |
| `stale_hr_annual_leave_10d_content` | `hr_leave_no_stale_10d_annual FAIL :: violations=2` | `violations=0`, gq_d10_09 OK | pipeline log `after-fix` |
| P1 escalation enrichment | `gq_d10_06 FAIL` | `gq_d10_06 OK` | instructor check output |
| `required_doc_ids_present_for_grading` expectation | không kiểm đủ source grading | `missing_doc_ids=[]` | expectation log |
| `unique_chunk_id` expectation | chưa check duplicate ID | `duplicate_chunk_ids=0` | expectation log |

**Rule chính:**

- Quarantine unknown/invalid doc_id.
- Normalize effective_date sang `YYYY-MM-DD`.
- Quarantine HR stale effective_date trước 2026.
- Quarantine HR stale content “10 ngày phép năm”.
- Fix refund stale “14 ngày làm việc” thành “7 ngày làm việc”.
- Enrich P1 escalation text để retrieval câu “10 phút” ổn định.
- Deduplicate chunk text.

**Ví dụ expectation fail và cách xử lý:**

Trước khi sửa HR stale content:

```text
expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=2
PIPELINE_HALT
```

Sau khi thêm rule quarantine `stale_hr_annual_leave_10d_content`:

```text
expectation[hr_leave_no_stale_10d_annual] OK (halt) :: violations=0
```

---

## 3. Before / after ảnh hưởng retrieval hoặc agent

**Kịch bản inject:**

Nhóm cố tình chạy:

```powershell
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Kịch bản này bỏ fix refund window 14 ngày và vẫn embed dù expectation halt, để chứng minh expectation phát hiện corruption.

**Kết quả định lượng:**

Inject bad:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=3
WARN: expectation failed but --skip-validate → tiếp tục embed
```

Clean run `after-fix`:

```text
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
GRADE_CHECK[gq_d10_01] OK :: refund window 7 ngày + không forbidden 14 ngày
```

Các câu khó cũng pass sau fix:

```text
GRADE_CHECK[gq_d10_06] OK :: SLA P1 escalation 10 phút
GRADE_CHECK[gq_d10_09] OK :: HR 12 ngày phép năm + không stale 10 ngày
GRADE_CHECK[gq_d10_10] OK :: access control Level 4 IT Manager + CISO
```

---

## 4. Freshness & monitoring

Freshness run final trả về:

```text
freshness_check=WARN {"reason": "no_timestamp_in_manifest"}
```

Pipeline vẫn pass vì đây là monitor warning, không phải expectation halt. Nguyên nhân là `latest_exported_at` trong raw có format `2026/04/07T00:00:00`, chưa chuẩn ISO nên checker không parse được. Trong runbook, nhóm ghi rõ cần normalize `exported_at` hoặc mở rộng freshness parser nếu production.

---

## 5. Liên hệ Day 09

Day 10 publish collection riêng `day10_kb`, không ghi đè `day09_docs`. Về mặt kiến trúc, đây là tầng data-quality trước khi agent Day 09 retrieve. Nếu muốn tích hợp, chỉ cần đổi retrieval worker Day 09 sang collection `day10_kb` hoặc dùng output cleaned CSV làm nguồn canonical cho Chroma. Lợi ích là tránh stale refund/HR/access data đi vào multi-agent.

---

## 6. Rủi ro còn lại & việc chưa làm

- Freshness đang WARN do timestamp format, cần normalize `exported_at` trong manifest.
- Chưa dùng Great Expectations thật, mới dùng custom expectation suite.
- P1 escalation fix hiện là string enrichment, chưa phải reranker/hybrid retrieval.
- Nếu raw source format thay đổi, các string-based rules cần chuyển sang contract-driven validation.
