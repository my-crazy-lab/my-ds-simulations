# Commit-log Service & State Reconstruction

A production-grade distributed commit log service similar to Apache Kafka, featuring durable append-only logs, consumer groups, retention policies, log compaction, and complete state reconstruction capabilities.

## 🎯 **Project Goals**

Build a distributed commit log system with:
- **Durable Append-Only Logs**: Immutable, ordered sequence of records
- **Consumer Groups**: Scalable message consumption with load balancing
- **Retention & Compaction**: Configurable retention policies and log compaction
- **State Reconstruction**: Complete application state rebuilding from commit logs
- **Partition Leadership**: Leader/follower model for high availability
- **Exactly-Once Semantics**: Idempotent producers and transactional consumers

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                        Producers                                │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│                    Commit Log Cluster                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │   Broker 1  │    │   Broker 2  │    │   Broker 3  │        │
│  │             │    │             │    │             │        │
│  │ Topic A     │    │ Topic A     │    │ Topic A     │        │
│  │ Partition 0 │◄──►│ Partition 1 │◄──►│ Partition 2 │        │
│  │ (Leader)    │    │ (Follower)  │    │ (Leader)    │        │
│  │             │    │             │    │             │        │
│  │ Topic B     │    │ Topic B     │    │ Topic B     │        │
│  │ Partition 0 │    │ Partition 0 │    │ Partition 0 │        │
│  │ (Follower)  │    │ (Leader)    │    │ (Follower)  │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│                    Consumer Groups                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │ Consumer    │    │ Consumer    │    │ Consumer    │        │
│  │ Group A     │    │ Group B     │    │ Group C     │        │
│  │             │    │             │    │             │        │
│  │ - Consumer1 │    │ - Consumer1 │    │ - Consumer1 │        │
│  │ - Consumer2 │    │ - Consumer2 │    │ - Consumer2 │        │
│  │ - Consumer3 │    │             │    │             │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 **Features**

### Core Commit Log Features
- **Append-Only Logs**: Immutable, ordered message sequences
- **Partitioning**: Horizontal scaling with configurable partition count
- **Replication**: Configurable replication factor with leader/follower model
- **Durability**: Configurable flush policies and acknowledgment levels

### Consumer Features
- **Consumer Groups**: Load balancing across multiple consumers
- **Offset Management**: Automatic and manual offset tracking
- **Rebalancing**: Dynamic partition assignment on consumer join/leave
- **Exactly-Once**: Idempotent consumption with transactional semantics

### Advanced Features
- **Log Compaction**: Key-based compaction for state reconstruction
- **Retention Policies**: Time-based and size-based retention
- **Schema Evolution**: Backward/forward compatible message schemas
- **Transactions**: Multi-partition atomic writes

### Operational Features
- **Monitoring**: Comprehensive metrics for throughput, latency, lag
- **Administration**: Topic/partition management, consumer group monitoring
- **Backup/Restore**: Point-in-time recovery and cross-cluster replication
- **Security**: Authentication, authorization, and encryption

## 🛠️ **Technology Stack**

- **Language**: Go 1.21+ with high-performance I/O and concurrency
- **Storage**: Segmented log files with memory-mapped I/O for performance
- **Networking**: gRPC for inter-broker communication, HTTP for admin API
- **Coordination**: Integrated with existing infrastructure for leader election
- **Serialization**: Protocol Buffers with schema registry integration
- **Monitoring**: Prometheus metrics, Grafana dashboards, distributed tracing

## 📋 **Implementation Checklist**

### Phase 1: Core Log Storage ✅
- [x] Segmented log file implementation
- [x] Memory-mapped I/O for high performance
- [x] Configurable segment size and retention
- [x] Atomic append operations
- [x] Index files for fast offset lookups

### Phase 2: Partitioning & Replication ✅
- [x] Topic and partition management
- [x] Leader/follower replication model
- [x] In-sync replica (ISR) management
- [x] Configurable replication factor
- [x] Partition reassignment capabilities

### Phase 3: Producer API ✅
- [x] High-level producer API
- [x] Batching and compression
- [x] Configurable acknowledgment levels
- [x] Idempotent producers
- [x] Transactional producers

### Phase 4: Consumer Groups ✅
- [x] Consumer group coordination
- [x] Partition assignment strategies
- [x] Offset management and commits
- [x] Consumer rebalancing
- [x] Exactly-once consumption

### Phase 5: Advanced Features ✅
- [x] Log compaction implementation
- [x] Retention policy enforcement
- [x] Schema registry integration
- [x] State reconstruction utilities
- [x] Cross-datacenter replication

## 🧪 **Testing Strategy**

### Functional Testing
- **Producer Tests**: Message ordering, durability, idempotency
- **Consumer Tests**: Group coordination, rebalancing, offset management
- **Replication Tests**: Leader election, follower synchronization
- **Compaction Tests**: Key-based compaction correctness

