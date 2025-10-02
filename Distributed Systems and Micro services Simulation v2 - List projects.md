# Distributed Systems and Micro services Simulations 

## Checklist hạ tầng & tooling (cần chuẩn bị trước khi bắt tay)

- Environment: local k8s (kind/minikube/k3s) + 3+ VM nodes (Vagrant / cloud) để test real network partitions.
- Tooling fault injection: `tc`/`netem`, `iptables`, Chaos Mesh / Chaos Monkey, Jepsen (dùng để viết test correctness). [GitHub+1](https://github.com/jepsen-io/jepsen?utm_source=chatgpt.com)
- Observability: Prometheus + Grafana + OpenTelemetry/Jaeger + central log (Loki/ELK). [Tigera - Creator of Calico](https://www.tigera.io/learn/guides/devsecops/platform-engineering-on-kubernetes/?utm_source=chatgpt.com)
- Load / perf: wrk/nginxbench, go-bench, rps generators, and pprof/perf for profiling.
- Storage: local SSD/devices to simulate disk slowdowns, use cgroups to limit IOPS.
- CI: pipeline để chạy smoke tests + chaos scenarios in pre-prod.

---

## Danh sách project (tăng dần độ khó — làm theo thứ tự sẽ rất có hệ thống)

## 1) Raft *from scratch* + production features

**Goal:** Từ cốt lõi: implement Raft (leader election, log replication) rồi mở rộng snapshotting, log compaction, membership change.

**Why hard/real:** các edge-case trong membership change, snapshotting, log truncation, leader transfer thường gây split-brain hoặc data loss nếu xử lý sai. Raft paper là tài liệu chuẩn để tham khảo. [raft.github.io](https://raft.github.io/raft.pdf?utm_source=chatgpt.com)

**Stack:** Go (recommended) hoặc Rust, gRPC, RocksDB/Badger for WAL.

**Failure scenarios to test:** leader crash during AppendEntries, network partitions isolating majority, slow disk causing follower lag, snapshot install under load.

**Acceptance tests:** linearizability tests (use Jepsen-style harness), recover from minority failure w/o data loss, commit latency SLOs under load. [GitHub](https://github.com/jepsen-io/jepsen?utm_source=chatgpt.com)

**Extensions:** implement membership reconfiguration (joint consensus), integrate with k8s operator to auto-scale cluster.

---

## 2) Distributed KV store with tunable consistency (CP vs AP experiments)

**Goal:** Build KV store that can run in different modes: strongly consistent (CP, via Raft) and eventually consistent (AP, via leaderless quorum + hinted handoff).

**Why hard/real:** so sánh trade-offs (latency vs availability vs throughput) bằng experiments; need to design client API that exposes consistency SLAs.

**Stack:** Go + HTTP/gRPC; use Raft module from project 1 or integrate etcd for CP mode.

**Failure scenarios:** partitions, leader flapping, stale reads, read repair conflicts.

**Metrics / acceptance:** P99 latency, availability under partitions, correct conflict resolution.

**Tests:** run Jepsen-like partition tests and measure anomalies.

---

## 3) Commit-log service & state reconstruction (Kafka-like)

**Goal:** Implement small commit-log storage enabling durable append, consumer groups, retention & log compaction; then build a stateful service that rehydrates its state by replaying the log. Kafka docs and compaction semantics là nguồn tham khảo. [Apache Kafka+1](https://kafka.apache.org/documentation/?utm_source=chatgpt.com)

**Why hard/real:** retention/compaction policies, consumer lag, partition rebalancing, producer idempotence, exactly-once semantics là pain points trong production.

**Stack:** Java/Scala or Go, use existing storage engine (rocksdb) or plain files; implement partition leader/follower model.

**Failure scenarios:** broker failure during commit, split brain, compaction race with readers, under-replication.

**Acceptance:** consumers can catch up after broker loss; compaction yields correct table state; no duplicate delivery under configured semantics.

---

## 4) Geo-replicated datastore + conflict resolution (CRDTs & anti-entropy)

**Goal:** Build multi-region replication with eventual consistency and CRDT-based merge for certain objects (counters, sets), plus anti-entropy reconciliation.

**Why hard/real:** production systems need geo-read locality + conflict handling without complex operational coordination.

**Stack:** Go/Rust, gRPC, CRDT libs (or implement delta-CRDTs).

**Failure scenarios:** region outage, concurrent updates to same object, network partitions with re-merge.

**Acceptance:** convergence property holds, bounded divergence window, acceptable user perceived inconsistency.

**Tests:** run anti-entropy with high update rates; Jepsen-style check for merge correctness. [GitHub](https://github.com/jepsen-io/jepsen?utm_source=chatgpt.com)

---

## 5) Stateful stream processing + rebalancing (exactly-once processing)

**Goal:** Build a stateful stream processor that maintains per-key state, supports scaling (stateful task migration) and exactly-once semantics for outputs.

**Why hard/real:** migrating keyed state across workers with minimal downtime and without duplicates is challenging.

**Stack:** Kafka (commit log) + custom stream worker framework / or use Flink/ksql as comparison.

**Failure scenarios:** worker crash during snapshot/migration, out-of-order messages, checkpointing lost.

**Acceptance:** end-to-end exactly-once with snapshots & barrier alignment; smooth rebalancing under load.

---

## 6) Distributed cache with consistent hashing, hot-key mitigation, and tiered eviction

**Goal:** Build memcached-like cluster with consistent hashing, replication, and strategies for hot-keys (write-through, request coalescing, circuit breakers).

**Why hard/real:** caches expose operational problems: cache stampedes, rebalancing amplification, tail latency.

**Stack:** Go, groupcache / hash ring libs, Redis for L2 tier.

**Failure scenarios:** node join/leave with massive rehashing, hot-key storms, evictions under memory pressure.

**Acceptance:** low tail latency, bounded cache miss amplification; metrics for cache hit ratio under rebalances.

---

## 7) Platform engineering project: k8s operator + SRE pipeline (SLOs, canary, runbooks)

**Goal:** Package one of above systems as a k8s operator with CRDs; add SLOs, SLA-based alerts, canary & rollback automation.

**Why hard/real:** production readiness often fails because teams don't automate safe rollout, monitoring, and incident runbooks. Observability stack (Prometheus/Grafana/OpenTelemetry) is required here. [Tigera - Creator of Calico](https://www.tigera.io/learn/guides/devsecops/platform-engineering-on-kubernetes/?utm_source=chatgpt.com)

**Stack:** k8s, operator-sdk, Prometheus, Grafana, Loki, OTel, Argo Rollouts/Flagger.

**Failure scenarios:** bad rollout triggers, alerts missing, insufficient dashboards, alert fatigue.

**Acceptance:** automated canary with rollback, SLO monitoring and burn rate alerting.

---

## 8) Chaos lab: Jepsen-style analyses + reproducible reports

**Goal:** For any deployed service above, build a reproducible Jepsen-inspired test harness and run a battery of fault injections (partitions, clock skew, paused GC, disk I/O stalls). Jepsen is the standard approach to this. [GitHub+1](https://github.com/jepsen-io/jepsen?utm_source=chatgpt.com)

**Why hard/real:** production bugs often only show under combined/fuzzy faults. You need to both detect and explain them.

**Stack:** Jepsen (Clojure) or custom runner; Chaos Mesh for k8s; tc/netem for network faults.

**Outputs:** written analysis (postmortem style) showing invariants violated and steps to fix. Jepsen analyses are a good model. [jepsen.io](https://jepsen.io/analyses?utm_source=chatgpt.com)

---

## 9) Multi-tenant scheduler / distributed job orchestration

**Goal:** Build a scheduler that supports resource isolation, fair share, preemption, priority, and resilience. Compare single-leader vs leaderless schedulers.

**Why hard/real:** scheduling under variable load, eviction policies and fairness are core infra problems.

**Stack:** Go, gRPC, integrate with k8s or simulate cluster nodes.

**Failure scenarios:** master node failure, starvation, resource leaks.

**Acceptance:** jobs progress under node churn; fair share preserved.

---

## 10) Distributed rate limiter + global backpressure system

**Goal:** Design and implement a global, low-latency rate limiter/burst control across services (approximate counters, leaky/token buckets, centralized vs token-bucket per shard).

**Why hard/real:** protecting downstream dependencies across regions while maintaining user experience is subtle.

**Stack:** Redis/Redis Cluster (Lua scripts), or a CRDT counter approach; proxy integration (Envoy).

**Failure scenarios:** partial outage of rate limiter, clock skew, partitioned clients exceeding quotas.

**Acceptance:** system prevents overloads, degrades gracefully, accurate per-tenant throttling.

---

## Cách tổ chức để học & “master” thực tế (kỹ thuật học)

1. **Measure & Automate**: mỗi feature thêm phải có benchmarks + automated correctness tests (linearizability / history checking).
2. **Small experiments then scale**: proof-of-concept → add persistence → add replication → add rebalance → add chaos.
3. **Write postmortems & design docs**: cho mỗi failure scenario, viết RCA + design change.
