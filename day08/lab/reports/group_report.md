# Báo Cáo Nhóm — Lab Day 08: Full RAG Pipeline

**Tên nhóm:** Day 08 RAG Lab  
**Thành viên:**

| Tên | Vai trò | Email |
|-----|---------|-------|
| Trần Trung Kiên | Tech Lead / Retrieval Owner / Eval Owner / Documentation Owner | 2A202600850 |

**Ngày nộp:** 2026-06-10  
**Repo:** https://github.com/TranKien2005/Lecture-Day-08-09-10.git

---

## 1. Pipeline nhóm đã xây dựng

Nhóm xây dựng pipeline RAG cho trợ lý nội bộ CS + IT Helpdesk. Pipeline bắt đầu từ 5 tài liệu nội bộ trong `data/docs`, gồm refund policy, SLA P1, access control SOP, IT helpdesk FAQ và HR leave policy. `index.py` đọc tài liệu, parse metadata ở header, tách chunk theo section heading `=== ... ===`, embed từng chunk và lưu vào ChromaDB collection `rag_lab`. `rag_answer.py` nhận câu hỏi, retrieve top-k chunk, đóng gói context có citation `[1]`, rồi sinh câu trả lời grounded.

**Chunking decision:**

Nhóm dùng `chunk_size=400` tokens ước lượng và `overlap=80`. Chiến lược chính là heading-based chunking vì tài liệu có cấu trúc section rõ ràng. Cách này giúp mỗi chunk thường chứa trọn một điều khoản như SLA, exception refund hoặc approval requirement.

**Embedding model:**

Mặc định dùng Sentence Transformers `paraphrase-multilingual-MiniLM-L12-v2` để chạy local không cần API key. Pipeline vẫn hỗ trợ OpenAI embedding nếu cấu hình `EMBEDDING_PROVIDER=openai` và có API key hợp lệ.

**Retrieval variant (Sprint 3):**

Variant được chọn là hybrid retrieval: dense Chroma search kết hợp BM25 sparse search bằng Reciprocal Rank Fusion. Lý do là corpus có nhiều exact term và alias như `P1`, `Level 3`, `Approval Matrix`, `Flash Sale`, đồng thời vẫn cần semantic retrieval cho câu hỏi tự nhiên.

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Chọn hybrid retrieval làm Sprint 3 variant thay vì rerank hoặc query transform.

**Bối cảnh vấn đề:**

Baseline dense retrieval có thể hoạt động tốt với câu hỏi diễn đạt gần giống tài liệu, nhưng có rủi ro với alias/tên cũ và keyword ngắn. Ví dụ `Approval Matrix` là tên cũ của `Access Control SOP`; nếu chỉ dựa vào embedding similarity, retriever có thể không ưu tiên đúng source. Ngoài ra các câu có `P1`, `Level 3`, `Flash Sale`, `VPN` phụ thuộc nhiều vào exact match.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Hybrid dense + BM25 | Dễ implement, dùng dependency có sẵn, cải thiện exact keyword/alias | Có thể đưa thêm noise nếu BM25 match keyword nhưng thiếu ngữ nghĩa |
| Cross-encoder rerank | Chọn top context chính xác hơn sau search rộng | Tải model thêm, chậm hơn, không giải quyết triệt để missing recall nếu candidate ban đầu thiếu |
| Query transform | Có thể expand alias và câu hỏi phức tạp | Cần LLM call/JSON parsing, tăng độ phức tạp |

**Phương án đã chọn và lý do:**

Nhóm chọn hybrid vì đây là thay đổi nhỏ nhất nhưng trực tiếp xử lý điểm yếu của dense-only. Dense vẫn giữ vai trò semantic retrieval, còn BM25 bổ sung tín hiệu keyword. Hai kết quả được gộp bằng RRF nên không cần tự normalize score giữa embedding similarity và BM25.

**Bằng chứng từ scorecard/tuning-log:**

