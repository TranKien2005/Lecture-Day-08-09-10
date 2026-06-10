# Day 08 — RAG Pipeline

Day 08 triển khai pipeline RAG cho trợ lý nội bộ CS + IT Helpdesk. Mục tiêu là đọc tài liệu chính sách/SLA/FAQ/HR, chunk + embed vào ChromaDB, retrieve context đúng, sinh answer grounded có citation, và đánh giá baseline vs variant.

## 1. Cấu trúc thư mục

```text
day08/
├── lecture-08.html
└── lab/
    ├── index.py                  # Build Chroma index: preprocess -> chunk -> embed -> store
    ├── rag_answer.py             # Retrieve -> build grounded prompt -> call LLM/fallback -> answer
    ├── eval.py                   # Scorecard baseline vs hybrid variant + grading log generator
    ├── requirements.txt
    ├── .env.example
    ├── data/
    │   ├── docs/                 # 5 tài liệu nguồn
    │   └── test_questions.json   # 10 câu public test
    ├── docs/
    │   ├── architecture.md
    │   └── tuning-log.md
    ├── reports/
    │   ├── group_report.md
    │   └── individual/
    │       └── tran_trung_kien.md
    ├── results/                  # Generated scorecards
    └── logs/                     # Generated grading_run.json nếu có grading_questions.json
```

## 2. Cài đặt môi trường

Chạy trong PowerShell:

```powershell
cd "day08/lab"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu dùng 9router local endpoint, cấu hình `.env` như sau:

```env
LLM_PROVIDER=openrouter
EMBEDDING_PROVIDER=openrouter
OPENROUTER_API_BASE=http://localhost:20128/v1
OPENROUTER_MODEL=cx/gpt-5.5
OPENROUTER_EMBEDDING_MODEL=openrouter/openai/text-embedding-3-small
```

Nếu không dùng API, có thể dùng local fallback:

```env
EMBEDDING_PROVIDER=local
LLM_PROVIDER=extractive
```

## 3. Các bước chạy chính

### Bước 1 — Build index

```powershell
python index.py
```

Kết quả mong đợi:

- Đọc đủ 5 tài liệu trong `data/docs/`
- Tạo ChromaDB collection `rag_lab`
- In metadata coverage và sample chunks

### Bước 2 — Test RAG answer

```powershell
python rag_answer.py
```

Script chạy các câu mẫu:

- SLA P1 xử lý bao lâu?
- Refund trong bao nhiêu ngày?
- Level 3 cần ai phê duyệt?
- ERR-403-AUTH có trong docs không?

### Bước 3 — Evaluation

```powershell
python eval.py
```

Output:

```text
results/scorecard_baseline.md
results/scorecard_variant.md
results/ab_comparison.csv
```

Nếu có `data/grading_questions.json`, `eval.py` cũng tạo:

```text
logs/grading_run.json
```

## 4. File kỹ thuật quan trọng

### `index.py`

- `preprocess_document()`: parse metadata header (`source`, `department`, `effective_date`, `access`).
- `chunk_document()`: tách theo heading `=== ... ===`.
- `get_embedding()`: hỗ trợ OpenAI, OpenRouter/9router, hoặc SentenceTransformers local.
- `build_index()`: rebuild collection `rag_lab`, embed và upsert chunks.

### `rag_answer.py`

- `retrieve_dense()`: query ChromaDB bằng embedding cùng model khi index.
- `retrieve_sparse()`: BM25 keyword retrieval.
- `retrieve_hybrid()`: kết hợp dense + sparse bằng Reciprocal Rank Fusion.
- `call_llm()`: hỗ trợ OpenAI, Gemini, OpenRouter/9router.
- `extractive_answer()`: fallback local để tránh hallucination khi không có API.

### `eval.py`

- Baseline: `retrieval_mode="dense"`.
- Variant: `retrieval_mode="hybrid"`.
- Tạo scorecard và A/B comparison.
- Tạo grading log nếu file grading tồn tại.

## 5. Kết quả hiện tại

Kết quả public test sau khi chạy thật:

| Metric | Baseline Dense | Variant Hybrid |
|---|---:|---:|
| Faithfulness | 4.50/5 | 4.40/5 |
| Relevance | 5.00/5 | 4.80/5 |
| Context Recall | 5.00/5 | 5.00/5 |
| Completeness | 3.70/5 | 4.30/5 |

Variant hybrid được chọn vì cải thiện completeness, đặc biệt ở các câu có điều kiện/keyword.

## 6. Lệnh kiểm tra nhanh

```powershell
python -m py_compile index.py rag_answer.py eval.py
python index.py
python rag_answer.py
python eval.py
```
