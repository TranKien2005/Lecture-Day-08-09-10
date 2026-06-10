"""
workers/retrieval.py — Retrieval Worker
Sprint 2: Retrieve evidence chunks from ChromaDB.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

WORKER_NAME = "retrieval_worker"
DEFAULT_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "3"))
ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "data" / "docs"
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "day09_docs")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openrouter").lower()
OPENROUTER_API_BASE = os.getenv("OPENROUTER_API_BASE", "http://localhost:20128/v1")
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openrouter/openai/text-embedding-3-small")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

_local_model = None


def _has_real_api_key(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() not in {"sk-...", "...", "your_api_key_here"})


def _get_embedding(text: str) -> List[float]:
    global _local_model

    if EMBEDDING_PROVIDER == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if _has_real_api_key(api_key):
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=OPENROUTER_API_BASE)
            response = client.embeddings.create(
                model=OPENROUTER_EMBEDDING_MODEL,
                input=text,
            )
            return response.data[0].embedding

    if EMBEDDING_PROVIDER == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if _has_real_api_key(api_key):
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            response = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=text)
            return response.data[0].embedding

    from sentence_transformers import SentenceTransformer

    if _local_model is None:
        print(f"[retrieval] Loading local embedding model: {LOCAL_EMBEDDING_MODEL}")
        _local_model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)
    return _local_model.encode(text).tolist()


def _parse_doc(raw: str, fallback_source: str) -> tuple[str, Dict[str, str]]:
    metadata = {
        "source": fallback_source,
        "department": "unknown",
        "effective_date": "unknown",
        "access": "internal",
    }
    content_lines = []
    header_done = False
    for line in raw.strip().splitlines():
        stripped = line.strip()
        if not header_done:
            if stripped.startswith("Source:"):
                metadata["source"] = stripped.replace("Source:", "").strip()
                continue
            if stripped.startswith("Department:"):
                metadata["department"] = stripped.replace("Department:", "").strip()
                continue
            if stripped.startswith("Effective Date:"):
                metadata["effective_date"] = stripped.replace("Effective Date:", "").strip()
                continue
            if stripped.startswith("Access:"):
                metadata["access"] = stripped.replace("Access:", "").strip()
                continue
            if stripped.startswith("==="):
                header_done = True
                content_lines.append(line)
                continue
            if not stripped or stripped.isupper():
                continue
        else:
            content_lines.append(line)
    return "\n".join(content_lines), metadata


def _chunk_text(text: str, base_meta: Dict[str, str]) -> List[Dict[str, Any]]:
    parts = re.split(r"(===.*?===)", text)
    chunks = []
    section = "General"
    section_text = ""
    for part in parts:
        if re.match(r"===.*?===", part):
            if section_text.strip():
                chunks.append({"text": section_text.strip(), "metadata": {**base_meta, "section": section}})
            section = part.strip("= ").strip()
            section_text = ""
        else:
            section_text += part
    if section_text.strip():
        chunks.append({"text": section_text.strip(), "metadata": {**base_meta, "section": section}})
    return chunks


def build_index(force: bool = False) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    existing = None
    try:
        existing = client.get_collection(CHROMA_COLLECTION)
        if existing.count() > 0 and not force:
            return
    except Exception:
        pass

    if force:
        try:
            client.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass

    collection = client.get_or_create_collection(CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"})
    ids, docs, metas, embeddings = [], [], [], []
    for path in sorted(DOCS_DIR.glob("*.txt")):
        text, meta = _parse_doc(path.read_text(encoding="utf-8"), path.name)
        for i, chunk in enumerate(_chunk_text(text, meta)):
            ids.append(f"{path.stem}_{i}")
            docs.append(chunk["text"])
            metas.append(chunk["metadata"])
            embeddings.append(_get_embedding(chunk["text"]))
    if ids:
        collection.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
    print(f"[retrieval] Indexed {len(ids)} chunks into {CHROMA_COLLECTION}")


def _get_collection():
    import chromadb

    build_index(force=False)
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client.get_collection(CHROMA_COLLECTION)


def retrieve_dense(query: str, top_k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
    try:
        collection = _get_collection()
        results = collection.query(
            query_embeddings=[_get_embedding(query)],
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )
        chunks = []
        for doc, dist, meta in zip(
            (results.get("documents") or [[]])[0],
            (results.get("distances") or [[]])[0],
            (results.get("metadatas") or [[]])[0],
        ):
            meta = meta or {}
            chunks.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "score": round(1 - float(dist), 4),
                "metadata": meta,
            })
        return chunks
    except Exception as e:
        print(f"⚠️  ChromaDB query failed: {e}")
        return []


def run(state: dict) -> dict:
    task = state.get("task", "")
    top_k = state.get("retrieval_top_k", DEFAULT_TOP_K)
    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state["workers_called"].append(WORKER_NAME)
    worker_io = {"worker": WORKER_NAME, "input": {"task": task, "top_k": top_k}, "output": None, "error": None}
    try:
        chunks = retrieve_dense(task, top_k=top_k)
        sources = list({c["source"] for c in chunks})
        state["retrieved_chunks"] = chunks
        state["retrieved_sources"] = sources
        worker_io["output"] = {"chunks_count": len(chunks), "sources": sources}
        state["history"].append(f"[{WORKER_NAME}] retrieved {len(chunks)} chunks from {sources}")
    except Exception as e:
        worker_io["error"] = {"code": "RETRIEVAL_FAILED", "reason": str(e)}
        state["retrieved_chunks"] = []
        state["retrieved_sources"] = []
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")
    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


if __name__ == "__main__":
    print("=" * 50)
    print("Retrieval Worker — Standalone Test")
    print("=" * 50)
    build_index(force=True)
    for query in ["SLA ticket P1 là bao lâu?", "Điều kiện được hoàn tiền là gì?", "Ai phê duyệt cấp quyền Level 3?"]:
        print(f"\n▶ Query: {query}")
        result = run({"task": query})
        for c in result.get("retrieved_chunks", [])[:2]:
            print(f"  [{c['score']:.3f}] {c['source']}: {c['text'][:90]}...")
    print("\n✅ retrieval_worker test done.")
