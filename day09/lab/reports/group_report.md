# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Day 09 Multi-Agent Lab  
**Thành viên:**

| Tên | Vai trò | MSSV |
|-----|---------|------|
| Trần Trung Kiên | Supervisor Owner / Worker Owner / MCP Owner / Trace & Docs Owner | 2A202600850 |

**Ngày nộp:** 2026-06-10  
**Repo:** https://github.com/TranKien2005/Lecture-Day-08-09-10.git

---

## 1. Kiến trúc nhóm đã xây dựng

Hệ thống Day 09 dùng pattern Supervisor-Worker để tách pipeline RAG Day 08 thành các trách nhiệm rõ ràng. `graph.py` là supervisor, nhận task và set `supervisor_route`, `route_reason`, `risk_high`, `needs_tool`. Các worker gồm `retrieval_worker` để build/query ChromaDB, `policy_tool_worker` để xử lý policy/access/refund exceptions và gọi MCP, `synthesis_worker` để tổng hợp câu trả lời bằng 9router model `cx/gpt-5.5`. MCP mock server expose các tools như `search_kb`, `get_ticket_info`, `check_access_permission`, `create_ticket`.

**Routing logic cốt lõi:**

Routing dùng keyword rule. Các câu có `p1`, `sla`, `ticket`, `remote`, `mật khẩu` route sang retrieval. Các câu có `refund`, `hoàn tiền`, `access`, `contractor`, `admin access` route sang policy worker. Câu chứa unknown error như `ERR-*` được flag `risk_high` và trigger human review placeholder trước khi quay về retrieval.

**MCP tools đã tích hợp:**

- `search_kb`: policy worker dùng khi cần lấy context từ KB.
- `get_ticket_info`: policy worker gọi với ticket P1 mock để lấy thông tin incident/ticket.
- `check_access_permission`: implement trong MCP server để kiểm tra approvers/access level.
- `create_ticket`: mock ticket creation, phục vụ extension.

Trong run thật 15 câu, MCP usage rate là 7/15 (46%).

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Dùng rule-based supervisor routing thay vì LLM router.

**Bối cảnh vấn đề:**

Lab cần chứng minh supervisor route được nhiều loại task, nhưng corpus chỉ có 5 tài liệu và domain khá hẹp: SLA P1, refund policy, access control, helpdesk FAQ và HR policy. Nếu dùng LLM classifier, hệ thống sẽ tốn thêm latency và dễ khó debug khi route sai. Trong khi đó keyword của từng domain khá rõ, ví dụ `hoàn tiền`, `flash sale`, `access`, `level 3`, `p1`, `sla`, `remote`, `mật khẩu`.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Rule-based routing | Nhanh, dễ debug, route_reason rõ | Có thể miss query paraphrase lạ |
| LLM classifier | Linh hoạt hơn với ngôn ngữ tự nhiên | Tốn thêm call, khó kiểm soát, tăng latency |
| Route mọi câu qua retrieval trước | Đơn giản | Không thể hiện rõ policy/tool worker và MCP |

**Phương án đã chọn và lý do:**

Nhóm chọn rule-based routing vì phù hợp lab và trace dễ giải thích. Kết quả thật: 15/15 câu chạy không crash, routing distribution là retrieval 8/15, policy 7/15, HITL 1/15. Route reason trong trace đều có nội dung cụ thể, không phải unknown.

**Bằng chứng từ trace/code:**

```text
q01 route_reason = task contains retrieval/SLA/helpdesk keyword
workers_called = ['retrieval_worker', 'synthesis_worker']

q09 route_reason = unknown error code + risk_high → human review | human approved → retrieval
workers_called = ['human_review', 'retrieval_worker', 'synthesis_worker']

q15 route = policy_tool_worker
mcp_usage_rate toàn run = 7/15 (46%)
```

---

## 3. Kết quả grading questions

