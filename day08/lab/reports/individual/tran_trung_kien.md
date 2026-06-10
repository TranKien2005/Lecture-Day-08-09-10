# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Trần Trung Kiên  
**Mã sinh viên:** 2A202600850  
**Vai trò trong nhóm:** Tech Lead / Retrieval Owner / Eval Owner / Documentation Owner  
**Ngày nộp:** 2026-06-10

---

## 1. Tôi đã làm gì trong lab này?

Trong lab Day 08, tôi thực hiện toàn bộ pipeline RAG từ indexing đến retrieval, generation và evaluation. Ở Sprint 1, tôi hoàn thiện `index.py` để đọc 5 tài liệu nội bộ, parse metadata, chia chunk theo section heading, tạo embedding và lưu vào ChromaDB. Ở Sprint 2, tôi hoàn thiện `rag_answer.py` để query ChromaDB bằng dense retrieval, build grounded prompt và sinh câu trả lời có citation. Tôi cũng thêm cơ chế fallback extractive để pipeline vẫn có thể chạy local khi chưa cấu hình API key cho OpenAI hoặc Gemini. Ở Sprint 3, tôi implement variant hybrid retrieval bằng cách kết hợp dense search với BM25 sparse search thông qua Reciprocal Rank Fusion. Ở Sprint 4, tôi cập nhật `eval.py`, architecture document, tuning log và group report để mô tả rõ quyết định kỹ thuật cũng như cách đánh giá pipeline.

---

## 2. Điều tôi hiểu rõ hơn sau lab này

Sau lab này, tôi hiểu rõ hơn rằng chất lượng RAG không chỉ phụ thuộc vào LLM mà phụ thuộc rất nhiều vào retrieval. Nếu retriever không lấy đúng context, model dù tốt vẫn dễ trả lời thiếu hoặc hallucinate. Tôi cũng thấy chunking cần bám theo cấu trúc tài liệu thay vì cắt tùy ý theo số ký tự, vì mỗi tài liệu policy/SLA thường có các section độc lập chứa điều khoản quan trọng. Một điểm khác tôi hiểu rõ hơn là khác biệt giữa dense retrieval và sparse retrieval. Dense retrieval tốt cho câu hỏi diễn đạt tự nhiên, còn BM25 tốt với exact keyword, mã, tên chính sách hoặc alias. Vì vậy hybrid retrieval phù hợp với corpus nội bộ có cả văn bản policy tự nhiên và thuật ngữ như `P1`, `Level 3`, `Approval Matrix`, `Flash Sale`.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn

Điều tôi thấy đáng chú ý là chỉ cần một query dùng alias hoặc tên cũ thì dense retrieval có thể không chắc chắn lấy đúng tài liệu, dù thông tin thật sự có trong corpus. Ví dụ câu hỏi về “Approval Matrix” thực chất cần map đến “Access Control SOP”. Nếu pipeline chỉ dựa vào semantic similarity, kết quả có thể phụ thuộc nhiều vào embedding model. Vì vậy tôi chọn hybrid retrieval để bổ sung tín hiệu exact keyword từ BM25. Một khó khăn khác là làm sao để pipeline chạy được trên máy local mà không bắt buộc có API key. Nếu chỉ implement OpenAI/Gemini, người chạy thử có thể bị chặn ngay từ bước generation. Vì vậy tôi thêm `LLM_PROVIDER=extractive` làm fallback, giúp kiểm tra end-to-end indexing và retrieval trước. Tuy nhiên fallback này chỉ phục vụ smoke test, không thay thế hoàn toàn LLM thật.

---

## 4. Phân tích một câu hỏi trong scorecard

**Câu hỏi:** `q08` — “Nhân viên được làm remote tối đa mấy ngày mỗi tuần?”

**Phân tích:**

Tôi chọn `q08` vì đây là câu thể hiện rõ khác biệt giữa baseline và variant trong kết quả thật. Baseline dense retrieve đúng source HR policy và trả lời đúng ý chính: nhân viên sau thời gian thử việc được làm remote tối đa 2 ngày mỗi tuần. Tuy nhiên baseline thiếu điều kiện quan trọng là lịch remote cần được Team Lead phê duyệt. Vì vậy completeness của baseline chỉ đạt 3/5 theo scorecard. Variant hybrid vẫn retrieve đúng source, nhưng answer đầy đủ hơn: “Nhân viên sau probation period được làm remote tối đa 2 ngày mỗi tuần. Lịch remote cần được Team Lead phê duyệt qua HR Portal.” Nhờ đó completeness tăng lên 5/5. Root cause không nằm ở indexing vì metadata/source đúng, cũng không nằm ở recall vì cả hai đều recall 5/5. Vấn đề chính là selection/context quality trong retrieval: hybrid đưa chunk có điều kiện approval rõ hơn vào top context, giúp generation trả lời đầy đủ hơn. Đây là bằng chứng thực tế cho thấy hybrid không nhất thiết tăng recall khi baseline đã tốt, nhưng vẫn có thể cải thiện completeness của answer.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì?

Nếu có thêm thời gian, tôi sẽ thêm cross-encoder rerank sau hybrid retrieval để giảm noise trước khi chọn top-3 context đưa vào prompt. Tôi cũng sẽ implement LLM-as-Judge cho các metric faithfulness, answer relevance và completeness để scorecard tự động đầy đủ hơn, thay vì hiện tại chủ yếu tự động được context recall và cần chấm thủ công các metric generation.
