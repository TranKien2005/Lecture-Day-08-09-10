# Routing Decisions Log — Lab Day 09

**Nhóm:** Trần Trung Kiên  
**MSSV:** 2A202600850  
**Ngày:** 2026-06-10

> Các quyết định dưới đây lấy từ trace thật trong `artifacts/traces/` sau khi chạy `python eval_trace.py` với 15 test questions.

---

## Routing Decision #1 — SLA P1 simple retrieval

**Task đầu vào:**
> SLA xử lý ticket P1 là bao lâu?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `task contains retrieval/SLA/helpdesk keyword`  
**MCP tools được gọi:** Không  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: SLA P1 resolution là 4 giờ, first response là 15 phút.
- confidence: `0.52`
- Correct routing? Yes

**Nhận xét:**

Routing đúng vì câu hỏi chỉ cần retrieve SLA từ `support/sla-p1-2026.pdf`, không cần policy worker hay MCP. Trace `run_20260610_150200.json` ghi đủ retrieved chunks, sources và answer.

---

## Routing Decision #2 — Unknown error + HITL

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý?

**Worker được chọn:** ban đầu `human_review`, sau auto-approve về `retrieval_worker`  
**Route reason (từ trace):** `unknown error code + risk_high → human review | human approved → retrieval`  
**MCP tools được gọi:** Không  
**Workers called sequence:** `human_review → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: Không đủ thông tin trong tài liệu nội bộ để xác định ERR-403-AUTH; chỉ nêu thông tin liên quan về access request hoặc reset account.
- confidence: `0.35`
- Correct routing? Yes

**Nhận xét:**

Đây là routing quan trọng vì tránh hallucination. Supervisor nhận diện `ERR-*` là risk, bật HITL placeholder, sau đó retrieval lấy context liên quan. Synthesis abstain đúng vì tài liệu không có mã lỗi cụ thể.

---

## Routing Decision #3 — Policy/refund exception

**Task đầu vào:**
> Sản phẩm kỹ thuật số (license key) có được hoàn tiền không?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** `policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: Không được hoàn tiền vì license key/subscription là sản phẩm kỹ thuật số thuộc exception refund.
- confidence: khoảng `0.42`
- Correct routing? Yes

**Nhận xét:**

Routing đúng vì câu hỏi cần policy exception chứ không chỉ retrieve fact. Policy worker phát hiện digital product/license exception và synthesis nêu exception trước khi kết luận.

---

## Routing Decision #4 — Cross-doc access + P1 emergency

**Task đầu vào:**
> Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor. Quy trình gồm những gì?

**Worker được chọn:** `policy_tool_worker`  
**Route reason:** `task contains policy/access keyword`

**MCP tools được gọi:** `search_kb`, `get_ticket_info`  
**Workers called sequence:** `policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: Kết hợp P1 incident context và access control procedure; nêu điều kiện cấp quyền tạm thời và yêu cầu ticket/audit.
- confidence: `0.62`
- Correct routing? Yes

**Nhận xét:**

Đây là routing khó nhất vì câu hỏi chứa cả P1/SLA và access policy. Supervisor ưu tiên `policy_tool_worker` vì có `Level 2 access` và `contractor`, đồng thời policy worker gọi MCP để lấy KB/ticket info. Trace cho thấy MCP usage rate toàn run là 7/15.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8 | 53% |
| policy_tool_worker | 7 | 46% |
| human_review | 1 | 6% *(HITL là route trung gian, sau đó về retrieval)* |

### Routing Accuracy

- Câu route đúng: 15 / 15 theo review trace thủ công.
- Câu route sai: 0 / 15 trong test run hiện tại.
- Câu trigger HITL: 1 (`q09`, ERR-403-AUTH).

### Lesson Learned về Routing

1. Keyword routing đủ tốt cho corpus nhỏ nếu keywords được chọn theo domain: `p1`, `sla`, `ticket`, `remote`, `mật khẩu`, `refund`, `hoàn tiền`, `access`, `contractor`.
2. Cần route risk/unknown-code sang HITL hoặc abstain path để tránh hallucination, đặc biệt với câu hỏi như `ERR-403-AUTH`.

### Route Reason Quality

Các `route_reason` hiện đủ để debug vì nêu trực tiếp rule đã match, ví dụ `task contains retrieval/SLA/helpdesk keyword` hoặc `unknown error code + risk_high → human review`. Nếu cải tiến, có thể ghi thêm matched keyword cụ thể, ví dụ `matched=['err-']`, để debug nhanh hơn.
