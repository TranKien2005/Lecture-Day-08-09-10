# Tuning Log — RAG Pipeline (Day 08 Lab)

> A/B Rule: Chỉ đổi MỘT biến mỗi lần.

---

## Baseline (Sprint 2)

**Ngày:** 2026-06-10  
**Config:**

```python
retrieval_mode = "dense"
chunk_size = 400 tokens
chunk_overlap = 80 tokens
top_k_search = 10
top_k_select = 3
use_rerank = False
embedding_model = "paraphrase-multilingual-MiniLM-L12-v2"  # default local
llm_provider = "extractive"  # local fallback nếu chưa có API key
```

**Scorecard Baseline:**

| Metric | Average Score |
|--------|--------------|
| Faithfulness | Chạy bằng heuristic trong `python eval.py` |
| Answer Relevance | Chạy bằng heuristic trong `python eval.py` |
| Context Recall | Chạy bằng `python eval.py` |
| Completeness | Chạy bằng heuristic trong `python eval.py` |

**Câu hỏi có rủi ro yếu:**

- `q07` — “Approval Matrix” là alias/tên cũ của “Access Control SOP”. Dense retrieval có thể bỏ lỡ nếu embedding không bắt đúng alias.
- `q09` — `ERR-403-AUTH` không có trong tài liệu. Pipeline phải abstain thay vì đoán theo kiến thức ngoài context.
- `q10` — VIP refund process không được nêu riêng trong tài liệu; answer cần nói không có quy trình đặc biệt nếu context không đề cập.

**Giả thuyết nguyên nhân (Error Tree):**

- [ ] Indexing: Chunking cắt giữa điều khoản
- [x] Retrieval: Dense có thể bỏ lỡ exact keyword / alias
- [ ] Retrieval: Top-k quá ít → thiếu evidence
- [x] Generation: Nếu không có guard, model có thể trả lời ngoài context
- [ ] Generation: Context quá dài → lost in the middle

---

## Variant 1 (Sprint 3)

**Ngày:** 2026-06-10  
**Biến thay đổi:** Retrieval mode từ `dense` sang `hybrid`.

**Lý do chọn biến này:**

Corpus có cả câu tự nhiên và exact term: `P1`, `Level 3`, `Approval Matrix`, `Flash Sale`, `VPN`, tên nguồn tài liệu, và các thuật ngữ policy. Dense retrieval phù hợp cho semantic match, nhưng có thể yếu với alias hoặc mã/từ khóa ngắn. BM25 mạnh với keyword chính xác. Vì vậy variant hybrid dùng dense + BM25 và gộp bằng Reciprocal Rank Fusion.

**Config thay đổi:**

```python
retrieval_mode = "hybrid"
# Các tham số còn lại giữ nguyên như baseline:
chunk_size = 400
overlap = 80
top_k_search = 10
top_k_select = 3
use_rerank = False
```

**Scorecard Variant 1:**

| Metric | Baseline | Variant 1 | Delta |
|--------|----------|-----------|-------|
| Faithfulness | 4.50/5 | 4.40/5 | -0.10 |
| Answer Relevance | 5.00/5 | 4.80/5 | -0.20 |
| Context Recall | 5.00/5 | 5.00/5 | 0.00 |
| Completeness | 3.70/5 | 4.30/5 | +0.60 |

**Nhận xét:**

Kết quả thực tế cho thấy baseline dense đã retrieve đúng expected source cho toàn bộ câu có expected source, nên `Context Recall` của cả baseline và hybrid đều đạt 5.00/5. Vì vậy hybrid không tạo delta ở recall. Tuy nhiên hybrid cải thiện `Completeness` từ 3.70/5 lên 4.30/5. Cải thiện rõ nhất là `q08`: baseline thiếu điều kiện Team Lead approval, còn hybrid trả lời đủ “2 ngày/tuần” và “Team Lead phê duyệt”. `q09` cũng tốt hơn ở completeness vì variant abstain rõ ràng hơn khi context không có lỗi `ERR-403-AUTH`.

Đổi lại, `Faithfulness` giảm nhẹ từ 4.50 xuống 4.40 và `Answer Relevance` giảm từ 5.00 xuống 4.80 theo heuristic. Nguyên nhân chính là answer của `q09` rất ngắn và không overlap nhiều token với context/expected answer, dù về mặt hành vi abstain là đúng. Đây là hạn chế của heuristic scoring, cần manual review với các câu insufficient-context.

**Kết luận:**

Variant hybrid tốt hơn baseline ở mục tiêu quan trọng nhất của Sprint 3 là trả lời đầy đủ hơn trên một số câu có điều kiện/keyword, đặc biệt q08 và q09. Vì baseline đã có recall 100%, hybrid không cải thiện retrieval recall nhưng cải thiện answer completeness. Nhóm chọn hybrid làm cấu hình tốt nhất cho grading vì completeness tăng +0.60 trong khi các giảm nhẹ ở faithfulness/relevance chủ yếu do heuristic scoring với câu abstain.

---

## Variant 2

Không thực hiện trong scope hiện tại để giữ đúng A/B rule. Nếu có thêm thời gian, có thể thử rerank bằng cross-encoder, nhưng chỉ nên bật sau khi đã ghi nhận rõ baseline và hybrid.

---

## Tóm tắt học được

1. **Lỗi phổ biến nhất trong pipeline này là gì?**  
   Retrieval không chỉ là semantic similarity. Với corpus nội bộ, keyword/alias/ngữ cảnh version rất quan trọng, nên dense-only có thể bỏ lỡ tài liệu đúng.

2. **Biến nào có tác động lớn nhất tới chất lượng?**  
   Retrieval mode có tác động lớn vì generation chỉ có thể grounded nếu context đúng được đưa vào prompt. Hybrid giúp tăng cơ hội lấy đúng source mà vẫn giữ top-k nhỏ.

3. **Nếu có thêm 1 giờ, nhóm sẽ thử gì tiếp theo?**  
   Thử rerank bằng cross-encoder sau hybrid để giảm noise trong top-10 trước khi chọn top-3. Việc này nên được đo riêng, không bật cùng lúc với một biến khác.
