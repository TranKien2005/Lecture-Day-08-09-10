# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Trần Trung Kiên  
**MSSV:** 2A202600850  
**Ngày:** 2026-06-10

---

## 1. Metrics Comparison

Nguồn số liệu:

- Day 08: `day08/lab/results/scorecard_variant.md` sau khi chạy `python eval.py`.
- Day 09: `day09/lab/artifacts/eval_report.json` sau khi chạy `python eval_trace.py` với 15 traces sạch.

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | N/A | 0.474 | N/A | Day 08 scorecard không có confidence field. |
| Avg latency (ms) | N/A | 14,751 ms | N/A | Day 08 không đo latency trong eval.py. |
| Context recall / source success | 5.00/5 | Top sources traced per run | Không cùng metric | Day 09 ghi sources trong trace, không chấm recall tự động. |
| Abstain/HITL rate | q09 abstain trong scorecard | HITL 1/15 (6%) | Day 09 rõ hơn | Day 09 trace ghi `hitl_triggered=true`. |
| MCP usage rate | N/A | 7/15 (46%) | +46% | Day 08 không có MCP/tool layer. |
| Routing visibility | Không có | Có `route_reason` cho 15/15 traces | Cải thiện rõ | Debug nhanh hơn vì biết route và worker sequence. |
| Trace completeness | Answer-level scorecard | Full JSON trace: route, workers, sources, confidence | Cải thiện rõ | Day 09 dễ audit từng bước. |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Tốt với câu đơn như SLA P1, refund, account lock | Tốt, route về retrieval hoặc policy đúng |
| Latency | Không đo trong scorecard | Khoảng 9–15s/câu sau khi index |
| Observation | Pipeline đơn giản hơn | Có trace nhưng overhead cao hơn |

**Kết luận:** Với câu hỏi đơn giản, multi-agent không nhất thiết tăng chất lượng answer so với Day 08. Lợi ích chính là trace/debug, không phải accuracy.

### 2.2 Câu hỏi multi-hop / policy + tool

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Có thể trả lời nếu retrieve đủ context | Tốt hơn về tổ chức vì policy worker + MCP tools tách trách nhiệm |
| Routing visible? | Không | Có |
| Observation | Khó biết vì sao context được chọn | Trace ghi route, workers, MCP usage |

**Kết luận:** Multi-agent hữu ích hơn ở câu có policy exception hoặc access/P1 combination. Ví dụ câu `Ticket P1 lúc 2am + Level 2 access temporary for contractor` route sang policy worker, gọi MCP, rồi synthesis trả lời dựa trên policy/access context.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain behavior | q09 trong scorecard trả lời không biết | q09 trigger HITL và abstain rõ |
| Hallucination cases | Không thấy trong public test | Không thấy trong trace q09 |
| Observation | Không có trace risk decision | Có `risk_high=true`, `hitl_triggered=true` |

**Kết luận:** Day 09 tốt hơn về anti-hallucination process vì có risk/HITL path. Với `ERR-403-AUTH`, trace ghi rõ unknown error → human_review → retrieval → answer không đủ thông tin.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow

```
Khi answer sai → đọc output scorecard → kiểm tra chunks_used trong rag_answer
→ đoán lỗi ở retrieval/generation → sửa trực tiếp pipeline.
Không có route_reason hoặc worker boundary.
Thời gian ước tính: 10–20 phút cho một lỗi routing/policy phức tạp.
```

### Day 09 — Debug workflow

```
Khi answer sai → đọc trace JSON → xem supervisor_route + route_reason
  → Nếu route sai → sửa supervisor_node/route_decision
  → Nếu retrieval sai → test workers/retrieval.py độc lập
  → Nếu policy sai → test workers/policy_tool.py độc lập
  → Nếu synthesis sai → test workers/synthesis.py độc lập
Thời gian ước tính: 5–10 phút vì trace đã chỉ rõ worker sequence.
```

**Câu cụ thể nhóm đã debug:**

Khi chạy `graph.py` lần đầu, trace cho thấy retrieval không hoạt động vì thiếu dependency `chromadb`. Sau khi cài requirements và chạy lại, `retrieval_worker` build được 29 chunks vào Chroma collection `day09_docs`, và `q01` retrieve đúng `support/sla-p1-2026.pdf` với score 0.618. Đây là ví dụ Day 09 trace giúp xác định lỗi nằm ở retrieval environment, không phải supervisor/synthesis.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa pipeline/prompt chính | Thêm MCP tool + route rule |
| Thêm 1 domain mới | Thường sửa retrieval/generation chung | Thêm worker hoặc MCP capability riêng |
| Thay đổi retrieval strategy | Sửa trực tiếp trong RAG pipeline | Sửa `retrieval_worker.py` độc lập |
| A/B test một phần | Khó tách riêng | Có thể swap từng worker |

**Nhận xét:**

Day 09 dễ mở rộng hơn vì capability nằm sau interface rõ: supervisor quyết route, worker xử lý domain, MCP server expose tool. Ví dụ `get_ticket_info` có thể thay từ mock sang API thật mà không cần sửa synthesis worker.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query | 1 LLM call | 1 LLM call + routing/retrieval trace |
| Complex query | 1 LLM call | 1 LLM call + policy worker + optional MCP |
| MCP tool call | N/A | 7/15 câu có MCP usage |

**Nhận xét về cost-benefit:**

Day 09 tốn latency hơn. Run thật có avg latency 14,751 ms/câu với 9router LLM. Đổi lại, trace rõ hơn và hỗ trợ policy/MCP/HITL. Với câu hỏi đơn giản, Day 08 có thể đủ. Với câu multi-hop hoặc rủi ro hallucination, Day 09 đáng dùng hơn.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở điểm nào?**

1. Debuggability: có `route_reason`, `workers_called`, `mcp_tools_used`, `confidence` trong trace.
2. Extensibility: thêm MCP tool/worker mới mà không phải sửa toàn bộ RAG pipeline.
3. Risk handling: q09 unknown error trigger HITL thay vì chỉ dựa vào prompt abstain.

**Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. Latency cao hơn rõ rệt; avg 14,751 ms/câu trong run thật.
2. Với câu hỏi single-document đơn giản, answer quality không nhất thiết tốt hơn Day 08.

**Khi nào KHÔNG nên dùng multi-agent?**

Không nên dùng nếu task chỉ là FAQ/RAG đơn giản, không cần tool, không cần policy exception và không cần trace chi tiết. Khi đó Day 08 single-agent RAG đơn giản hơn và có thể nhanh hơn.

**Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

Thêm LLM classifier hoặc structured router để thay keyword routing, đồng thời biến MCP mock thành HTTP/MCP server thật. Ngoài ra cần metric tự động cho answer correctness giống Day 08 scorecard.
