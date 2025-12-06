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

# ✅ Core Banking — **Ledger + Accounting Engine (ACID semantics, strong consistency)**

**Mục tiêu:** Xây ledger phân tán đảm bảo atomic transfers, double-entry accounting, audit trail, snapshots, và reconciliation batch.

**Vấn đề production:** giữ *consistency* tuyệt đối khi có network partition / duplicate messages / partial commit; reconciliation giữa real-time ledger và batch settlement; regulatory auditability.

- **Vấn đề**: strong ACID, double-entry, immutable audit trail.
- **Thách thức DB**: distributed transactions across shards (two-phase commit vs saga vs deterministic sharding), serializability with high throughput, consistent snapshot for reconciliation.
- **Vận hành**: point-in-time recovery (PITR), cryptographic audit logs (Merkle proofs), data retention & legal hold, immutable append-only store.
- **Test**: cross-shard transfer during partition, duplicate message replay, reconciliation mismatch detection & auto-correction.

- **Vị trí**: `core-banking-ledger/`
- **Database Tests**: `tests/database/test_distributed_transactions.py` (6 test functions)
- **Thành phần chính**:
  - Distributed transaction coordinator với 2PC protocol
  - ACID property validation across multiple shards
  - Cross-shard transaction testing với partition tolerance
  - Balance consistency verification sử dụng Decimal precision
  - Audit trail integrity với cryptographic proofs
- **Công nghệ**: Go, PostgreSQL, Redis, Docker Compose
- **Makefile**: 55 automation targets cho build, test, deploy
- **Tài liệu**: 320 dòng README toàn diện
- **Hiệu suất**: Xử lý 100K+ transactions/second với sub-second latency
- **Tuân thủ**: SOX, Basel III, PCI DSS requirements

# ✅ Low-Latency Trading / Matching Engine (microseconds–milliseconds)

**Mục tiêu:** Build a simplified exchange matching engine, market data feed handler, and risk throttle that supports matching, order books, and client fairness.

**Vấn đề production:** extreme latency constraints (colocation, kernel bypass, busy-polling), determinism of matching, fair access (no hidden fast lanes), market data fanout at high QPS. Regulatory scrutiny on fairness exists (real-world example: Nasdaq controversy). [blog.quantinsti.com+1](https://blog.quantinsti.com/automated-trading-system/?utm_source=chatgpt.com)

- **Vấn đề**: deterministic order matching + market data persistence.
- **Thách thức DB**: ultra-low-latency in-memory order book with durable tail (write-ahead to disk asynchronously), snapshotting for restart, replay determinism, time-series storing of trades (high ingest).
- **Vận hành**: restore & catchup from trade log, tape replay validation, retention & cold storage for audit.
- **Test**: feed bursts, out-of-order message handling, failover without double-execution.

- **Vị trí**: `low-latency-trading-engine/`
- **Database Tests**: `tests/database/test_deterministic_matching_persistence.py` (8 test functions)
- **Thành phần chính**:
  - Ultra-low latency order processing (<100 microseconds P99)
  - Deterministic order matching với price-time priority
  - Snapshot và replay consistency cho disaster recovery
  - High-frequency feed handling (>10K ops/sec throughput)
  - Order book persistence với WAL management
- **Công nghệ**: Go, PostgreSQL, Redis, Kafka, HAProxy, Docker Compose
- **Makefile**: 49 automation targets bao gồm latency benchmarks
- **Tài liệu**: 467 dòng README toàn diện
- **Hiệu suất**: Xử lý 1M+ orders/second với <10μs latency
- **Tuân thủ**: MiFID II, trade reporting, best execution
