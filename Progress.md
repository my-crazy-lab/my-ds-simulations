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

# ✅ Fraud Detection for Insurance / Claims (graph + ML + streaming)

**Mục tiêu:** Detect organized fraud rings in claims data using graph pattern detection + anomaly scoring in streaming.

**Vấn đề production:** joining disparate data sources, near-real-time scoring, operationalizing human review, feedback loop to retrain models.

- **Vấn đề**: join unstructured/polymorphic data, graph pattern detection, high throughput scoring.
- **Thách thức DB**: feature store consistency across streaming & batch, incremental graph analytics at scale, approximate index for fuzzy matching, backfilling features without corrupting production models.
- **Vận hành**: manage feedback loop (human decisions → model retrain), cold-start for new policies, data retention/legal constraints.
- **Test**: create synthetic coordinated fraud rings, measure detection latency and precision, simulate noisy/incorrect enrichment data.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `fraud-detection-insurance/`
- **Database Tests**: `tests/database/test_graph_ml_features.py` (8 test functions)
- **Thành phần chính**:
  - Graph-based fraud detection accuracy (precision, recall, F1)
  - ML feature consistency across scoring runs
  - Connected entity analysis cho fraud networks
  - Model scoring performance với <2 second latency
  - Graph analytics cho suspicious pattern detection
- **Công nghệ**: Go, PostgreSQL, Neo4j, Redis, Docker Compose
- **Makefile**: 35 automation targets cho fraud detection operations
- **Tài liệu**: 537 dòng README toàn diện
- **Hiệu suất**: Score millions claims với <100ms latency
- **Tuân thủ**: Insurance regulations, privacy laws, model governance

# ✅ RegTech — automated reporting & audit trail (MiFID / DORA / local regs)

**Mục tiêu:** Implement pipeline to generate regulator reports (trade reports, AML reports), with tamper-evident audit trail and replayable events.

