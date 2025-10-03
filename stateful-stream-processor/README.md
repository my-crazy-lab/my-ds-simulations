# Stateful Stream Processing + Rebalancing

A production-grade distributed stream processing system with per-key state management, dynamic rebalancing, exactly-once processing semantics, and fault-tolerant state recovery.

## 🎯 **Project Goals**

Build a stateful stream processor with:
- **Per-Key State Management**: Partitioned state with consistent hashing and local storage
- **Dynamic Rebalancing**: Automatic partition reassignment during scaling and failures
- **Exactly-Once Processing**: Idempotent operations with transactional state updates
- **Fault-Tolerant Recovery**: State snapshots, changelog replay, and standby replicas
- **Elastic Scaling**: Horizontal scaling with minimal state migration overhead

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Stream Processing Cluster                    │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
│  Processor 1   │    │  Processor 2    │    │  Processor 3    │
│                │    │                 │    │                 │
│ ┌────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Partition 0 │ │    │ │Partition 1  │ │    │ │Partition 2  │ │
│ │State Store │ │    │ │State Store  │ │    │ │State Store  │ │
│ │Changelog   │ │    │ │Changelog    │ │    │ │Changelog    │ │
│ └────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│                │    │                 │    │                 │
│ ┌────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Partition 3 │ │    │ │Partition 4  │ │    │ │Partition 5  │ │
│ │State Store │ │    │ │State Store  │ │    │ │State Store  │ │
│ │Changelog   │ │    │ │Changelog    │ │    │ │Changelog    │ │
│ └────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Rebalance Manager   │
                    │                       │
                    │ ┌─────────────────┐   │
                    │ │ Partition Map   │   │
                    │ │ Health Monitor  │   │
                    │ │ Migration Coord │   │
                    │ └─────────────────┘   │
                    └───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    Input Streams      │
                    │                       │
                    │ ┌─────────────────┐   │
                    │ │ Stream Topic A  │   │
                    │ │ Stream Topic B  │   │
                    │ │ Stream Topic C  │   │
                    │ └─────────────────┘   │
                    └───────────────────────┘
```

## 🚀 **Features**

### Stateful Processing
- **Per-Key State**: Partitioned state management with consistent key routing
- **State Stores**: RocksDB-backed local state with efficient key-value operations
- **State Snapshots**: Point-in-time state snapshots for recovery and migration
- **Changelog Streams**: Durable state change logs for replay and replication

### Exactly-Once Semantics
- **Idempotent Processing**: Duplicate message detection and deduplication
- **Transactional Updates**: Atomic state updates with commit/rollback semantics
- **Offset Management**: Coordinated input offset and state checkpoint management
- **Failure Recovery**: Consistent state restoration from snapshots and changelogs

### Dynamic Rebalancing
- **Consistent Hashing**: Deterministic partition assignment with minimal reshuffling
- **Live Migration**: Online state migration during rebalancing with minimal downtime
- **Health Monitoring**: Automatic failure detection and partition reassignment
- **Elastic Scaling**: Add/remove processors with automatic workload redistribution

### Fault Tolerance
- **Standby Replicas**: Hot standby replicas for fast failover
- **State Replication**: Asynchronous state replication across processors
- **Recovery Mechanisms**: Multiple recovery strategies (snapshot, changelog, replica)
- **Graceful Degradation**: Partial availability during failures

## 🛠️ **Technology Stack**

- **Language**: Go 1.21+ with advanced concurrency and memory management
- **State Storage**: RocksDB with column families for different state types
- **Streaming**: Apache Kafka integration for input/output streams and changelogs
- **Coordination**: Apache Zookeeper for cluster coordination and partition assignment
- **Serialization**: Apache Avro with schema evolution support
- **Monitoring**: Comprehensive metrics for processing lag, state size, and rebalancing

## 📋 **Implementation Checklist**

### Phase 1: Core Stream Processing ✅
- [x] Stream consumer with partition assignment
- [x] Message processing pipeline with error handling
- [x] Basic state management with RocksDB
- [x] Offset tracking and commit coordination
- [x] Processing metrics and monitoring

### Phase 2: Stateful Operations ✅
- [x] Per-key state partitioning with consistent hashing
- [x] State store abstraction with CRUD operations
- [x] Changelog generation for state changes
- [x] State snapshot creation and restoration
- [x] Transactional state updates

### Phase 3: Exactly-Once Processing ✅
- [x] Message deduplication with idempotency keys
- [x] Transactional processing with atomic commits
- [x] Coordinated offset and state checkpointing
- [x] Failure detection and recovery mechanisms
- [x] End-to-end exactly-once guarantees

### Phase 4: Dynamic Rebalancing ✅
- [x] Partition assignment with consistent hashing
- [x] Health monitoring and failure detection
- [x] Live state migration during rebalancing
- [x] Rebalancing coordination and synchronization
- [x] Minimal downtime during topology changes

### Phase 5: Advanced Features ✅
- [x] Standby replicas for fast failover
- [x] State replication across processors
- [x] Multiple recovery strategies
- [x] Elastic scaling with automatic rebalancing
- [x] Performance optimization and tuning

## 🧪 **Testing Strategy**

### Functional Testing
- **State Consistency**: Verify state updates are applied correctly
- **Exactly-Once**: Validate no duplicate processing under failures
- **Rebalancing**: Test partition migration and state transfer
- **Recovery**: Validate recovery from various failure scenarios

### Performance Testing
- **Throughput**: Messages processed per second under load
- **Latency**: End-to-end processing latency including state operations
- **State Size**: Performance with large state stores
- **Rebalancing Overhead**: Impact of rebalancing on processing performance

### Fault Tolerance Testing
- **Processor Failures**: Single and multiple processor failures
- **Network Partitions**: Coordination failures and split-brain scenarios
- **State Corruption**: Recovery from corrupted state stores
- **Cascading Failures**: System behavior under multiple simultaneous failures

### Chaos Engineering
- **Random Failures**: Inject random processor and network failures
- **State Migration**: Force frequent rebalancing to test migration
- **Resource Exhaustion**: Test behavior under memory and disk pressure
- **Clock Skew**: Test timestamp-based operations under clock drift

## 📊 **Performance Targets**

### Throughput
- **Message Processing**: 100,000+ messages/second per processor
- **State Operations**: 50,000+ state reads/writes per second
- **Rebalancing**: Complete rebalancing in <60 seconds for 1TB state

### Latency
- **Processing Latency**: <10ms p99 for stateless operations
- **State Access**: <1ms p99 for local state reads
- **Rebalancing**: <30 seconds downtime during planned rebalancing

### Scalability
- **Horizontal Scaling**: Linear scaling up to 100 processors
- **State Size**: Support up to 10TB of state per processor
- **Partition Count**: Support up to 10,000 partitions per cluster

## 🚀 **Quick Start**

```bash
# Build and start the stream processing cluster
make build
make start-cluster

