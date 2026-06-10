# Day 09 — Multi-Agent Orchestration

Day 09 refactor RAG Day 08 thành kiến trúc supervisor-worker. Hệ thống có supervisor để route câu hỏi, retrieval worker để lấy evidence, policy/tool worker để xử lý chính sách và MCP tools, synthesis worker để tổng hợp answer có citation, và trace để debug.

## 1. Cấu trúc thư mục

```text
day09/
├── lecture-09.html
└── lab/
    ├── graph.py                         # Supervisor orchestrator, main entrypoint
    ├── eval_trace.py                    # Batch run + trace analysis + grading JSONL
    ├── mcp_server.py                    # Mock MCP tools
    ├── requirements.txt
    ├── .env.example
    ├── workers/
    │   ├── retrieval.py                 # Build/query ChromaDB with 9router embeddings
    │   ├── policy_tool.py               # Policy exception detection + MCP calls
    │   └── synthesis.py                 # 9router LLM synthesis + fallback
    ├── contracts/
    │   └── worker_contracts.yaml
    ├── data/
    │   ├── docs/                        # 5 domain docs
    │   └── test_questions.json          # 15 public test questions
    ├── artifacts/
    │   ├── traces/                      # JSON traces per run
    │   └── eval_report.json
    ├── docs/
    │   ├── system_architecture.md
    │   ├── routing_decisions.md
    │   └── single_vs_multi_comparison.md
    └── reports/
        ├── group_report.md
        └── individual/
            └── tran_trung_kien.md
```

## 2. Cài đặt môi trường

```powershell
cd "day09/lab"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Cấu hình 9router local endpoint trong `.env`:

```env
LLM_PROVIDER=openrouter
EMBEDDING_PROVIDER=openrouter
OPENROUTER_API_BASE=http://localhost:20128/v1
OPENROUTER_MODEL=cx/gpt-5.5
OPENROUTER_EMBEDDING_MODEL=openrouter/openai/text-embedding-3-small

CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION=day09_docs
RETRIEVAL_TOP_K=3
MCP_SERVER_MODE=mock
TRACE_OUTPUT_DIR=./artifacts/traces
```

Đảm bảo 9router đang chạy ở `http://localhost:20128` trước khi chạy LLM/embedding qua API.

## 3. Các bước chạy chính

### Bước 1 — Smoke test graph

```powershell
python graph.py
```

Kết quả mong đợi:

- Supervisor route được ít nhất retrieval và policy tasks.
- Auto-build ChromaDB collection `day09_docs` nếu chưa có.
- Lưu trace vào `artifacts/traces/`.

### Bước 2 — Run 15 public test questions

```powershell
python eval_trace.py
```

Output:

```text
artifacts/traces/*.json
artifacts/eval_report.json
```

### Bước 3 — Analyze traces

```powershell
python eval_trace.py --analyze
```

### Bước 4 — Compare Day 08 vs Day 09

```powershell
python eval_trace.py --compare
```

### Bước 5 — Grading log khi có grading questions

Nếu có `data/grading_questions.json`:

```powershell
python eval_trace.py --grading
```

Output:

```text
artifacts/grading_run.jsonl
```

## 4. File kỹ thuật quan trọng

### `graph.py`

- `AgentState`: shared state cho toàn graph.
- `supervisor_node()`: rule-based routing.
- `route_decision()`: chọn worker tiếp theo.
- `human_review_node()`: HITL placeholder cho risk/unknown error.
- `run_graph()`: public API chạy một task.
- `save_trace()`: lưu JSON trace.

Routing hiện tại:

| Loại câu hỏi | Route |
|---|---|
| SLA, P1, ticket, VPN, remote, password | `retrieval_worker` |
| refund, hoàn tiền, access, contractor, admin | `policy_tool_worker` |
| unknown error `ERR-*` | `human_review` rồi retrieval |

### `workers/retrieval.py`

- Auto-build ChromaDB từ `data/docs`.
- Dùng 9router embedding model `openrouter/openai/text-embedding-3-small`.
- Trả về `retrieved_chunks`, `retrieved_sources`, `worker_io_logs`.

### `workers/policy_tool.py`

- Phát hiện exception:
  - Flash Sale
  - digital product/license/subscription
  - activated product
  - policy v3 temporal note
- Gọi MCP mock tools khi `needs_tool=True`.

### `workers/synthesis.py`

- Gọi 9router model `cx/gpt-5.5`.
- Prompt yêu cầu chỉ trả lời từ context.
- Fallback extractive nếu LLM lỗi.
- Tính confidence heuristic theo retrieval score/abstain.

### `mcp_server.py`

Mock tools:

- `search_kb(query, top_k)`
- `get_ticket_info(ticket_id)`
- `check_access_permission(access_level, requester_role, is_emergency)`
- `create_ticket(priority, title, description)`

## 5. Kết quả hiện tại

Sau khi chạy `python eval_trace.py` với 15 test questions:

| Metric | Value |
|---|---:|
| Total traces | 15 |
| retrieval_worker | 8/15 (53%) |
| policy_tool_worker | 7/15 (46%) |
| Avg confidence | 0.474 |
| Avg latency | 14,751 ms |
| MCP usage rate | 7/15 (46%) |
| HITL rate | 1/15 (6%) |

Ví dụ trace quan trọng:

- `q01`: SLA P1 → `retrieval_worker → synthesis_worker`.
- `q09`: `ERR-403-AUTH` → `human_review → retrieval_worker → synthesis_worker`, abstain đúng.
- `q15`: P1 + Level 2 temporary access → policy route + MCP.

## 6. Lệnh kiểm tra nhanh

```powershell
python -m py_compile graph.py mcp_server.py eval_trace.py workers/retrieval.py workers/policy_tool.py workers/synthesis.py
python graph.py
python eval_trace.py
python eval_trace.py --analyze
```
