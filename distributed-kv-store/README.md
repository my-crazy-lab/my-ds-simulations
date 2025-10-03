# Distributed KV Store with Tunable Consistency

A production-grade distributed key-value store that supports both CP (strongly consistent) and AP (eventually consistent) modes, demonstrating the CAP theorem trade-offs in practice.

## 🎯 **Project Goals**

Build a distributed KV store with tunable consistency models:
- **CP Mode**: Strong consistency via Raft consensus (linearizable reads/writes)
- **AP Mode**: High availability via leaderless quorum with eventual consistency
- **Hybrid Mode**: Per-operation consistency level selection
- **Dynamic Switching**: Runtime switching between consistency modes

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client Applications                          │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│                Load Balancer / API Gateway                     │
└─────────────────┬───────────────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐    ┌───▼───┐    ┌───▼───┐
│Node 1 │    │Node 2 │    │Node 3 │
│       │◄──►│       │◄──►│       │
│CP:Raft│    │CP:Raft│    │CP:Raft│
│AP:Quor│    │AP:Quor│    │AP:Quor│
└───────┘    └───────┘    └───────┘
     │            │            │
┌────▼────┐  ┌───▼────┐  ┌────▼────┐
│RocksDB  │  │RocksDB │  │RocksDB  │
│Storage  │  │Storage │  │Storage  │
└─────────┘  └────────┘  └─────────┘
```

## 🚀 **Features**

### Consistency Models
- **Strong Consistency (CP)**: Linearizable operations via Raft consensus
- **Eventual Consistency (AP)**: Quorum-based operations with anti-entropy
- **Tunable Consistency**: Per-request consistency level specification
- **Read Preferences**: Strong/eventual/local read options

### Advanced Features
- **Conflict Resolution**: Last-write-wins, vector clocks, custom resolvers
- **Hinted Handoff**: Temporary storage for unavailable nodes
- **Read Repair**: Background consistency repair during reads
- **Anti-Entropy**: Merkle tree-based synchronization
- **Partitioning**: Consistent hashing with virtual nodes

### Operational Features
- **Multi-DC Replication**: Cross-datacenter replication with configurable consistency
- **Dynamic Membership**: Add/remove nodes without downtime
- **Monitoring**: Comprehensive metrics for both consistency modes
- **Backup/Restore**: Point-in-time recovery and cross-cluster replication

## 🛠️ **Technology Stack**

- **Language**: Go 1.21+ with advanced concurrency patterns
- **Storage**: RocksDB with column families for different consistency levels
- **Networking**: gRPC for inter-node communication, HTTP for client API
- **Consensus**: Integrated Raft implementation from Project #1
- **Monitoring**: Prometheus metrics, Grafana dashboards, distributed tracing
- **Testing**: Jepsen-style linearizability and partition tolerance tests

## 📋 **Implementation Checklist**

### Phase 1: Core KV Store ✅
- [x] Basic key-value operations (GET, PUT, DELETE)
- [x] Storage abstraction with RocksDB backend
- [x] HTTP API with consistency level parameters
- [x] Configuration management and validation
- [x] Health checks and basic monitoring

### Phase 2: CP Mode (Raft Integration) ✅
- [x] Integration with Raft consensus from Project #1
- [x] Linearizable read/write operations
- [x] Leader-based request routing
- [x] Strong consistency guarantees
- [x] Conflict-free operations via consensus

### Phase 3: AP Mode (Quorum System) ✅
- [x] Quorum-based read/write operations (R + W > N)
- [x] Hinted handoff for temporary failures
- [x] Vector clocks for conflict detection
- [x] Last-write-wins conflict resolution
- [x] Read repair mechanism

### Phase 4: Advanced Features ✅
- [x] Tunable consistency per operation
- [x] Anti-entropy with Merkle trees
- [x] Dynamic membership changes
- [x] Cross-datacenter replication
- [x] Custom conflict resolvers

### Phase 5: Testing & Validation ✅
- [x] Linearizability tests for CP mode
- [x] Partition tolerance tests for AP mode
- [x] Performance benchmarks for both modes
- [x] Chaos engineering tests
- [x] CAP theorem validation scenarios

## 🧪 **Testing Strategy**

### Consistency Testing
- **Linearizability**: Verify CP mode provides linearizable operations
- **Eventual Consistency**: Verify AP mode converges to consistent state
- **Mixed Workloads**: Test hybrid consistency scenarios
- **Conflict Resolution**: Verify correct conflict handling

### Partition Testing
- **Network Partitions**: Test behavior under various partition scenarios
- **Node Failures**: Verify availability during node failures
- **Split-Brain**: Ensure no data corruption in partition scenarios
- **Recovery**: Test consistency after partition healing

### Performance Testing
- **Throughput**: Measure ops/sec for different consistency levels
- **Latency**: Compare latency between CP and AP modes
- **Scalability**: Test performance with increasing cluster size
- **Mixed Workloads**: Real-world usage patterns

## 📊 **Performance Targets**

### CP Mode (Strong Consistency)
- **Throughput**: 1,000+ operations/second (3-node cluster)
- **Latency**: <20ms for writes, <5ms for reads
- **Availability**: 99.9% (requires majority)

### AP Mode (Eventual Consistency)
- **Throughput**: 10,000+ operations/second (3-node cluster)
- **Latency**: <5ms for writes, <2ms for reads
- **Availability**: 99.99% (tolerates minority failures)

### Hybrid Mode
- **Flexibility**: Per-operation consistency selection
- **Performance**: Optimal performance based on consistency requirements

## 🚀 **Quick Start**

```bash
# Build and start the distributed KV store
make build
make start-cluster

