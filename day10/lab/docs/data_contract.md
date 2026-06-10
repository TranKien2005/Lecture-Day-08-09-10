# Data contract — Lab Day 10

> Đồng bộ với `contracts/data_contract.yaml` và implementation trong `transform/cleaning_rules.py`.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | Raw CSV export | Stale refund window 14 ngày thay vì 7 ngày; duplicate chunks | `refund_no_stale_14d_window`, `hits_forbidden=false` |
| `sla_p1_2026` | Raw CSV export | P1 escalation bị lẫn với P2 90 phút; missing/old effective_date | `gq_d10_06 contains_expected=true`, top1 doc match |
| `it_helpdesk_faq` | Raw CSV export | Missing FAQ details như lockout/VPN | grading `gq_d10_07`, `gq_d10_08` |
| `hr_leave_policy` | Raw CSV export | HR 2025 stale annual leave 10 ngày phép năm | `hr_leave_no_stale_10d_annual`, grading `gq_d10_09` |
| `access_control_sop` | Raw CSV export | Bị thiếu khỏi allowlist baseline | `required_doc_ids_present_for_grading`, grading `gq_d10_10` |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | Hash ổn định từ `doc_id`, text, seq; dùng cho idempotent upsert/prune |
| `doc_id` | string | Có | Nằm trong allowlist: refund, SLA, FAQ, HR, access control |
| `chunk_text` | string | Có | Nội dung cleaned, không chứa stale forbidden content |
| `effective_date` | date `YYYY-MM-DD` | Có | Normalize từ ISO hoặc `DD/MM/YYYY`; invalid thì quarantine |
| `exported_at` | datetime/string | Có | Ghi lại timestamp export để freshness/lineage |

---

## 3. Quy tắc quarantine vs drop

Record không đạt rule được ghi vào `artifacts/quarantine/quarantine_<run-id>.csv` kèm `reason`, không silently drop. Các reason chính:

- `unknown_doc_id`: doc_id ngoài allowlist, gồm invalid/legacy sources.
- `missing_effective_date`: thiếu effective_date.
- `invalid_effective_date_format`: format ngày không parse được.
- `stale_hr_policy_effective_date`: HR policy cũ trước 2026.
- `stale_hr_annual_leave_10d_content`: nội dung HR stale nói 10 ngày phép năm.
- `missing_chunk_text`: chunk text rỗng.
- `duplicate_chunk_text`: duplicate nội dung.

Record được phép merge lại chỉ khi owner xác nhận source hợp lệ và cập nhật allowlist/contract tương ứng. Ví dụ `access_control_sop` là source hợp lệ nên được thêm vào allowlist và contract.

---

## 4. Phiên bản & canonical

Canonical sources:

| doc_id | Source of truth | Version rule |
|--------|-----------------|--------------|
| `policy_refund_v4` | `data/docs/policy_refund_v4.txt` | Current refund window là 7 ngày làm việc; 14 ngày bị coi là stale |
| `sla_p1_2026` | `data/docs/sla_p1_2026.txt` | P1 first response 15 phút, resolution 4 giờ, escalation 10 phút |
| `it_helpdesk_faq` | `data/docs/it_helpdesk_faq.txt` | Account lockout 5 lần, VPN 2 thiết bị |
| `hr_leave_policy` | `data/docs/hr_leave_policy.txt` | HR 2026: dưới 3 năm = 12 ngày phép năm; không dùng bản 2025 10 ngày |
| `access_control_sop` | `data/docs/access_control_sop.txt` | Level 4 Admin Access cần IT Manager và CISO |

Run chính `after-fix` đã publish đủ 5 doc_id cần grading và đạt 10/10 `GRADE_CHECK OK`.