### Performance Testing
- **Throughput**: Messages per second under various loads
- **Latency**: End-to-end message delivery latency
- **Scalability**: Performance with increasing partitions/consumers
- **Resource Usage**: Memory, disk, and network utilization

### Reliability Testing
- **Fault Tolerance**: Broker failures, network partitions
- **Data Integrity**: Message ordering and durability guarantees
- **Recovery**: State reconstruction from commit logs
- **Chaos Engineering**: Random failure injection

## 📊 **Performance Targets**

### Throughput
- **Single Partition**: 100,000+ messages/second
- **Multi-Partition**: 1,000,000+ messages/second (cluster)
- **Batch Processing**: 10MB/second sustained throughput

### Latency
- **Producer Latency**: <5ms (async), <50ms (sync)
- **Consumer Latency**: <10ms end-to-end
- **Replication Latency**: <20ms follower lag

### Scalability
- **Partitions**: 1000+ partitions per broker
- **Consumers**: 100+ consumers per group
- **Topics**: 100+ topics per cluster

## 🚀 **Quick Start**

```bash
# Build and start the commit log cluster
make build
make start-cluster

# Create a topic
curl -X POST http://localhost:8080/admin/topics \
  -d '{"name": "events", "partitions": 3, "replication_factor": 2}'

# Produce messages
curl -X POST http://localhost:8080/produce/events \
  -d '{"messages": [
    {"key": "user1", "value": "login"},
    {"key": "user2", "value": "purchase"}
  ]}'

# Consume messages
curl http://localhost:8080/consume/events?group=processors

# Run comprehensive tests
make test-comprehensive
```

## 📖 **API Examples**

### Producer Operations
```bash
# Produce single message
curl -X POST http://localhost:8080/produce/events \
  -d '{"key": "order123", "value": "{\"amount\": 100}", "partition": 0}'

# Produce batch of messages
curl -X POST http://localhost:8080/produce/events \
  -d '{"messages": [
    {"key": "user1", "value": "event1"},
    {"key": "user2", "value": "event2"}
  ]}'

# Transactional produce
curl -X POST http://localhost:8080/produce/events?transactional=true \
  -d '{"transaction_id": "tx123", "messages": [...]}'
```

### Consumer Operations
```bash
# Join consumer group
curl -X POST http://localhost:8080/consumers/group1 \
  -d '{"consumer_id": "consumer1", "topics": ["events"]}'

# Consume messages
curl http://localhost:8080/consume/events?group=group1&consumer=consumer1

# Commit offsets
curl -X POST http://localhost:8080/consumers/group1/consumer1/offsets \
  -d '{"offsets": [{"partition": 0, "offset": 100}]}'
```

### Admin Operations
```bash
# List topics
curl http://localhost:8080/admin/topics

# Topic details
curl http://localhost:8080/admin/topics/events

# Consumer group status
curl http://localhost:8080/admin/consumer-groups/group1

# Trigger log compaction
curl -X POST http://localhost:8080/admin/topics/events/compact
```

## 🔍 **Monitoring & Observability**

### Metrics (Prometheus)
- `commitlog_messages_produced_total`: Total messages produced
- `commitlog_messages_consumed_total`: Total messages consumed
- `commitlog_partition_size_bytes`: Partition size in bytes
- `commitlog_consumer_lag`: Consumer lag per partition
- `commitlog_replication_lag_ms`: Replication lag in milliseconds

### Dashboards
- **Cluster Overview**: http://localhost:3000/d/commitlog-cluster
- **Producer Metrics**: http://localhost:3000/d/commitlog-producers
- **Consumer Metrics**: http://localhost:3000/d/commitlog-consumers
- **Replication Health**: http://localhost:3000/d/commitlog-replication

### State Reconstruction
- **Snapshot Creation**: Point-in-time state snapshots
- **Replay Utilities**: Fast state reconstruction from logs
- **Consistency Checks**: Verify reconstructed state integrity

## 🎯 **Acceptance Criteria**

- ✅ **Durability**: No message loss under configured replication
- ✅ **Ordering**: Strict ordering within partitions
- ✅ **Scalability**: Linear scaling with partition count
- ✅ **Exactly-Once**: Idempotent producers and consumers
- ✅ **State Reconstruction**: Complete application state rebuilding
- ✅ **Performance**: Meet throughput and latency targets

## 📚 **References**

- [Apache Kafka](https://kafka.apache.org/) - Distributed streaming platform
- [Kafka Paper](https://notes.stephenholiday.com/Kafka.pdf) - Original Kafka design
- [Log Structured Storage](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying) - Log-centric architecture
- [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html) - State reconstruction patterns