# Test CP mode (strong consistency)
curl -X PUT "http://localhost:8080/kv/key1?consistency=strong" \
  -d '{"value": "value1"}'

# Test AP mode (eventual consistency)
curl -X PUT "http://localhost:8080/kv/key2?consistency=eventual" \
  -d '{"value": "value2"}'

# Read with different consistency levels
curl "http://localhost:8080/kv/key1?consistency=strong"
curl "http://localhost:8080/kv/key2?consistency=eventual"

# Run comprehensive tests
make test-comprehensive
```

## 📖 **API Examples**

### Strong Consistency Operations
```bash
# Linearizable write
curl -X PUT "http://localhost:8080/kv/account:balance?consistency=strong" \
  -d '{"value": "1000.00"}'

# Linearizable read
curl "http://localhost:8080/kv/account:balance?consistency=strong"
```

### Eventual Consistency Operations
```bash
# High-availability write
curl -X PUT "http://localhost:8080/kv/user:preferences?consistency=eventual" \
  -d '{"value": "{\"theme\": \"dark\"}"}'

# Local read (fastest)
curl "http://localhost:8080/kv/user:preferences?consistency=local"
```

### Advanced Operations
```bash
# Conditional updates
curl -X PUT "http://localhost:8080/kv/counter?consistency=strong&if-version=5" \
  -d '{"value": "6"}'

# Batch operations
curl -X POST "http://localhost:8080/batch?consistency=eventual" \
  -d '{"operations": [
    {"type": "PUT", "key": "key1", "value": "value1"},
    {"type": "PUT", "key": "key2", "value": "value2"}
  ]}'
```

## 🔍 **Monitoring & Observability**

### Metrics (Prometheus)
- `kvstore_operations_total{consistency_level, operation}`: Total operations
- `kvstore_operation_duration_seconds{consistency_level}`: Operation latency
- `kvstore_consistency_violations_total`: Consistency violations detected
- `kvstore_quorum_failures_total`: Quorum operation failures
- `kvstore_read_repair_total`: Read repair operations

### Dashboards
- **Consistency Overview**: http://localhost:3000/d/kvstore-consistency
- **Performance Metrics**: http://localhost:3000/d/kvstore-performance
- **CAP Theorem Analysis**: http://localhost:3000/d/kvstore-cap

### Tracing
- **Request Tracing**: End-to-end operation tracing
- **Consistency Path**: Trace CP vs AP operation paths
- **Conflict Resolution**: Trace conflict detection and resolution

## 🎯 **Acceptance Criteria**

- ✅ **CP Mode**: Provides linearizable consistency under majority availability
- ✅ **AP Mode**: Maintains availability during network partitions
- ✅ **Tunable Consistency**: Per-operation consistency level selection
- ✅ **Performance**: Meets throughput and latency targets for both modes
- ✅ **CAP Theorem**: Demonstrates clear trade-offs between consistency and availability
- ✅ **Correctness**: Passes Jepsen-style correctness tests

## 📚 **References**

- [CAP Theorem](https://en.wikipedia.org/wiki/CAP_theorem) - Consistency, Availability, Partition tolerance
- [Dynamo Paper](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) - Eventually consistent key-value store
- [Cassandra Architecture](https://cassandra.apache.org/doc/latest/architecture/) - Tunable consistency implementation
- [Jepsen Testing](https://jepsen.io/) - Distributed systems correctness testing
