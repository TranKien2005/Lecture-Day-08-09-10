# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repository contains the Day 08, Day 09, and Day 10 materials for the "AI in Action" course. The three days are a continuous case study for an internal CS + IT Helpdesk assistant:

- Day 08 builds a grounded RAG pipeline over policy/SLA/helpdesk documents.
- Day 09 refactors the Day 08 RAG artifact into a supervisor-worker multi-agent system with traceability and optional MCP-style tools.
- Day 10 adds the data pipeline and observability layer that cleans, validates, embeds, and monitors the knowledge base feeding retrieval.

Lecture slides are standalone HTML/PDF assets. Lab code is Python and is organized independently under each `dayXX/lab/` directory.

## Setup and commands

Run commands from the relevant lab directory unless noted otherwise. Each lab has its own `requirements.txt` and `.env.example`.

### Day 08 RAG lab

```powershell
cd day08/lab
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Common commands:

```powershell
python index.py        # preview preprocess/chunking; full Chroma indexing requires TODO embedding implementation
python rag_answer.py   # run sample RAG queries after retrieval + LLM TODOs are implemented
python eval.py         # run scorecard/A-B evaluation after the RAG pipeline is implemented
```

Day 08 can use either OpenAI or Gemini for generation and either OpenAI embeddings or Sentence Transformers for embeddings. Keep the embedding model used in `index.py` and `rag_answer.py` consistent.

### Day 09 multi-agent lab

```powershell
cd day09/lab
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Common commands:

```powershell
python graph.py                    # run sample supervisor-worker graph queries and save traces
python eval_trace.py               # run test questions, save traces, and produce an eval report
python eval_trace.py --analyze     # analyze existing traces in artifacts/traces
python eval_trace.py --compare     # compare Day 09 traces to Day 08 baseline placeholders/results
python eval_trace.py --grading     # run grading questions if data/grading_questions.json exists
```

There are no dedicated test files in the baseline. Worker-level smoke tests are done by importing each worker `run(state)` function directly, as shown in [day09/lab/README.md](day09/lab/README.md).

### Day 10 data pipeline lab

```powershell
cd day10/lab
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Common commands:

```powershell
python etl_pipeline.py run
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
python grading_run.py --out artifacts/eval/grading_run.jsonl
python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
python instructor_quick_check.py --manifest artifacts/manifests/manifest_<run-id>.json
```

Corruption/before-after demo command:

```powershell
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Day 10 uses `CHROMA_DB_PATH`, `CHROMA_COLLECTION`, `EMBEDDING_MODEL`, and `FRESHNESS_SLA_HOURS` from environment variables when present; otherwise it defaults to a local Chroma DB and `all-MiniLM-L6-v2`.

### Pytest

Day 09 and Day 10 list `pytest` as a dependency, but this repository currently does not include pytest test files. If tests are added later, run them from the relevant lab directory:

```powershell
pytest
pytest path\to\test_file.py
pytest path\to\test_file.py::test_name
```

## Architecture overview

### Cross-day data and artifact flow

The labs intentionally reuse the same domain corpus in `data/docs/`: refund policy, P1 SLA, access control SOP, IT helpdesk FAQ, and HR leave policy. The progression is:

1. Day 08 reads text documents, preprocesses/chunks them, embeds them into Chroma, retrieves relevant chunks, and generates grounded answers with citations.
2. Day 09 keeps the same assistant domain but splits responsibilities into an orchestrator plus workers. The supervisor records route decisions, workers append outputs to shared state, and trace artifacts explain each run.
3. Day 10 works below the agent layer. It ingests a dirty CSV export, cleans/quarantines rows, validates expectations, publishes a snapshot to Chroma, writes manifests/logs, and evaluates retrieval quality before/after data fixes.

### Day 08: RAG pipeline shape

Key files:

- [day08/lab/index.py](day08/lab/index.py): document preprocessing, section-aware chunking, embedding, Chroma storage, and index inspection helpers.
- [day08/lab/rag_answer.py](day08/lab/rag_answer.py): dense/sparse/hybrid retrieval hooks, optional reranking/query transformation, grounded prompt construction, LLM call, and final answer packaging.
- [day08/lab/eval.py](day08/lab/eval.py): scorecard runner for faithfulness, relevance, context recall, completeness, plus baseline-vs-variant comparison.

Important implementation relationship: `rag_answer.py` expects retrieval embeddings and Chroma collection details to match what `index.py` used. Sprint TODOs are intentionally left in place as student work; do not assume all pipeline steps are fully implemented.

### Day 09: supervisor-worker orchestration

Key files:

- [day09/lab/graph.py](day09/lab/graph.py): main entry point. Defines `AgentState`, `supervisor_node()`, `route_decision()`, placeholder HITL, worker wrapper nodes, `run_graph()`, and `save_trace()`.
- [day09/lab/workers/](day09/lab/workers/): worker modules for retrieval, policy/tool logic, and synthesis. They are meant to operate on and return the shared state dictionary.
- [day09/lab/contracts/worker_contracts.yaml](day09/lab/contracts/worker_contracts.yaml): expected worker I/O contracts.
- [day09/lab/mcp_server.py](day09/lab/mcp_server.py): mock MCP-style capability surface for Sprint 3.
- [day09/lab/eval_trace.py](day09/lab/eval_trace.py): runs batches, saves JSON traces, computes routing/confidence/latency/MCP/HITL/source metrics, and emits comparison reports.

The graph defaults to a plain Python orchestrator rather than LangGraph. The intended flow is `Supervisor → selected worker or HITL → retrieval if needed → synthesis → trace`. Preserve route reasons and `workers_called` updates when changing behavior because the evaluation/reporting code depends on trace fields.

### Day 10: data quality and observability pipeline

Key files:

- [day10/lab/etl_pipeline.py](day10/lab/etl_pipeline.py): CLI entry point for `run` and `freshness`; coordinates CSV load, cleaning, quarantine, expectations, Chroma upsert/prune, manifest creation, and freshness check.
- [day10/lab/transform/cleaning_rules.py](day10/lab/transform/cleaning_rules.py): row loading/writing plus cleaning/quarantine rules. This is the main Sprint 1-2 extension point.
- [day10/lab/quality/expectations.py](day10/lab/quality/expectations.py): expectation suite. A halt stops the pipeline unless `--skip-validate` is used for the intentional corruption demo.
- [day10/lab/monitoring/freshness_check.py](day10/lab/monitoring/freshness_check.py): manifest freshness status logic.
- [day10/lab/eval_retrieval.py](day10/lab/eval_retrieval.py): retrieval evaluation against `data/test_questions.json`, writing CSV evidence.
- [day10/lab/grading_run.py](day10/lab/grading_run.py): official grading retrieval run against `data/grading_questions.json`, writing JSONL evidence.

The Day 10 Chroma publish step is snapshot-like: it upserts by `chunk_id` and prunes IDs no longer present in the cleaned CSV so stale vectors do not remain retrievable. This behavior is important for grading because `hits_forbidden` checks all retrieved top-k content, not only the top result.

## Documentation and reports

Each lab includes docs/report templates that are part of the course deliverables. When modifying pipeline behavior, update the corresponding docs under that lab's `docs/` and `reports/` folders rather than only changing code.

- Day 08: architecture and tuning log.
- Day 09: system architecture, routing decisions, and single-vs-multi comparison.
- Day 10: pipeline architecture, data contract, runbook, quality report, and group/individual reports.

No Cursor rules or Copilot instruction files are present in this repository at the time this file was created.
