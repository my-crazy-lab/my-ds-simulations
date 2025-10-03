# Raft Consensus Algorithm - Production Implementation

A production-grade implementation of the Raft consensus algorithm from scratch, including leader election, log replication, snapshotting, log compaction, and membership changes.

## 🎯 **Project Goals**

Implement Raft consensus algorithm with all production features:
- **Leader Election**: Robust leader election with randomized timeouts
- **Log Replication**: Consistent log replication across cluster nodes
- **Snapshotting**: Periodic state snapshots for log compaction
- **Log Compaction**: Automatic log truncation and cleanup
- **Membership Changes**: Dynamic cluster membership reconfiguration
- **Persistence**: Durable state storage with WAL (Write-Ahead Log)

## 🏗️ **Architecture**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Raft Node 1   │    │   Raft Node 2   │    │   Raft Node 3   │
│   (Leader)      │◄──►│   (Follower)    │◄──►│   (Follower)    │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ State Machine   │    │ State Machine   │    │ State Machine   │
│ Log Storage     │    │ Log Storage     │    │ Log Storage     │
│ Persistent State│    │ Persistent State│    │ Persistent State│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Client API    │
                    │ (HTTP/gRPC)     │
                    └─────────────────┘
```

## 🚀 **Features**

### Core Raft Features
- **Leader Election**: Automatic leader election with split-vote prevention
- **Log Replication**: Consistent log replication with majority consensus
- **Safety**: Strong consistency guarantees and linearizability
- **Liveness**: Progress under network partitions (majority available)

### Production Features
- **Snapshotting**: Periodic state snapshots to reduce log size
- **Log Compaction**: Automatic log truncation after snapshots
- **Membership Changes**: Joint consensus for safe cluster reconfiguration
- **Persistence**: RocksDB/Badger for durable state storage
- **Batching**: Log entry batching for improved throughput
- **Pipelining**: Pipelined AppendEntries for reduced latency

### Operational Features
- **Metrics**: Comprehensive Prometheus metrics
- **Health Checks**: Cluster health and node status endpoints
- **Admin API**: Cluster management and debugging tools
- **Observability**: Distributed tracing with Jaeger
- **Configuration**: Dynamic configuration updates

## 🛠️ **Technology Stack**

- **Language**: Go 1.21+
- **Storage**: RocksDB (via gorocksdb) for persistent state
- **Networking**: gRPC for inter-node communication
- **API**: HTTP REST API for client operations
- **Metrics**: Prometheus metrics collection
- **Tracing**: OpenTelemetry/Jaeger integration
- **Testing**: Comprehensive test suite with chaos engineering

## 📋 **Implementation Checklist**

### Phase 1: Core Raft Algorithm ✅
- [x] Basic Raft state machine (Follower, Candidate, Leader)
- [x] Leader election with randomized timeouts
- [x] Log replication with AppendEntries RPC
- [x] RequestVote RPC implementation
- [x] Term management and vote tracking
- [x] Log consistency checks and conflict resolution

### Phase 2: Persistence & Storage ✅
- [x] Persistent state storage (currentTerm, votedFor, log)
- [x] Write-Ahead Log (WAL) implementation
- [x] State machine integration
- [x] Recovery from persistent state on restart
- [x] Log entry serialization/deserialization

### Phase 3: Production Features ✅
- [x] Snapshotting mechanism
- [x] Log compaction and truncation
- [x] Membership changes (joint consensus)
- [x] Batching and pipelining optimizations
- [x] Configuration management

### Phase 4: Operational Features ✅
- [x] HTTP API for client operations
- [x] Admin API for cluster management
- [x] Prometheus metrics integration
- [x] Health check endpoints
- [x] Distributed tracing

### Phase 5: Testing & Validation ✅
- [x] Unit tests for all components
- [x] Integration tests for cluster scenarios
- [x] Chaos engineering tests (network partitions, node failures)
- [x] Linearizability tests (Jepsen-style)
- [x] Performance benchmarks

## 🧪 **Testing Strategy**

### Unit Tests
- State machine transitions
- Log replication logic
- Election algorithms
- Persistence layer

### Integration Tests
- Multi-node cluster scenarios
- Leader election under various conditions
- Log replication with network delays
- Recovery from failures

### Chaos Tests
- Network partitions (majority/minority splits)
- Node crashes during critical operations
- Disk I/O failures and slowdowns
- Clock skew and timing issues

### Correctness Tests
- Linearizability verification
- Safety property validation
- Liveness under partition scenarios
- Consistency after recovery

## 📊 **Performance Targets**

- **Throughput**: 10,000+ operations/second (3-node cluster)
- **Latency**: <10ms commit latency (local network)
- **Recovery**: <5 seconds leader election after failure
- **Scalability**: Support 5-7 node clusters efficiently
- **Availability**: 99.9% uptime with proper majority

## 🚀 **Quick Start**

```bash
# Build the Raft implementation
make build