`tuning-log.md` xác định `q07` và các câu chứa exact term là nhóm câu có rủi ro. `eval.py` đã được cấu hình chạy cả baseline dense và variant hybrid, xuất `results/scorecard_baseline.md`, `results/scorecard_variant.md` và `results/ab_comparison.csv` để so sánh context recall.

---

## 3. Kết quả grading questions

Hiện repo Day 08 có `data/test_questions.json` gồm 10 câu public để tự kiểm. Nếu có `grading_questions.json` riêng được public sau, cần chạy lại pipeline trên bộ đó và cập nhật mục này. Với test hiện tại, các câu kiểm tra chính gồm SLA P1, refund window, Level 3 approval, digital product refund exception, account lock, P1 escalation, alias Approval Matrix, remote work và abstain với `ERR-403-AUTH`.

**Ước tính điểm raw:** Chưa chấm chính thức / 98

**Câu tốt nhất:** `q01` — SLA P1 có thông tin trực tiếp trong `support/sla-p1-2026.pdf`, dễ retrieve và answer grounded.

**Câu fail/rủi ro:** `q07` — root cause có thể nằm ở retrieval nếu retriever không map alias “Approval Matrix” về `Access Control SOP`.

**Câu abstain:** `q09` — pipeline không nên đoán lỗi `ERR-403-AUTH`; nếu context không chứa mã lỗi này, answer phải nói không đủ dữ liệu.

---

## 4. A/B Comparison — Baseline vs Variant

**Biến đã thay đổi (chỉ 1 biến):** `retrieval_mode`: `dense` → `hybrid`.

| Metric | Baseline | Variant | Delta |
|--------|---------|---------|-------|
| Faithfulness | 4.50/5 | 4.40/5 | -0.10 |
| Answer Relevance | 5.00/5 | 4.80/5 | -0.20 |
| Context Recall | 5.00/5 | 5.00/5 | 0.00 |
| Completeness | 3.70/5 | 4.30/5 | +0.60 |

**Kết luận:**

Variant hybrid tốt hơn baseline ở `Completeness`, tăng từ 3.70/5 lên 4.30/5. Mức tăng rõ nhất nằm ở `q08`, nơi baseline chỉ trả lời số ngày remote tối đa còn hybrid trả lời thêm điều kiện Team Lead approval. `q09` cũng cải thiện completeness vì variant abstain rõ ràng hơn với lỗi không có trong tài liệu. Tuy nhiên `Context Recall` không đổi vì baseline đã retrieve đúng source 100%. `Faithfulness` và `Answer Relevance` giảm nhẹ theo heuristic, chủ yếu do câu abstain ngắn có ít token overlap với context. Nhóm vẫn chọn hybrid cho grading vì mục tiêu của variant là tăng độ đầy đủ câu trả lời mà không làm giảm recall.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Trần Trung Kiên | Indexing, embedding, Chroma store | Sprint 1 |
| Trần Trung Kiên | Dense retrieval, grounded answer, extractive fallback | Sprint 2 |
| Trần Trung Kiên | Hybrid retrieval bằng BM25 + RRF | Sprint 3 |
| Trần Trung Kiên | Eval config, architecture docs, tuning log, report | Sprint 4 |

**Điều nhóm làm tốt:**

Pipeline được thiết kế để chạy được local mà không phụ thuộc bắt buộc vào API key. Điều này giúp debug indexing/retrieval nhanh trước khi chuyển sang LLM generation thật.

**Điều nhóm làm chưa tốt:**

Các metric faithfulness, relevance và completeness vẫn cần chấm thủ công hoặc implement LLM-as-Judge. Hiện phần tự động mạnh nhất là context recall.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

Nhóm sẽ thêm cross-encoder rerank sau hybrid để giảm noise trong top-10 trước khi chọn top-3 vào prompt. Ngoài ra, nhóm sẽ implement LLM-as-Judge cho faithfulness/relevance/completeness để scorecard đầy đủ hơn thay vì chỉ dựa vào context recall và manual review.
