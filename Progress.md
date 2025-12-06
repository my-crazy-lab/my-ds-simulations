# ✅ Payments / Acquiring Gateway (PCI DSS, tokenization, fraud mitigation) 

**Mục tiêu:** Build an acquiring gateway that accepts card transactions, tokenizes PAN, routes to acquirers, supports 3D Secure flow, and retry/settlement.

**Vấn đề production:** PCI-scope minimization, high throughput for peak shopping events, idempotent processing, dispute chargebacks, retries to external PSPs, sharding of sensitive data.

- **Vấn đề**: tokenization, idempotency, PCI scope minimization.
- **Thách thức DB**: separation of sensitive vs non-sensitive data (token vault), secure key management, high-throughput small writes (token create, auth), guaranteed-once settlement records.
- **Vận hành**: HSM integration testing, purge/retention for PANs, strict logging without leakage.
- **Test**: simulate PSP retries; ensure exactly-once settlement records; verify logs contain no PANs.

- **Vị trí**: `payments-acquiring-gateway/`
- **Database Tests**: `tests/database/test_tokenization_pci.py` (8 test functions)
- **Thành phần chính**:
  - Secure card tokenization với PCI scope minimization
  - Exactly-once settlement record creation với idempotency
  - PCI-compliant audit logging (không có sensitive data trong logs)
  - PSP retry scenarios với idempotency guarantees
  - Luhn algorithm validation cho test card generation
- **Công nghệ**: Go, PostgreSQL, Redis, Kafka, Docker Compose
- **Makefile**: 57 automation targets bao gồm PCI compliance checks
- **Tài liệu**: 535 dòng README toàn diện
- **Hiệu suất**: Xử lý millions payment transactions hàng ngày
- **Tuân thủ**: PCI DSS Level 1, strong encryption, no PAN leakage
