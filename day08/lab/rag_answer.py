"""
rag_answer.py — Sprint 2 + Sprint 3: Retrieval & Grounded Answer
================================================================
Sprint 2 (60 phút): Baseline RAG
  - Dense retrieval từ ChromaDB
  - Grounded answer function với prompt ép citation
  - Trả lời được ít nhất 3 câu hỏi mẫu, output có source

Sprint 3 (60 phút): Tuning tối thiểu
  - Thêm hybrid retrieval (dense + sparse/BM25)
  - Hoặc thêm rerank (cross-encoder)
  - Hoặc thử query transformation (expansion, decomposition, HyDE)
  - Tạo bảng so sánh baseline vs variant

Definition of Done Sprint 2:
  ✓ rag_answer("SLA ticket P1?") trả về câu trả lời có citation
  ✓ rag_answer("Câu hỏi không có trong docs") trả về "Không đủ dữ liệu"

Definition of Done Sprint 3:
  ✓ Có ít nhất 1 variant (hybrid / rerank / query transform) chạy được
  ✓ Giải thích được tại sao chọn biến đó để tune
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CẤU HÌNH
# =============================================================================

TOP_K_SEARCH = 10    # Số chunk lấy từ vector store trước rerank (search rộng)
TOP_K_SELECT = 3     # Số chunk gửi vào prompt sau rerank/select (top-3 sweet spot)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_API_BASE = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")


def _has_real_api_key(value: Optional[str]) -> bool:
    return bool(value and value.strip() and value.strip() not in {"sk-...", "...", "your_api_key_here"})


def _resolve_llm_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "").lower().strip()
    if provider in {"openai", "gemini", "openrouter", "extractive"}:
        if provider == "openai" and not _has_real_api_key(os.getenv("OPENAI_API_KEY")):
            return "extractive"
        if provider == "gemini" and not _has_real_api_key(os.getenv("GOOGLE_API_KEY")):
            return "extractive"
        if provider == "openrouter" and not _has_real_api_key(os.getenv("OPENROUTER_API_KEY")):
            return "extractive"
        return provider
    if _has_real_api_key(os.getenv("OPENROUTER_API_KEY")):
        return "openrouter"
    if _has_real_api_key(os.getenv("OPENAI_API_KEY")):
        return "openai"
    if _has_real_api_key(os.getenv("GOOGLE_API_KEY")):
        return "gemini"
    return "extractive"


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[\w-]+", text.lower(), flags=re.UNICODE)


def _chunk_key(chunk: Dict[str, Any]) -> str:
    meta = chunk.get("metadata", {}) or {}
    return "|".join([
        str(meta.get("source", "")),
        str(meta.get("section", "")),
        chunk.get("text", "")[:120],
    ])


# =============================================================================
# RETRIEVAL — DENSE (Vector Search)
# =============================================================================

def retrieve_dense(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Dense retrieval: tìm kiếm theo embedding similarity trong ChromaDB.
    """
    try:
        import chromadb
        from index import get_embedding, CHROMA_DB_DIR

        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        collection = client.get_collection("rag_lab")
    except Exception as e:
        raise RuntimeError(
            "Không đọc được Chroma index. Hãy chạy `python index.py` trong day08/lab trước. "
            f"Chi tiết: {e}"
        ) from e

    query_embedding = get_embedding(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    chunks = []
    for doc, meta, distance in zip(documents, metadatas, distances):
        chunks.append({
            "text": doc,
            "metadata": meta or {},
            "score": 1 - float(distance),
        })
    return chunks


# =============================================================================
# RETRIEVAL — SPARSE / BM25 (Keyword Search)
# Dùng cho Sprint 3 Variant hoặc kết hợp Hybrid
# =============================================================================

def retrieve_sparse(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Sparse retrieval: tìm kiếm theo keyword (BM25).

    Mạnh ở exact term, mã lỗi, tên riêng (ví dụ: "ERR-403", "P1", "refund").
    """
    try:
        import chromadb
        from rank_bm25 import BM25Okapi
        from index import CHROMA_DB_DIR

        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        collection = client.get_collection("rag_lab")
        results = collection.get(include=["documents", "metadatas"])
    except Exception as e:
        print(f"[retrieve_sparse] Không đọc được index/BM25 dependency: {e}")
        return []

    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or []
    if not documents:
        return []

    searchable_docs = []
    for doc, meta in zip(documents, metadatas):
        meta = meta or {}
        searchable_docs.append(
            " ".join([
                doc,
                str(meta.get("source", "")),
                str(meta.get("section", "")),
            ])
        )

    tokenized_corpus = [_tokenize(doc) for doc in searchable_docs]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    chunks = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        chunks.append({
            "text": documents[idx],
            "metadata": metadatas[idx] or {},
            "score": float(scores[idx]),
        })
    return chunks


# =============================================================================
# RETRIEVAL — HYBRID (Dense + Sparse với Reciprocal Rank Fusion)
# =============================================================================

def retrieve_hybrid(
    query: str,
    top_k: int = TOP_K_SEARCH,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: kết hợp dense và sparse bằng Reciprocal Rank Fusion (RRF).

    Mạnh ở: giữ được cả nghĩa (dense) lẫn keyword chính xác (sparse)
    Phù hợp khi: corpus lẫn lộn ngôn ngữ tự nhiên và tên riêng/mã lỗi/điều khoản

    Args:
        dense_weight: Trọng số cho dense score (0-1)
        sparse_weight: Trọng số cho sparse score (0-1)

    TODO Sprint 3 (nếu chọn hybrid):
    1. Chạy retrieve_dense() → dense_results
    2. Chạy retrieve_sparse() → sparse_results
    3. Merge bằng RRF:
       RRF_score(doc) = dense_weight * (1 / (60 + dense_rank)) +
                        sparse_weight * (1 / (60 + sparse_rank))
       60 là hằng số RRF tiêu chuẩn
    4. Sort theo RRF score giảm dần, trả về top_k

    Khi nào dùng hybrid (từ slide):
    - Corpus có cả câu tự nhiên VÀ tên riêng, mã lỗi, điều khoản
    - Query như "Approval Matrix" khi doc đổi tên thành "Access Control SOP"
    """
    dense_results = retrieve_dense(query, top_k=top_k)
    sparse_results = retrieve_sparse(query, top_k=top_k)

    if not sparse_results:
        return dense_results

    rrf_k = 60
    merged: Dict[str, Dict[str, Any]] = {}

    def add_results(results: List[Dict[str, Any]], weight: float) -> None:
        for rank, chunk in enumerate(results, start=1):
            key = _chunk_key(chunk)
            if key not in merged:
                merged[key] = {**chunk, "score": 0.0, "dense_score": None, "sparse_score": None}
            merged[key]["score"] += weight * (1 / (rrf_k + rank))
            if weight == dense_weight:
                merged[key]["dense_score"] = chunk.get("score")
            else:
                merged[key]["sparse_score"] = chunk.get("score")

    add_results(dense_results, dense_weight)
    add_results(sparse_results, sparse_weight)

    return sorted(merged.values(), key=lambda c: c.get("score", 0), reverse=True)[:top_k]


# =============================================================================
# RERANK (Sprint 3 alternative)
# Cross-encoder để chấm lại relevance sau search rộng
# =============================================================================

def rerank(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = TOP_K_SELECT,
) -> List[Dict[str, Any]]:
    """
    Rerank các candidate chunks bằng cross-encoder.

    Cross-encoder: chấm lại "chunk nào thực sự trả lời câu hỏi này?"
    MMR (Maximal Marginal Relevance): giữ relevance nhưng giảm trùng lặp

    Funnel logic (từ slide):
      Search rộng (top-20) → Rerank (top-6) → Select (top-3)

    TODO Sprint 3 (nếu chọn rerank):
    Option A — Cross-encoder:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [[query, chunk["text"]] for chunk in candidates]
        scores = model.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _ in ranked[:top_k]]

    Option B — Rerank bằng LLM (đơn giản hơn nhưng tốn token):
        Gửi list chunks cho LLM, yêu cầu chọn top_k relevant nhất

    Khi nào dùng rerank:
    - Dense/hybrid trả về nhiều chunk nhưng có noise
    - Muốn chắc chắn chỉ 3-5 chunk tốt nhất vào prompt
    """
    # TODO Sprint 3: Implement rerank
    # Tạm thời trả về top_k đầu tiên (không rerank)
    return candidates[:top_k]


# =============================================================================
# QUERY TRANSFORMATION (Sprint 3 alternative)
# =============================================================================

def transform_query(query: str, strategy: str = "expansion") -> List[str]:
    """
    Biến đổi query để tăng recall.

    Strategies:
      - "expansion": Thêm từ đồng nghĩa, alias, tên cũ
      - "decomposition": Tách query phức tạp thành 2-3 sub-queries
      - "hyde": Sinh câu trả lời giả (hypothetical document) để embed thay query

    TODO Sprint 3 (nếu chọn query transformation):
    Gọi LLM với prompt phù hợp với từng strategy.

    Ví dụ expansion prompt:
        "Given the query: '{query}'
         Generate 2-3 alternative phrasings or related terms in Vietnamese.
         Output as JSON array of strings."

    Ví dụ decomposition:
        "Break down this complex query into 2-3 simpler sub-queries: '{query}'
         Output as JSON array."

    Khi nào dùng:
    - Expansion: query dùng alias/tên cũ (ví dụ: "Approval Matrix" → "Access Control SOP")
    - Decomposition: query hỏi nhiều thứ một lúc
    - HyDE: query mơ hồ, search theo nghĩa không hiệu quả
    """
    # TODO Sprint 3: Implement query transformation
    # Tạm thời trả về query gốc
    return [query]


# =============================================================================
# GENERATION — GROUNDED ANSWER FUNCTION
# =============================================================================

def build_context_block(chunks: List[Dict[str, Any]]) -> str:
    """
    Đóng gói danh sách chunks thành context block để đưa vào prompt.

    Format: structured snippets với source, section, score (từ slide).
    Mỗi chunk có số thứ tự [1], [2], ... để model dễ trích dẫn.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", "unknown")
        section = meta.get("section", "")
        score = chunk.get("score", 0)
        text = chunk.get("text", "")

        # TODO: Tùy chỉnh format nếu muốn (thêm effective_date, department, ...)
        header = f"[{i}] {source}"
        if section:
            header += f" | {section}"
        if score > 0:
            header += f" | score={score:.2f}"

        context_parts.append(f"{header}\n{text}")

    return "\n\n".join(context_parts)


def build_grounded_prompt(query: str, context_block: str) -> str:
    """
    Xây dựng grounded prompt theo 4 quy tắc từ slide:
    1. Evidence-only: Chỉ trả lời từ retrieved context
    2. Abstain: Thiếu context thì nói không đủ dữ liệu
    3. Citation: Gắn source/section khi có thể
    4. Short, clear, stable: Output ngắn, rõ, nhất quán

    TODO Sprint 2:
    Đây là prompt baseline. Trong Sprint 3, bạn có thể:
    - Thêm hướng dẫn về format output (JSON, bullet points)
    - Thêm ngôn ngữ phản hồi (tiếng Việt vs tiếng Anh)
    - Điều chỉnh tone phù hợp với use case (CS helpdesk, IT support)
    """
    prompt = f"""Answer only from the retrieved context below.
If the context is insufficient to answer the question, say you do not know and do not make up information.
Cite the source field (in brackets like [1]) when possible.
Keep your answer short, clear, and factual.
Respond in the same language as the question.

Question: {query}

Context:
{context_block}

Answer:"""
    return prompt


def call_llm(prompt: str) -> str:
    """
    Gọi LLM để sinh câu trả lời. Hỗ trợ OpenAI hoặc Gemini qua LLM_PROVIDER.
    Nếu không có API key, dùng LLM_PROVIDER=extractive trong rag_answer() để fallback local.
    """
    provider = _resolve_llm_provider()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not _has_real_api_key(api_key):
            raise RuntimeError("LLM_PROVIDER=openai nhưng thiếu OPENAI_API_KEY hợp lệ")

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        return (response.choices[0].message.content or "").strip()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not _has_real_api_key(api_key):
            raise RuntimeError("LLM_PROVIDER=openrouter nhưng thiếu OPENROUTER_API_KEY hợp lệ")

        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_API_BASE,
        )
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        return (response.choices[0].message.content or "").strip()

    if provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not _has_real_api_key(api_key):
            raise RuntimeError("LLM_PROVIDER=gemini nhưng thiếu GOOGLE_API_KEY hợp lệ")

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0, "max_output_tokens": 512},
        )
        return (response.text or "").strip()

    raise RuntimeError("LLM_PROVIDER=extractive không gọi call_llm(); dùng extractive_answer().")


def extractive_answer(query: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Fallback local khi chưa cấu hình API key. Trích các câu/dòng liên quan nhất
    từ retrieved chunks và gắn citation. Không thay thế chất lượng LLM thật,
    nhưng đủ để kiểm thử indexing/retrieval end-to-end.
    """
    if not chunks:
        return "Không đủ dữ liệu trong tài liệu hiện có để trả lời câu hỏi này."

    query_tokens = set(_tokenize(query))
    # Nếu query chứa mã lỗi không xuất hiện trong context thì abstain rõ ràng.
    code_tokens = {t for t in query_tokens if re.search(r"[a-z]+-?\d+|\d+-?[a-z]+", t)}
    context_text = "\n".join(c.get("text", "") for c in chunks).lower()
    if code_tokens and not any(t in context_text for t in code_tokens):
        return "Không đủ dữ liệu trong tài liệu hiện có để trả lời câu hỏi này."

    scored_lines = []
    for idx, chunk in enumerate(chunks, start=1):
        text = chunk.get("text", "")
        lines = [line.strip(" -•\t") for line in re.split(r"\n+|(?<=[.!?])\s+", text) if line.strip()]
        for line in lines:
            line_tokens = set(_tokenize(line))
            overlap = len(query_tokens & line_tokens)
            score = overlap + max(float(chunk.get("score", 0)), 0)
            if overlap > 0:
                scored_lines.append((score, idx, line))

    if not scored_lines:
        top = chunks[0]
        if float(top.get("score", 0)) < 0.2:
            return "Không đủ dữ liệu trong tài liệu hiện có để trả lời câu hỏi này."
        preview = top.get("text", "").strip().split("\n")[0]
        return f"{preview} [1]"

    selected = []
    seen = set()
    for _, idx, line in sorted(scored_lines, key=lambda x: x[0], reverse=True):
        if line in seen:
            continue
        seen.add(line)
        selected.append(f"{line} [{idx}]")
        if len(selected) >= 3:
            break

    return " ".join(selected)


def rag_answer(
    query: str,
    retrieval_mode: str = "dense",
    top_k_search: int = TOP_K_SEARCH,
    top_k_select: int = TOP_K_SELECT,
    use_rerank: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Pipeline RAG hoàn chỉnh: query → retrieve → (rerank) → generate.

    Args:
        query: Câu hỏi
        retrieval_mode: "dense" | "sparse" | "hybrid"
        top_k_search: Số chunk lấy từ vector store (search rộng)
        top_k_select: Số chunk đưa vào prompt (sau rerank/select)
        use_rerank: Có dùng cross-encoder rerank không
        verbose: In thêm thông tin debug

    Returns:
        Dict với:
          - "answer": câu trả lời grounded
          - "sources": list source names trích dẫn
          - "chunks_used": list chunks đã dùng
          - "query": query gốc
          - "config": cấu hình pipeline đã dùng

    TODO Sprint 2 — Implement pipeline cơ bản:
    1. Chọn retrieval function dựa theo retrieval_mode
    2. Gọi rerank() nếu use_rerank=True
    3. Truncate về top_k_select chunks
    4. Build context block và grounded prompt
    5. Gọi call_llm() để sinh câu trả lời
    6. Trả về kết quả kèm metadata

    TODO Sprint 3 — Thử các variant:
    - Variant A: đổi retrieval_mode="hybrid"
    - Variant B: bật use_rerank=True
    - Variant C: thêm query transformation trước khi retrieve
    """
    config = {
        "retrieval_mode": retrieval_mode,
        "top_k_search": top_k_search,
        "top_k_select": top_k_select,
        "use_rerank": use_rerank,
    }

    # --- Bước 1: Retrieve ---
    if retrieval_mode == "dense":
        candidates = retrieve_dense(query, top_k=top_k_search)
    elif retrieval_mode == "sparse":
        candidates = retrieve_sparse(query, top_k=top_k_search)
    elif retrieval_mode == "hybrid":
        candidates = retrieve_hybrid(query, top_k=top_k_search)
    else:
        raise ValueError(f"retrieval_mode không hợp lệ: {retrieval_mode}")

    if verbose:
        print(f"\n[RAG] Query: {query}")
        print(f"[RAG] Retrieved {len(candidates)} candidates (mode={retrieval_mode})")
        for i, c in enumerate(candidates[:3]):
            print(f"  [{i+1}] score={c.get('score', 0):.3f} | {c['metadata'].get('source', '?')}")

    # --- Bước 2: Rerank (optional) ---
    if use_rerank:
        candidates = rerank(query, candidates, top_k=top_k_select)
    else:
        candidates = candidates[:top_k_select]

    if verbose:
        print(f"[RAG] After select: {len(candidates)} chunks")

    if not candidates:
        return {
            "query": query,
            "answer": "Không đủ dữ liệu trong tài liệu hiện có để trả lời câu hỏi này.",
            "sources": [],
            "chunks_used": [],
            "config": config,
        }

    # --- Bước 3: Build context và prompt ---
    context_block = build_context_block(candidates)
    prompt = build_grounded_prompt(query, context_block)

    if verbose:
        print(f"\n[RAG] Prompt:\n{prompt[:500]}...\n")

    # --- Bước 4: Generate ---
    if _resolve_llm_provider() == "extractive":
        answer = extractive_answer(query, candidates)
    else:
        try:
            answer = call_llm(prompt)
        except Exception as e:
            if verbose:
                print(f"[RAG] LLM call failed, fallback extractive: {e}")
            answer = extractive_answer(query, candidates)

    # --- Bước 5: Extract sources ---
    sources = list({
        c["metadata"].get("source", "unknown")
        for c in candidates
    })

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "chunks_used": candidates,
        "config": config,
    }


# =============================================================================
# SPRINT 3: SO SÁNH BASELINE VS VARIANT
# =============================================================================

def compare_retrieval_strategies(query: str) -> None:
    """
    So sánh các retrieval strategies với cùng một query.

    TODO Sprint 3:
    Chạy hàm này để thấy sự khác biệt giữa dense, sparse, hybrid.
    Dùng để justify tại sao chọn variant đó cho Sprint 3.

    A/B Rule (từ slide): Chỉ đổi MỘT biến mỗi lần.
    """
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    strategies = ["dense", "hybrid"]  # Thêm "sparse" sau khi implement

    for strategy in strategies:
        print(f"\n--- Strategy: {strategy} ---")
        try:
            result = rag_answer(query, retrieval_mode=strategy, verbose=False)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except NotImplementedError as e:
            print(f"Chưa implement: {e}")
        except Exception as e:
            print(f"Lỗi: {e}")


# =============================================================================
# MAIN — Demo và Test
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 2 + 3: RAG Answer Pipeline")
    print("=" * 60)

    # Test queries từ data/test_questions.json
    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?",
        "Ai phải phê duyệt để cấp quyền Level 3?",
        "ERR-403-AUTH là lỗi gì?",  # Query không có trong docs → kiểm tra abstain
    ]

    print("\n--- Sprint 2: Test Baseline (Dense) ---")
    for query in test_queries:
        print(f"\nQuery: {query}")
        try:
            result = rag_answer(query, retrieval_mode="dense", verbose=True)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except NotImplementedError:
            print("Chưa implement — hoàn thành TODO trong retrieve_dense() và call_llm() trước.")
        except Exception as e:
            print(f"Lỗi: {e}")

    # Uncomment sau khi Sprint 3 hoàn thành:
    # print("\n--- Sprint 3: So sánh strategies ---")
    # compare_retrieval_strategies("Approval Matrix để cấp quyền là tài liệu nào?")
    # compare_retrieval_strategies("ERR-403-AUTH")

    print("\n\nSprint 2 + 3 demo hoàn thành.")
    print("Nếu LLM provider lỗi, pipeline đã fallback sang extractive answer để vẫn test được retrieval.")
    print("Chạy tiếp: python eval.py")
