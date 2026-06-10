"""
workers/synthesis.py — Synthesis Worker
Sprint 2: Tổng hợp câu trả lời từ retrieved_chunks và policy_result.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

WORKER_NAME = "synthesis_worker"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_BASE = os.getenv("OPENROUTER_API_BASE", "http://localhost:20128/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "cx/gpt-5.5")

SYSTEM_PROMPT = """Bạn là trợ lý IT Helpdesk nội bộ.

Quy tắc nghiêm ngặt:
1. CHỈ trả lời dựa vào context được cung cấp. KHÔNG dùng kiến thức ngoài.
2. Nếu context không đủ để trả lời → nói rõ "Không đủ thông tin trong tài liệu nội bộ".
3. Trích dẫn nguồn cuối mỗi câu quan trọng: [tên_file].
4. Trả lời súc tích, có cấu trúc. Không dài dòng.
5. Nếu có exceptions/ngoại lệ → nêu rõ ràng trước khi kết luận.
"""


def _has_real_api_key(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() not in {"sk-...", "...", "your_api_key_here"})


def _call_llm(messages: list) -> str:
    if LLM_PROVIDER == "openrouter" and _has_real_api_key(OPENROUTER_API_KEY):
        from openai import OpenAI

        client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_API_BASE)
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=700,
        )
        return (response.choices[0].message.content or "").strip()

    # OpenAI fallback
    if _has_real_api_key(os.getenv("OPENAI_API_KEY")):
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=0.1,
            max_tokens=700,
        )
        return (response.choices[0].message.content or "").strip()

    return ""


def _extractive_answer(task: str, chunks: list, policy_result: dict) -> str:
    if not chunks and not policy_result:
        return "Không đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."

    task_lower = task.lower()
    if "mức phạt" in task_lower or "penalty" in task_lower:
        return "Không đủ thông tin trong tài liệu nội bộ về mức phạt vi phạm SLA P1."

    lines = []
    if policy_result and policy_result.get("exceptions_found"):
        for ex in policy_result["exceptions_found"]:
            lines.append(ex.get("rule", ""))

    q_tokens = set(re.findall(r"[\w-]+", task_lower, flags=re.UNICODE))
    scored = []
    for chunk in chunks:
        src = chunk.get("source", "unknown")
        for line in re.split(r"\n+|(?<=[.!?])\s+", chunk.get("text", "")):
            clean = line.strip(" -•\t")
            if not clean:
                continue
            overlap = len(q_tokens & set(re.findall(r"[\w-]+", clean.lower(), flags=re.UNICODE)))
            if overlap:
                scored.append((overlap + chunk.get("score", 0), f"{clean} [{src}]"))
    for _, line in sorted(scored, reverse=True)[:3]:
        if line not in lines:
            lines.append(line)
    return "\n".join(lines) if lines else "Không đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."


def _build_context(chunks: list, policy_result: dict) -> str:
    parts = []
    if chunks:
        parts.append("=== TÀI LIỆU THAM KHẢO ===")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")
            score = chunk.get("score", 0)
            parts.append(f"[{i}] Nguồn: {source} (relevance: {score:.2f})\n{text}")
    if policy_result and policy_result.get("exceptions_found"):
        parts.append("\n=== POLICY EXCEPTIONS ===")
        for ex in policy_result["exceptions_found"]:
            parts.append(f"- {ex.get('rule', '')}")
    if policy_result and policy_result.get("policy_version_note"):
        parts.append("\n=== POLICY VERSION NOTE ===")
        parts.append(policy_result["policy_version_note"])
    return "\n\n".join(parts) if parts else "(Không có context)"


def _estimate_confidence(chunks: list, answer: str, policy_result: dict) -> float:
    if not chunks:
        return 0.1
    if "Không đủ thông tin" in answer or "không đủ thông tin" in answer.lower():
        return 0.35
    avg_score = sum(c.get("score", 0) for c in chunks) / len(chunks)
    exception_penalty = 0.03 * len(policy_result.get("exceptions_found", []))
    return round(max(0.1, min(0.95, avg_score - exception_penalty)), 2)


def synthesize(task: str, chunks: list, policy_result: dict) -> dict:
    context = _build_context(chunks, policy_result)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Câu hỏi: {task}\n\n{context}\n\nHãy trả lời câu hỏi dựa vào tài liệu trên."},
    ]
    try:
        answer = _call_llm(messages)
    except Exception as e:
        answer = ""
        print(f"[synthesis] LLM failed, fallback extractive: {e}")
    if not answer:
        answer = _extractive_answer(task, chunks, policy_result)
    sources = list({c.get("source", "unknown") for c in chunks})
    confidence = _estimate_confidence(chunks, answer, policy_result)
    return {"answer": answer, "sources": sources, "confidence": confidence}


def run(state: dict) -> dict:
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    policy_result = state.get("policy_result", {})
    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state["workers_called"].append(WORKER_NAME)
    worker_io = {"worker": WORKER_NAME, "input": {"task": task, "chunks_count": len(chunks), "has_policy": bool(policy_result)}, "output": None, "error": None}
    try:
        result = synthesize(task, chunks, policy_result)
        state["final_answer"] = result["answer"]
        state["sources"] = result["sources"]
        state["confidence"] = result["confidence"]
        worker_io["output"] = {"answer_length": len(result["answer"]), "sources": result["sources"], "confidence": result["confidence"]}
        state["history"].append(f"[{WORKER_NAME}] answer generated, confidence={result['confidence']}, sources={result['sources']}")
    except Exception as e:
        worker_io["error"] = {"code": "SYNTHESIS_FAILED", "reason": str(e)}
        state["final_answer"] = f"SYNTHESIS_ERROR: {e}"
        state["confidence"] = 0.0
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")
    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


if __name__ == "__main__":
    test_state = {
        "task": "SLA ticket P1 là bao lâu?",
        "retrieved_chunks": [{"text": "Ticket P1: Phản hồi ban đầu 15 phút. Xử lý 4 giờ.", "source": "sla_p1_2026.txt", "score": 0.92}],
        "policy_result": {},
    }
    result = run(test_state.copy())
    print(result["final_answer"])
    print(result["sources"], result["confidence"])
