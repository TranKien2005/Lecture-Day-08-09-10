# Quality report — Lab Day 10

**run_id:** `after-fix`  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước / Inject | Sau / Clean | Ghi chú |
|--------|----------------|-------------|---------|
| raw_records | 247 | 247 | cùng raw CSV |
| cleaned_records | 44 | 44 | sau khi đã thêm access_control_sop và loại HR stale |
| quarantine_records | 203 | 203 | invalid/legacy/stale/duplicate rows |
| Expectation halt? | Có: `refund_no_stale_14d_window FAIL` khi inject | Không: tất cả halt expectations OK | inject dùng `--skip-validate` để demo |
| embed_upsert | 44 | 44 | collection `day10_kb` |
| grading checks | không dùng làm final | 10/10 OK | `artifacts/eval/grading_run.jsonl` |

---

## 2. Before / after retrieval

Artifact:

- Before/inject: `artifacts/eval/after_inject_bad.csv`
- After/clean: `artifacts/eval/after_fix_eval.csv`
- Grading final: `artifacts/eval/grading_run.jsonl`

**Câu hỏi then chốt:** refund window (`q_refund_window` / `gq_d10_01`)

**Trước/inject:** expectation phát hiện lỗi:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=3
WARN: expectation failed but --skip-validate → tiếp tục embed
```

**Sau:** grading pass:

```text
GRADE_CHECK[gq_d10_01] OK :: refund window 7 ngày + không forbidden 14 ngày
```

**Merit/Distinction — HR versioning (`gq_d10_09`):**

**Trước khi fix:** pipeline halt do còn 2 chunk HR stale:

```text
expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=2
```

**Sau khi fix:**

```text
expectation[hr_leave_no_stale_10d_annual] OK (halt) :: violations=0
GRADE_CHECK[gq_d10_09] OK :: HR 12 ngày phép năm + không stale 10 ngày
```

**Access control allowlist (`gq_d10_10`):**

Baseline allowlist thiếu `access_control_sop`. Sau khi thêm vào `ALLOWED_DOC_IDS` và contract:

```text
expectation[required_doc_ids_present_for_grading] OK (halt) :: missing_doc_ids=[]
GRADE_CHECK[gq_d10_10] OK :: access control Level 4 IT Manager + CISO
```

**P1 escalation retrieval (`gq_d10_06`):**

Trước khi enrichment rule, grading fail:

```text
GRADE_CHECK[gq_d10_06] FAIL :: SLA P1 escalation 10 phút
```

Sau khi enrich P1 escalation wording:

```text
GRADE_CHECK[gq_d10_06] OK :: SLA P1 escalation 10 phút
```

---

## 3. Freshness & monitor

Run final:

```text
freshness_check=WARN {"reason": "no_timestamp_in_manifest", ...}
```

Giải thích: manifest có `run_timestamp`, nhưng `latest_exported_at` trong raw dùng format `2026/04/07T00:00:00`, chưa chuẩn ISO nên freshness checker không parse thành timestamp hợp lệ. Với lab, đây là WARN monitor, không halt pipeline. Trong production cần normalize `exported_at` sang ISO trước khi ghi manifest hoặc sửa freshness checker đọc nhiều format.

---

## 4. Corruption inject (Sprint 3)

Kịch bản inject:

```powershell
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Mục tiêu: cố tình không sửa refund window 14 ngày và bỏ qua validation để chứng minh expectation phát hiện corruption.

Kết quả:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=3
WARN: expectation failed but --skip-validate → tiếp tục embed
```

Sau inject, nhóm chạy lại clean run `after-fix` để restore index sạch và grading 10/10 OK.

---

## 5. Hạn chế & việc chưa làm

- Freshness checker đang WARN do timestamp format; cần normalize `exported_at` trong manifest.
- Rule enrichment P1 escalation là string-based; có thể thay bằng rerank/BM25 hybrid nếu mở rộng retrieval.
- Chưa tích hợp Great Expectations thật; hiện dùng custom expectation suite.
