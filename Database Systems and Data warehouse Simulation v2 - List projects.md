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

## 1) Raft from scratch + production features

- Vấn đề dữ liệu: durable WAL, snapshotting, log compaction, membership change.
- Thách thức DB: đảm bảo **snapshot + log truncation** không làm mất commit; MVCC hoặc single-writer log layout; stable storage ordering; leader transfer correctness.
- Vận hành: checkpoint frequency trade-off (recovery time vs throughput); backup snapshot consistency; repair/replay scripts.
- Test/metrics: linearizability checks (history), follower catch-up latency, snapshot install time, WAL growth under heavy write; simulate disk stalls + leader crash.

## 2) Distributed KV store (tunable CP vs AP)

- Vấn đề: giao diện read/write với chế độ consistency có thể đổi được.
- Thách thức DB: implement multi-model replication (Raft) và leaderless quorum; read repair, vector clocks or version vectors for conflict detection; tombstone/GC.
- Vận hành: compaction policy control cho tombstones; per-key TTL; metrics per consistency-mode.
- Test: partition scenarios comparing latency/availability; staleness windows; conflict resolution correctness.

## 3) Commit-log service (Kafka-like)

- Vấn đề: durable append, partitioning, offsets, retention & compaction, consumer groups.
- Thách thức DB: segment roll, compaction pauses, index maintenance, leader/follower replica sync, exactly-once semantics (producer idempotence + transactions).
- Vận hành: offline/online log compaction, disk space reclamation, broker recovery time.
- Test: broker crash during commit, compaction vs reader race, end-to-end exactly-once with producer restarts; measure retention reclaim latency.

## 4) Geo-replicated datastore + CRDTs

- Vấn đề: convergence, delta-CRDT design, anti-entropy efficiency.
- Thách thức DB: bandwidth-efficient anti-entropy, tombstone semantics for deletes, state size growth, causal delivery vs eventually-consistent merges.
- Vận hành: cross-region replication lag/throughput, conflict resolution observability, snapshotting for cold regions.
- Test: region outage + re-merge; divergence window measurement; memory growth under high-update churn.

## 5) Stateful stream processing + exactly-once

- Vấn đề: durable operator state + checkpointing + state migration.
- Thách thức DB: efficient incremental checkpoints, externalized state backend (RocksDB) compaction, EOS across stream + DB (idempotency/outbox + atomic commit).
- Vận hành: checkpoint cadence vs latency; restore determinism; state size growth and rebalancing cost.
- Test: worker crash during checkpoint, state transfer time, end-to-end duplicate suppression metrics.

## 6) Distributed cache (consistent hashing + hot-key mitigation)

- Vấn đề: cache coherence, eviction policies, multi-tiered storage.
- Thách thức DB: rehashing amplification (replication factor impact), cache warmup patterns, request coalescing, stale read windows.
- Vận hành: cold-start mitigation, memory pressure handling, eviction storms, cache instrumentation (hit/miss per-key).
- Test: node join/leave with hot keys, burst traffic causing stampede, measure tail latency P99.

## 7) k8s operator + SRE pipeline (apply to DBs)

- Vấn đề: operator for stateful DBs (backup, restore, rolling upgrades).
- Thách thức DB: safe schema migration operators, operator-driven backups/PITR, pod eviction + quorum maintenance, operator reconcilers correctness.
- Vận hành: automated canary for DB schema+engine upgrades, backup verification, restore drill.
- Test: operator race conditions (reconcile loops), upgrade rollback, restore-to-point-in-time validation.

## 8) Chaos lab: Jepsen-style analyses

- Vấn đề: correctness under combined faults.
- Thách thức DB: specifying invariants (serializability/linearizability/causal), building harness that can inject disk/network/process faults while capturing histories.
- Vận hành: reproducible test harness, retention of full event history.
- Test: run partition+disk-corruption schedules; produce written RCA with minimal repro.

## 9) Multi-tenant scheduler / distributed job orchestration

- Vấn đề: persistent job metadata, leases, resource accounting.
- Thách thức DB: high-cardinality tenant metadata, multi-tenancy isolation (rate limiting/query cgroup), durable lease revocation/heartbeating.
- Vận hành: per-tenant quotas, soft vs hard limits in storage, tenant-level backup/restore.
- Test: tenant noisy-neighbor emulation, metadata DB failover impact on scheduling.

## 10) Distributed rate limiter + global backpressure

- Vấn đề: accurate global counters with low latency.
- Thách thức DB: centralized counter hot-spot; approximate counters (sketches) correctness vs error bounds; clock skew handling for token bucket windows.
- Vận hành: storage throttling, resilience when counters partitioned, per-tenant keys lifecycle.
- Test: partial outage of counter shard, error-bound verification, degrade mode behavior.