# Create input stream topic
curl -X POST http://localhost:8080/admin/topics \
  -d '{"name": "user_events", "partitions": 12, "replication_factor": 2}'

# Start stream processors
curl -X POST http://localhost:8080/processors \
  -d '{"processor_id": "processor-1", "input_topics": ["user_events"]}'

# Send test messages
curl -X POST http://localhost:8080/streams/user_events \
  -d '{"key": "user123", "value": {"event": "login", "timestamp": 1640995200}}'

# Check processing status
curl http://localhost:8080/processors/processor-1/status

# Run comprehensive tests
make test-comprehensive
```

## 📖 **API Examples**

### Stream Processing Operations
```bash
# Create processor
curl -X POST http://localhost:8080/processors \
  -d '{"processor_id": "analytics", "input_topics": ["events"], "state_stores": ["user_sessions"]}'

# Get processor status
curl http://localhost:8080/processors/analytics/status

# Query state store
curl http://localhost:8080/processors/analytics/state/user_sessions/user123

# Trigger rebalancing
curl -X POST http://localhost:8080/admin/rebalance
```

### State Management
```bash
# Create state store
curl -X POST http://localhost:8080/state-stores \
  -d '{"name": "user_profiles", "type": "key_value", "changelog_topic": "user_profiles_changelog"}'

# Query state
curl http://localhost:8080/state-stores/user_profiles/user456

# Create snapshot
curl -X POST http://localhost:8080/state-stores/user_profiles/snapshots

# List snapshots
curl http://localhost:8080/state-stores/user_profiles/snapshots
```

### Administrative Operations
```bash
# Cluster status
curl http://localhost:8080/admin/cluster/status

# Partition assignment
curl http://localhost:8080/admin/partitions

# Rebalancing status
curl http://localhost:8080/admin/rebalance/status

# Health check
curl http://localhost:8080/health
```

## 🔍 **Monitoring & Observability**

### Metrics (Prometheus)
- `stream_processor_messages_processed_total`: Total messages processed by processor
- `stream_processor_processing_latency_seconds`: Message processing latency
- `stream_processor_state_size_bytes`: Size of state stores
- `stream_processor_rebalancing_duration_seconds`: Time spent rebalancing
- `stream_processor_exactly_once_violations_total`: Exactly-once violations detected

### Dashboards
- **Processing Overview**: http://localhost:3000/d/stream-processor-overview
- **State Management**: http://localhost:3000/d/stream-processor-state
- **Rebalancing**: http://localhost:3000/d/stream-processor-rebalancing
- **Exactly-Once**: http://localhost:3000/d/stream-processor-exactly-once

### Distributed Tracing
- **End-to-End Processing**: Trace messages from input to output
- **State Operations**: Detailed tracing of state reads and writes
- **Rebalancing**: Trace partition migration and state transfer

## 🎯 **Use Cases**

### Real-Time Analytics
- **Session Aggregation**: Track user sessions with stateful windowing
- **Fraud Detection**: Maintain user behavior profiles for anomaly detection
- **Recommendation Systems**: Update user preferences in real-time

### Event Sourcing
- **State Reconstruction**: Rebuild application state from event streams
- **CQRS Implementation**: Maintain read models from command events
- **Audit Trails**: Process and index audit events with state correlation

### Stream Joins
- **Enrichment**: Join streams with reference data stored in state
- **Temporal Joins**: Join events within time windows using state
- **Complex Event Processing**: Detect patterns across multiple streams

## 🎯 **Acceptance Criteria**

- ✅ **Exactly-Once Processing**: No duplicate processing under failures
- ✅ **State Consistency**: State updates are atomic and consistent
- ✅ **Dynamic Rebalancing**: Automatic rebalancing with minimal downtime
- ✅ **Fault Tolerance**: Recovery from processor and network failures
- ✅ **Performance**: Meets throughput and latency targets
- ✅ **Scalability**: Linear scaling with number of processors

## 📚 **References**

- [Apache Kafka Streams](https://kafka.apache.org/documentation/streams/)
- [Apache Flink State Management](https://flink.apache.org/features/2018/01/30/state-evolution.html)
- [Exactly-Once Semantics in Stream Processing](https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/)
- [Consistent Hashing](https://en.wikipedia.org/wiki/Consistent_hashing)
- [State Machine Replication](https://en.wikipedia.org/wiki/State_machine_replication)
