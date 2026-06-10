# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Trần Trung Kiên  
**Mã sinh viên:** 2A202600850  
**Vai trò trong nhóm:** Supervisor Owner / Worker Owner / MCP Owner / Trace & Docs Owner  
**Ngày nộp:** 2026-06-10

---

## 1. Tôi phụ trách phần nào?

Trong Day 09, tôi phụ trách toàn bộ hệ thống multi-agent. Phần supervisor nằm ở `graph.py`, trong đó tôi sửa `supervisor_node()` để route task theo keyword domain và thay placeholder worker bằng worker thật. Phần retrieval nằm ở `workers/retrieval.py`: tôi implement auto-build ChromaDB từ `data/docs`, dùng 9router embedding endpoint và trả về `retrieved_chunks`, `retrieved_sources`. Phần synthesis nằm ở `workers/synthesis.py`: tôi cấu hình gọi 9router model `cx/gpt-5.5`, viết grounded prompt và thêm fallback extractive nếu LLM lỗi. Tôi cũng kiểm tra `policy_tool.py` và `mcp_server.py` để MCP mock tools được gọi từ worker. Cuối cùng, tôi chạy `eval_trace.py`, đọc trace thật trong `artifacts/traces/` và cập nhật docs/report theo kết quả.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Tôi chọn rule-based routing trong supervisor thay vì LLM classifier.

Lý do là domain của lab khá rõ: câu về SLA/P1/ticket/helpdesk/remote nên route sang retrieval; câu về refund/access/contractor/admin nên route sang policy worker; câu có `ERR-*` hoặc risk thì trigger human review. Nếu dùng LLM classifier, mỗi câu sẽ tốn thêm một LLM call, làm tăng latency và khó debug vì route decision phụ thuộc output model. Rule-based routing ít linh hoạt hơn với paraphrase lạ, nhưng đổi lại trace rất rõ và dễ giải thích.

Bằng chứng từ trace thật: sau khi chạy `python eval_trace.py`, hệ thống chạy thành công 15/15 câu. Routing distribution là retrieval worker 8/15, policy tool worker 7/15, HITL 1/15. Trace `run_20260610_150343.json` cho q09 ghi `unknown error code + risk_high → human review | human approved → retrieval`, chứng minh rule risk hoạt động đúng. Trace q01 ghi `task contains retrieval/SLA/helpdesk keyword`, route sang retrieval và trả lời đúng SLA P1 là 4 giờ, first response 15 phút.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** Worker graph ban đầu chạy nhưng retrieval không hoạt động thật.

**Symptom:** Khi chạy `python graph.py` lần đầu, output báo `ChromaDB query failed: No module named 'chromadb'`, các câu vẫn có answer fallback nhưng confidence thấp 0.1 và không retrieve được chunks thật. Ngoài ra `graph.py` ban đầu còn dùng placeholder worker nodes nên dù có worker files, graph không gọi logic thật.

**Root cause:** Lỗi nằm ở cả environment và orchestration. Environment thiếu dependency `chromadb`. Code `graph.py` vẫn để placeholder output thay vì import và gọi `workers.retrieval.run`, `workers.policy_tool.run`, `workers.synthesis.run`. `retrieval.py` cũng chưa tự build index bằng cấu hình 9router.

**Cách sửa:** Tôi sửa `requirements.txt` để cài dependency ổn trên Windows, cài requirements, viết lại `workers/retrieval.py` để auto-build Chroma index 29 chunks bằng 9router embedding, sửa `workers/synthesis.py` để gọi 9router, và sửa `graph.py` để gọi worker thật.

**Bằng chứng trước/sau:** Trước sửa, graph báo thiếu `chromadb`. Sau sửa, `python graph.py` build được `29 chunks into day09_docs`; `python eval_trace.py` chạy 15/15 câu thành công, avg confidence 0.474, MCP usage 7/15, HITL 1/15.

---

## 4. Tôi tự đánh giá đóng góp của mình

Tôi làm tốt nhất ở phần nối các thành phần rời rạc thành pipeline chạy thật. Trước đó repo có scaffold tương đối đầy đủ nhưng nhiều phần là placeholder; tôi đã chuyển thành graph có worker thật, trace thật và evaluation thật. Tôi cũng giữ được bằng chứng cụ thể: trace JSON, eval_report và docs cập nhật theo số liệu thật.

Điểm còn yếu là routing vẫn dựa trên keyword rule, chưa có classifier có cấu trúc nên có thể miss các cách hỏi khác. Confidence cũng chỉ là heuristic từ retrieval score và abstain, chưa phải confidence được judge độc lập. Vì nhóm chỉ có một người, toàn bộ supervisor, worker, MCP, trace và docs đều phụ thuộc vào tôi; nếu một module chưa xong thì toàn pipeline bị block. Tôi không phụ thuộc thành viên khác, nhưng vì không có review chéo nên rủi ro sót lỗi cao hơn.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ cải thiện policy worker để gọi `check_access_permission` có cấu trúc cho mọi câu hỏi access level. Lý do là trace các câu access/P1 emergency như q15 có confidence tốt hơn nhưng vẫn có rủi ro partial nếu grading yêu cầu chính xác số approver, emergency override và điều kiện contractor. Tool call có cấu trúc sẽ giúp answer ổn định hơn cho gq09, câu multi-hop khó nhất.