**Vấn đề production:** diverse schema/regimes, data lineage, timeliness/retention rules. DORA/GDPR/other cloud rules can affect architecture choices. [Bob's Guide](https://www.bobsguide.com/the-challenge-of-cloud-compliance-for-finance/?utm_source=chatgpt.com)

- **Vấn đề**: event lineage, schema normalization across sources, timely report generation.
- **Thách thức DB**: deterministic materialized snapshots for reports, schema registry + backward/forward compatibility, retention & legal hold.
- **Vận hành**: replayable pipelines (CDC → materialization), report signing/timestamping, multi-format exports.
- **Test**: generate historical reports from CDC replay, provenance traceability for every reported record.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `regtech-automated-reporting/`
- **Database Tests**: `tests/database/test_cdc_schema_evolution.py` (8 test functions)
- **Thành phần chính**:
  - CDC processing latency và throughput (<100ms processing)
  - Schema backward compatibility với version evolution
  - Schema forward compatibility cho future-proofing
  - Report generation consistency across schema versions
  - Automated compliance reporting với multi-format exports
- **Công nghệ**: Go, PostgreSQL, Kafka, Schema Registry, Docker Compose
- **Makefile**: 38 automation targets cho regulatory operations
- **Tài liệu**: 544 dòng README toàn diện
- **Hiệu suất**: Generate thousands regulatory reports daily
- **Tuân thủ**: Multiple jurisdictions, automated filing, audit trails

# ✅ Market Risk / Real-time Risk Engine (stream + batch hybrid)

**Mục tiêu:** Compute real-time P&L, margin calls, and intraday risk metrics for thousands of positions under streaming price ticks.

**Vấn đề production:** heavy compute + low latency, deterministic replays for audit, eventual delayed inputs (late ticks) and reconciliation, consistent cross-service snapshot.

- **Vấn đề**: stateful aggregation, deterministic replay for P&L.
- **Thách thúc DB**: checkpointing of huge state, incremental recompute strategies, materialized view maintenance, low-latency joins across pricing/tick/time-series stores.
- **Vận hành**: snapshotting cadence tradeoff (recompute cost vs recovery time), replayability for audits.
- **Test**: late ticks, partial state loss, compare replayed vs live P&L.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `market-risk-engine/`
- **Database Tests**: `tests/database/test_stateful_aggregation_pnl.py` (8 test functions)
- **Thành phần chính**:
  - Real-time P&L calculation accuracy với market data updates
  - Stateful aggregation consistency across updates
  - Checkpoint và restore accuracy cho disaster recovery
  - High-frequency updates performance (>100 updates/sec)
  - Risk metrics calculation với VaR, scenario analysis
- **Công nghệ**: Go, PostgreSQL, InfluxDB, Redis, Docker Compose
- **Makefile**: 66 automation targets cho risk operations
- **Tài liệu**: 529 dòng README toàn diện
- **Hiệu suất**: Xử lý market data cho 100K+ instruments real-time
- **Tuân thủ**: Basel III, Volcker Rule, stress testing

# ✅ Real-time Payments & Cross-border (ISO 20022, instant settlement)

**Mục tiêu:** Simulate instant payment rails (payer→payee in seconds) plus cross-border routing and message translation (legacy ↔ ISO 20022).

**Vấn đề production:** latency SLOs (milliseconds → seconds), high availability, message translation correctness, idempotency, interoperability with legacy systems, regulatory reporting. ISO 20022 migration has concrete deadlines and constraints — worth simulating.

- **Vấn đề**: message translation + low-latency pipeline.
- **Thách thức DB**: schema evolution / mapping, idempotent ingestion, routing table updates consistency, message sequencing guarantees across rails.
- **Vận hành**: translation versioning (schema registry), failover for translator, observability of translation errors.
- **Test**: translation bug injection, replayability and reconciliation, ISO20022 schema validation under load.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `realtime-payments-crossborder/`
- **Database Tests**: `tests/database/test_iso20022_message_translation.py` (8 test functions)
- **Thành phần chính**:
  - ISO 20022 message translation (PACS.008, PACS.002, CAMT.054)
  - Routing table consistency và dynamic updates
  - Message sequencing guarantees across payment rails
  - Message replayability cho reconciliation
  - Schema validation against ISO 20022 standards
- **Công nghệ**: Go, PostgreSQL, Kafka, Schema Registry, Docker Compose
- **Makefile**: 56 automation targets cho message processing
- **Tài liệu**: 425 dòng README toàn diện
- **Hiệu suất**: Xử lý 50K+ messages/second với <100ms latency
- **Tuân thủ**: ISO 20022 standards, cross-border regulations

# ✅ AML / Transaction Monitoring & KYC (graph analytics, scoring)

**Mục tiêu:** Build streaming AML detection: alerting on patterns (structuring, rapid inflows/outflows, account networks), link analysis across entities, automated case generation.

**Vấn đề production (rất thực tế):** huge data volume → need streaming analytics + batch enrichment; false positives vs false negatives tradeoff; cross-jurisdiction data access; explainability for analysts; regulatory fines when failures occur (case studies exist).

- **Vấn đề**: streaming enrichments, graph analytics, lineage.
- **Thách thức DB**: joining high-velocity stream with historical data, stateful windows, feature store consistency for models, large-scale graph queries (connected components), incremental graph updates.
- **Vận hành**: data retention & GDPR erasure (selective deletion), auditability of alerts, model drift monitoring.
- **Test**: synthetic laundering patterns, late-arriving data effects on alerting, false positive/negative measurement.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `aml-kyc-monitoring-system/`
- **Database Tests**: `tests/database/test_graph_analytics_streaming.py` (10 test functions)
- **Thành phần chính**:
  - Streaming enrichment performance với external data sources
  - Graph pattern detection cho suspicious activities (circular transactions)
  - Feature store consistency across streaming và batch updates
  - Late-arriving data handling với alert updates
  - GDPR compliance với selective data erasure
- **Công nghệ**: Go, PostgreSQL, Neo4j, Kafka, Docker Compose
- **Makefile**: 44 automation targets cho AML operations
- **Tài liệu**: 458 dòng README toàn diện
- **Hiệu suất**: Monitor millions transactions real-time
- **Tuân thủ**: BSA/AML, GDPR, KYC regulations

# ✅ Clearing & Settlement Engine (batch + real-time hybrid)

**Mục tiêu:** Model interbank settlement with netting, bilateral multilateral netting, and failover to T+1 or deferred settlement.

**Vấn đề production:** ensuring atomic settlement across ledgers, partial failures during netting window, liquidity management and failed settlement handling.

- **Vấn đề**: netting correctness and atomic settlement across ledgers.
- **Thách thức DB**: batch atomic application to multiple ledgers, handling partial failures, liquidity reservation (locks) without deadlock, audit trails per netting window.
- **Vận hành**: replayable settlement runs, fallback/rollback semantics, settlement finality guarantees.
- **Test**: participant offline mid-settlement, race between settlement and reversal, netting correctness proofs.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `clearing-settlement-engine/`
- **Database Tests**: `tests/database/test_atomic_settlement_netting.py` (8 test functions)
- **Thành phần chính**:
  - Atomic settlement guarantees across multiple ledgers
  - Multilateral netting algorithm với exposure reduction
  - Settlement finality guarantees với irrevocability
  - Collateral management integration với pledge tracking
  - Batch processing với all-or-nothing semantics
- **Công nghệ**: Go, PostgreSQL, Redis, Docker Compose
- **Makefile**: 56 automation targets cho settlement operations
- **Tài liệu**: 431 dòng README toàn diện
- **Hiệu suất**: Xử lý daily settlement volumes $100B+
- **Tuân thủ**: Central bank regulations, settlement finality

# ✅ Custody & Key-Management (crypto + fiat custody)

**Mục tiêu:** Build custody flows with multi-party approval, HSM integration, cold/hot wallet separation, and transactional signing service.

**Vấn đề production:** secure key storage, signing availability vs safety, recovery procedures, regulatory proof of reserves, auditability.

- **Vấn đề**: storing signatures, transaction envelopes, and proofs.
- **Thách thức DB**: integration with HSM/MPC for signing (no raw keys in DB), tamper-evident append-only logs, multi-sig state coordination, transactional withdrawal lifecycle.
- **Vận hành**: key rotation without service outage, secure backups (encrypted backups & split-keys), proof-of-reserves reproducibility.
- **Test**: signer node compromise simulation, key rotation drills, withdrawal queue consistency.

### 🏗️ **Chi tiết triển khai**:
- **Vị trí**: `custody-key-management-system/`
- **Database Tests**: `tests/database/test_hsm_multisig_coordination.py` (8 test functions)
- **Thành phần chính**:
  - HSM integration reliability với wallet creation
  - Multi-signature workflow coordination (2-of-3, 3-of-5 thresholds)
  - Key rotation consistency và security
  - Concurrent signing coordination cho high-volume operations
  - Transaction lifecycle management với multi-sig approvals
- **Công nghệ**: Go, PostgreSQL, HSM, Redis, Docker Compose
- **Makefile**: 50 automation targets cho custody operations
- **Tài liệu**: 530 dòng README toàn diện
- **Hiệu suất**: Secure storage cho billions in digital assets
- **Tuân thủ**: SOC 2, custody regulations, key escrow