Hiện chưa có `data/grading_questions.json` trong repo, nên nhóm chưa thể tạo `artifacts/grading_run.jsonl` thật. Nhóm đã chạy bộ public `data/test_questions.json` gồm 15 câu bằng `python eval_trace.py` và đạt 15/15 câu chạy thành công.

**Tổng điểm raw ước tính:** Chưa chấm chính thức / 96

**Câu pipeline xử lý tốt nhất:**

- ID: `q09` — lý do tốt: câu hỏi `ERR-403-AUTH` không có trong tài liệu, supervisor trigger HITL và synthesis abstain rõ ràng, không bịa thông tin.

**Câu pipeline fail hoặc partial:**

- ID: `q13` hoặc các câu access emergency phức tạp có thể partial nếu grading yêu cầu exact số lượng approver/role. Root cause tiềm năng là policy worker vẫn rule-based, chưa gọi `check_access_permission` cho mọi query access level.

**Câu gq07 (abstain):**

Logic hiện tại có path anti-hallucination tốt: nếu hỏi thông tin không có trong tài liệu như mức phạt SLA hoặc mã lỗi unknown, synthesis trả lời “Không đủ thông tin trong tài liệu nội bộ”.

**Câu gq09 (multi-hop khó nhất):**

Trace public tương tự q15 cho thấy câu P1 + temporary access route sang policy worker và gọi MCP. Workers sequence ghi được policy/synthesis, MCP usage được log trong `mcp_tools_used`. Đây là cơ sở để chạy grading q09 khi file được public.

---

## 4. So sánh Day 08 vs Day 09 — Điều nhóm quan sát được

**Metric thay đổi rõ nhất:**

Day 09 có trace-level metrics mà Day 08 không có: routing distribution, MCP usage, HITL rate, avg confidence, avg latency. Run thật Day 09 có 15 traces, avg confidence 0.474, avg latency 14,751 ms, MCP usage 7/15, HITL 1/15.

**Điều nhóm bất ngờ nhất:**

Multi-agent không tự động làm answer tốt hơn ở câu đơn giản. Với câu như SLA P1, Day 08 single RAG đã đủ tốt. Lợi ích lớn nhất của Day 09 là debuggability: trace cho biết route, reason, worker sequence, source và confidence.

**Trường hợp multi-agent không giúp ích hoặc làm chậm hệ thống:**

Các câu single-document đơn giản như “SLA xử lý ticket P1 là bao lâu?” có latency khoảng 11s trong run Day 09 do vẫn qua orchestration + LLM synthesis. Với câu đơn giản, Day 08 có thể nhanh và gọn hơn.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Trần Trung Kiên | Supervisor routing trong `graph.py` | Sprint 1 |
| Trần Trung Kiên | Retrieval, policy, synthesis workers | Sprint 2 |
| Trần Trung Kiên | MCP mock tools và policy worker integration | Sprint 3 |
| Trần Trung Kiên | Eval trace, architecture docs, routing log, comparison, report | Sprint 4 |

**Điều nhóm làm tốt:**

Hệ thống chạy được end-to-end với 15/15 test questions, trace rõ và có MCP/HITL evidence. Các report/docs dựa trên trace thật thay vì giả định.

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**

Vì nhóm chỉ có một người, mọi phần phụ thuộc vào cùng một người nên dễ bị bottleneck. Về kỹ thuật, routing còn keyword-based và confidence còn heuristic.

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**

Nếu có thêm người, nên tách rõ một người phụ trách routing/trace và một người phụ trách policy/MCP để review chéo các câu multi-hop khó.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

Nhóm sẽ cải thiện policy worker để gọi `check_access_permission` có cấu trúc cho mọi câu access level, đặc biệt các câu Level 2/Level 3 emergency. Ngoài ra, nhóm sẽ thêm LLM/structured router để ghi matched keywords cụ thể trong `route_reason` và giảm rủi ro miss paraphrase.