# Start a 3-node cluster
make start-cluster

# Run tests
make test

# Run chaos tests
make test-chaos

# Run performance benchmarks
make benchmark
```

## 📖 **API Examples**

### Client Operations
```bash
# Put a key-value pair
curl -X PUT http://localhost:8080/kv/mykey -d '{"value": "myvalue"}'

# Get a value
curl http://localhost:8080/kv/mykey

# Delete a key
curl -X DELETE http://localhost:8080/kv/mykey
```

### Admin Operations
```bash
# Get cluster status
curl http://localhost:8080/admin/status

# Get node metrics
curl http://localhost:8080/metrics

# Add a new node
curl -X POST http://localhost:8080/admin/nodes -d '{"id": "node4", "address": "localhost:8084"}'
```

## 🔍 **Monitoring & Observability**

### Metrics (Prometheus)
- `raft_term_current`: Current Raft term
- `raft_state`: Current node state (0=Follower, 1=Candidate, 2=Leader)
- `raft_log_entries_total`: Total log entries
- `raft_commits_total`: Total committed entries
- `raft_leader_elections_total`: Total leader elections

### Dashboards
- **Cluster Overview**: http://localhost:3000/d/raft-cluster
- **Node Details**: http://localhost:3000/d/raft-node
- **Performance Metrics**: http://localhost:3000/d/raft-performance

### Tracing
- **Jaeger UI**: http://localhost:16686
- Traces for all RPC calls and state transitions

## 🔧 **Configuration**

```yaml
# raft.yaml
cluster:
  nodes:
    - id: "node1"
      address: "localhost:8081"
    - id: "node2" 
      address: "localhost:8082"
    - id: "node3"
      address: "localhost:8083"

raft:
  election_timeout: "150ms"
  heartbeat_interval: "50ms"
  snapshot_interval: "1000"
  log_compaction_threshold: "10000"

storage:
  data_dir: "./data"
  wal_dir: "./wal"
  sync_writes: true

api:
  http_port: 8080
  grpc_port: 8090
```

## 🎯 **Acceptance Criteria**

- ✅ **Linearizability**: All operations appear to execute atomically
- ✅ **Safety**: No split-brain or data corruption scenarios
- ✅ **Liveness**: Progress under majority availability
- ✅ **Performance**: Meet throughput and latency targets
- ✅ **Recovery**: Fast recovery from node failures
- ✅ **Membership**: Safe dynamic cluster reconfiguration

## 📚 **References**

- [Raft Paper](https://raft.github.io/raft.pdf) - Original Raft consensus algorithm
- [Raft Visualization](http://thesecretlivesofdata.com/raft/) - Interactive Raft explanation
- [etcd Raft](https://github.com/etcd-io/etcd/tree/main/raft) - Production Raft implementation
- [Jepsen](https://jepsen.io/) - Distributed systems testing framework
