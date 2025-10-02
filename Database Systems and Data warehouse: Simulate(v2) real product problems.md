# Database Systems and Data warehouse Simulations 

## Gợi ý chung

1. **Định nghĩa invariants DB rõ ràng** (serializability/causal/linearizability) trước khi code. Viết tests tự động kiểm tra invariants.
2. **CDC + Outbox pattern** cho consistency giữa DB và event streams; test idempotency và dedupe.
3. **Schema registry + migration framework** (backward+forward compatible), thử migration under load (in-place vs expand-contract).
4. **Plan backup & PITR, and test restores** — thực hiện restore drills thường xuyên.
5. **Observability của lưu trữ**: WAL size, compaction time, tombstone count, write amplification, repair time, GC pause, snapshot duration.
6. **Resource isolation**: enforce IOPS/CPU quotas for DB processes to simulate noisy neighbor.
7. **Run Jepsen-style experiments**: network partition + disk stalls + clock skew + process restart combos.
8. **Measure business SLOs** (P99 latency, RPO/RTO, commit latency under churn), không chỉ throughput.
9. **Automate postmortem**: every injected failure → RCA + regression test.

## 11) Core Banking — Ledger + Accounting Engine

- Vấn đề: strong ACID, double-entry, immutable audit trail.
- Thách thức DB: distributed transactions across shards (two-phase commit vs saga vs deterministic sharding), serializability with high throughput, consistent snapshot for reconciliation.
- Vận hành: point-in-time recovery (PITR), cryptographic audit logs (Merkle proofs), data retention & legal hold, immutable append-only store.
- Test: cross-shard transfer during partition, duplicate message replay, reconciliation mismatch detection & auto-correction.

## 12) Payments / Acquiring Gateway

- Vấn đề: tokenization, idempotency, PCI scope minimization.
- Thách thức DB: separation of sensitive vs non-sensitive data (token vault), secure key management, high-throughput small writes (token create, auth), guaranteed-once settlement records.
- Vận hành: HSM integration testing, purge/retention for PANs, strict logging without leakage.
- Test: simulate PSP retries; ensure exactly-once settlement records; verify logs contain no PANs.

## 13) Real-time Payments & Cross-border (ISO 20022)

- Vấn đề: message translation + low-latency pipeline.
- Thách thức DB: schema evolution / mapping, idempotent ingestion, routing table updates consistency, message sequencing guarantees across rails.
- Vận hành: translation versioning (schema registry), failover for translator, observability of translation errors.
- Test: translation bug injection, replayability and reconciliation, ISO20022 schema validation under load.

## 14) Clearing & Settlement Engine

- Vấn đề: netting correctness and atomic settlement across ledgers.
- Thách thức DB: batch atomic application to multiple ledgers, handling partial failures, liquidity reservation (locks) without deadlock, audit trails per netting window.
- Vận hành: replayable settlement runs, fallback/rollback semantics, settlement finality guarantees.
- Test: participant offline mid-settlement, race between settlement and reversal, netting correctness proofs.

## 15) AML / Transaction Monitoring & KYC

- Vấn đề: streaming enrichments, graph analytics, lineage.
- Thách thức DB: joining high-velocity stream with historical data, stateful windows, feature store consistency for models, large-scale graph queries (connected components), incremental graph updates.
- Vận hành: data retention & GDPR erasure (selective deletion), auditability of alerts, model drift monitoring.
- Test: synthetic laundering patterns, late-arriving data effects on alerting, false positive/negative measurement.

## 16) Low-Latency Trading / Matching Engine

- Vấn đề: deterministic order matching + market data persistence.
- Thách thức DB: ultra-low-latency in-memory order book with durable tail (write-ahead to disk asynchronously), snapshotting for restart, replay determinism, time-series storing of trades (high ingest).
- Vận hành: restore & catchup from trade log, tape replay validation, retention & cold storage for audit.
- Test: feed bursts, out-of-order message handling, failover without double-execution.

## 17) Market Risk / Real-time Risk Engine

- Vấn đề: stateful aggregation, deterministic replay for P&L.
- Thách thúc DB: checkpointing of huge state, incremental recompute strategies, materialized view maintenance, low-latency joins across pricing/tick/time-series stores.
- Vận hành: snapshotting cadence tradeoff (recompute cost vs recovery time), replayability for audits.
- Test: late ticks, partial state loss, compare replayed vs live P&L.

## 18) Custody & Key-Management

- Vấn đề: storing signatures, transaction envelopes, and proofs.
- Thách thức DB: integration with HSM/MPC for signing (no raw keys in DB), tamper-evident append-only logs, multi-sig state coordination, transactional withdrawal lifecycle.
- Vận hành: key rotation without service outage, secure backups (encrypted backups & split-keys), proof-of-reserves reproducibility.
- Test: signer node compromise simulation, key rotation drills, withdrawal queue consistency.

## 19) RegTech — automated reporting & audit trail

- Vấn đề: event lineage, schema normalization across sources, timely report generation.
- Thách thức DB: deterministic materialized snapshots for reports, schema registry + backward/forward compatibility, retention & legal hold.
- Vận hành: replayable pipelines (CDC → materialization), report signing/timestamping, multi-format exports.
- Test: generate historical reports from CDC replay, provenance traceability for every reported record.

## 20) Fraud Detection for Insurance / Claims

- Vấn đề: join unstructured/polymorphic data, graph pattern detection, high throughput scoring.
- Thách thức DB: feature store consistency across streaming & batch, incremental graph analytics at scale, approximate index for fuzzy matching, backfilling features without corrupting production models.
- Vận hành: manage feedback loop (human decisions → model retrain), cold-start for new policies, data retention/legal constraints.
- Test: create synthetic coordinated fraud rings, measure detection latency and precision, simulate noisy/incorrect enrichment data.
