# Day 10 — Data Pipeline & Data Observability

Day 10 xây tầng data pipeline trước khi dữ liệu đi vào RAG/agent. Pipeline ingest raw CSV dirty, clean/quarantine, validate expectations, embed cleaned snapshot vào ChromaDB, ghi manifest, kiểm tra freshness và chạy retrieval/grading evidence.

## 1. Cấu trúc thư mục

```text
day10/
├── Day 10 Data Pipeline and Data Observability.pdf
├── INSTRUCTOR_GUIDE_DAY10.md
└── lab/
    ├── etl_pipeline.py                  # Main CLI: run / freshness
    ├── eval_retrieval.py                # Retrieval eval public questions -> CSV
    ├── grading_run.py                   # Official grading -> JSONL
    ├── instructor_quick_check.py        # Sanity check grading/manifest
    ├── requirements.txt
    ├── transform/
    │   └── cleaning_rules.py            # Cleaning, quarantine, chunk_id
    ├── quality/
    │   └── expectations.py              # Halt/warn expectation suite
    ├── monitoring/
    │   └── freshness_check.py           # Manifest freshness check
    ├── contracts/
    │   └── data_contract.yaml
    ├── data/
    │   ├── raw/policy_export_dirty.csv  # Dirty source export
    │   ├── test_questions.json          # 21 public retrieval questions
    │   └── grading_questions.json       # 10 grading questions
    ├── artifacts/
    │   ├── cleaned/
    │   ├── quarantine/
    │   ├── manifests/
    │   ├── logs/
    │   └── eval/
    ├── docs/
    │   ├── pipeline_architecture.md
    │   ├── data_contract.md
    │   ├── runbook.md
    │   └── quality_report_template.md
    └── reports/
        ├── group_report.md
        └── individual/
            └── tran_trung_kien.md
```

## 2. Cài đặt môi trường

```powershell
cd "day10/lab"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Pipeline dùng local SentenceTransformers embedding mặc định:

```env
CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION=day10_kb
EMBEDDING_MODEL=all-MiniLM-L6-v2
FRESHNESS_SLA_HOURS=24
```

Nếu không có `.env`, code vẫn dùng default tương ứng.

## 3. Các bước chạy chính

### Bước 1 — Chạy pipeline clean

```powershell
python etl_pipeline.py run --run-id after-fix
```

Output chính:

```text
artifacts/cleaned/cleaned_after-fix.csv
artifacts/quarantine/quarantine_after-fix.csv
artifacts/manifests/manifest_after-fix.json
artifacts/logs/run_after-fix.log
```

### Bước 2 — Eval retrieval public questions

```powershell
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

### Bước 3 — Grading chính thức

```powershell
python grading_run.py --out artifacts/eval/grading_run.jsonl
python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
```

### Bước 4 — Check manifest/freshness

```powershell
python instructor_quick_check.py --manifest artifacts/manifests/manifest_after-fix.json
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_after-fix.json
```

### Bước 5 — Inject corruption để có before/after evidence

```powershell
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Sau inject, luôn restore clean index:

```powershell
python etl_pipeline.py run --run-id after-fix
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

## 4. File kỹ thuật quan trọng

### `etl_pipeline.py`

CLI chính:

- `python etl_pipeline.py run`
- `python etl_pipeline.py freshness --manifest ...`

Luồng xử lý:

```text
load raw CSV -> clean_rows -> write cleaned/quarantine -> expectations -> embed -> manifest -> freshness
```

### `transform/cleaning_rules.py`

Các rule chính:

- Allowlist doc_id hợp lệ, gồm `access_control_sop`.
- Normalize effective date sang ISO.
- Quarantine missing/invalid dates.
- Quarantine HR stale effective date.
- Quarantine HR stale annual leave “10 ngày phép năm”.
- Fix refund stale “14 ngày làm việc” thành “7 ngày làm việc”.
- Enrich P1 escalation 10 phút để retrieval ổn định.
- Deduplicate chunk text.

### `quality/expectations.py`

Expectations:

- `min_one_row` — halt
- `no_empty_doc_id` — halt
- `refund_no_stale_14d_window` — halt
- `chunk_min_length_8` — warn
- `effective_date_iso_yyyy_mm_dd` — halt
- `hr_leave_no_stale_10d_annual` — halt
- `required_doc_ids_present_for_grading` — halt
- `unique_chunk_id` — halt

### `grading_run.py`

Chạy 10 grading questions, ghi JSONL:

```text
artifacts/eval/grading_run.jsonl
```

Mỗi dòng ghi:

- `id`
- `question`
- `top1_doc_id`
- `contains_expected`
- `hits_forbidden`
- `top1_doc_matches`
- `top_k_used`

## 5. Kết quả hiện tại

Run chính:

```text
run_id=after-fix
raw_records=247
cleaned_records=44
quarantine_records=203
embed_upsert count=44
collection=day10_kb
PIPELINE_OK
```

Grading final:

```text
GRADE_CHECK[gq_d10_01] OK
GRADE_CHECK[gq_d10_02] OK
GRADE_CHECK[gq_d10_03] OK
GRADE_CHECK[gq_d10_04] OK
GRADE_CHECK[gq_d10_05] OK
GRADE_CHECK[gq_d10_06] OK
GRADE_CHECK[gq_d10_07] OK
GRADE_CHECK[gq_d10_08] OK
GRADE_CHECK[gq_d10_09] OK
GRADE_CHECK[gq_d10_10] OK
```

Important fixes:

- Added `access_control_sop` to allowlist and contract for `gq_d10_10`.
- Quarantined HR stale `10 ngày phép năm` for `gq_d10_09`.
- Enriched P1 escalation 10-minute wording for `gq_d10_06`.
- Inject bad run proves `refund_no_stale_14d_window` catches stale 14-day refund data.

## 6. Lệnh kiểm tra nhanh

```powershell
python -m py_compile etl_pipeline.py eval_retrieval.py grading_run.py instructor_quick_check.py transform/cleaning_rules.py quality/expectations.py monitoring/freshness_check.py
python etl_pipeline.py run --run-id after-fix
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
python grading_run.py --out artifacts/eval/grading_run.jsonl
python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
```
