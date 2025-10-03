# Geo-replicated Datastore + Conflict Resolution

A production-grade multi-region distributed datastore featuring CRDT-based conflict resolution, anti-entropy reconciliation, and eventual consistency across geographically distributed nodes.

## 🎯 **Project Goals**

Build a geo-replicated datastore with:
- **Multi-Region Replication**: Asynchronous replication across geographic regions
- **CRDT-Based Conflict Resolution**: Mathematically sound conflict-free replicated data types
- **Anti-Entropy Reconciliation**: Merkle tree-based synchronization and repair
- **Eventual Consistency**: Strong eventual consistency guarantees with convergence
- **Partition Tolerance**: Graceful operation during network partitions
- **Flexible Consistency Models**: Tunable consistency levels per operation

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Global Geo-Replicated System                │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
│   Region US     │    │   Region EU     │    │   Region APAC   │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │   Node 1    │ │    │ │   Node 1    │ │    │ │   Node 1    │ │
│ │             │ │    │ │             │ │    │ │             │ │
│ │ CRDT Store  │ │    │ │ CRDT Store  │ │    │ │ CRDT Store  │ │
│ │ Anti-Entropy│ │    │ │ Anti-Entropy│ │    │ │ Anti-Entropy│ │
│ │ Vector Clock│ │    │ │ Vector Clock│ │    │ │ Vector Clock│ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │   Node 2    │ │    │ │   Node 2    │ │    │ │   Node 2    │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │   Node 3    │ │    │ │   Node 3    │ │    │ │   Node 3    │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                    Cross-Region Replication
                    Anti-Entropy Synchronization
                    Conflict Resolution via CRDTs
```

## 🚀 **Features**

### CRDT Data Types
- **G-Counter**: Grow-only counter for metrics and analytics
- **PN-Counter**: Increment/decrement counter with conflict resolution
- **G-Set**: Grow-only set for immutable collections
- **2P-Set**: Two-phase set with add/remove operations
- **OR-Set**: Observed-remove set with unique element tracking
- **LWW-Register**: Last-writer-wins register with timestamps
- **MV-Register**: Multi-value register preserving concurrent updates

### Conflict Resolution
- **Automatic Merging**: CRDTs automatically resolve conflicts without coordination
- **Vector Clocks**: Causal ordering and concurrent update detection
- **Semantic Resolution**: Application-specific conflict resolution strategies
- **Merge Functions**: Customizable merge logic for complex data types

### Anti-Entropy & Synchronization
- **Merkle Trees**: Efficient difference detection between replicas
- **Gossip Protocol**: Epidemic-style information dissemination
- **Read Repair**: On-demand synchronization during read operations
- **Background Sync**: Periodic full synchronization between regions

### Consistency Models
- **Eventual Consistency**: All replicas converge to the same state
- **Strong Eventual Consistency**: Convergence without coordination
- **Causal Consistency**: Preserves causal relationships between operations
- **Session Consistency**: Monotonic reads and writes within sessions

## 🛠️ **Technology Stack**

- **Language**: Go 1.21+ with advanced concurrency patterns
- **Storage**: RocksDB with column families for different CRDT types
- **Networking**: gRPC for inter-region communication with compression
- **Serialization**: Protocol Buffers with CRDT-specific message types
- **Coordination**: Gossip-based membership and failure detection
- **Monitoring**: Comprehensive metrics for replication lag and conflicts

## 📋 **Implementation Checklist**

### Phase 1: Core CRDT Implementation ✅
- [x] G-Counter and PN-Counter implementations
- [x] G-Set and 2P-Set implementations
- [x] OR-Set with unique element tracking
- [x] LWW-Register and MV-Register
- [x] Vector clock implementation
- [x] CRDT merge operations

### Phase 2: Storage Layer ✅
- [x] RocksDB integration with CRDT serialization
- [x] Column families for different data types
- [x] Efficient storage of vector clocks
- [x] Snapshot and compaction support
- [x] Atomic batch operations

### Phase 3: Replication Engine ✅
- [x] Asynchronous multi-region replication
- [x] Gossip-based node discovery
- [x] Failure detection and recovery
- [x] Configurable replication topology
- [x] Network partition handling

### Phase 4: Anti-Entropy System ✅
- [x] Merkle tree construction and comparison
- [x] Efficient delta synchronization
- [x] Read repair mechanisms
- [x] Background synchronization jobs
- [x] Conflict detection and resolution

### Phase 5: API and Operations ✅
- [x] RESTful API for CRDT operations
- [x] Multi-region read/write routing
- [x] Consistency level configuration
- [x] Administrative operations
- [x] Monitoring and observability

## 🧪 **Testing Strategy**

### Functional Testing
- **CRDT Properties**: Commutativity, associativity, idempotency
- **Convergence**: All replicas reach the same state
- **Conflict Resolution**: Concurrent updates merge correctly
- **Partition Tolerance**: Operation during network splits

### Consistency Testing
- **Eventual Consistency**: Verify convergence under various scenarios
- **Causal Consistency**: Preserve happens-before relationships
- **Session Consistency**: Monotonic guarantees within sessions
- **Linearizability**: Where applicable for specific operations

### Performance Testing
- **Replication Latency**: Cross-region propagation times
- **Throughput**: Operations per second under load
- **Storage Efficiency**: CRDT overhead and compaction
- **Network Utilization**: Bandwidth usage for synchronization

### Chaos Engineering
- **Network Partitions**: Split-brain scenarios and recovery
- **Node Failures**: Graceful degradation and recovery
- **Clock Skew**: Timestamp-based conflict resolution
- **Byzantine Faults**: Malicious or corrupted data handling

## 📊 **Performance Targets**

### Latency
- **Local Operations**: <1ms for local CRDT updates
- **Cross-Region Sync**: <100ms for nearby regions, <500ms globally
- **Read Repair**: <10ms additional latency when triggered
- **Anti-Entropy**: <1s for small differences, <60s for full sync

### Throughput
- **Local Writes**: 100,000+ operations/second per node
- **Cross-Region**: 10,000+ operations/second sustained
- **Concurrent Updates**: Handle 1000+ concurrent writers per key

### Storage
- **CRDT Overhead**: <50% storage overhead for metadata
- **Compression**: 70%+ compression ratio for vector clocks
- **Compaction**: 90%+ space reclamation for tombstones

## 🚀 **Quick Start**

```bash
# Build and start the geo-replicated cluster
make build
make start-cluster

# Create a CRDT counter
curl -X POST http://localhost:8080/crdt/counters/page_views \
  -d '{"type": "pn_counter", "initial_value": 0}'

# Increment counter in different regions
curl -X POST http://localhost:8081/crdt/counters/page_views/increment \
  -d '{"value": 5}'

curl -X POST http://localhost:8082/crdt/counters/page_views/increment \
  -d '{"value": 3}'

# Read merged value (should be 8)
curl http://localhost:8080/crdt/counters/page_views

# Run comprehensive tests
make test-comprehensive
```

## 📖 **API Examples**

### CRDT Operations
```bash
# Create G-Counter
curl -X POST http://localhost:8080/crdt/counters/metrics \
  -d '{"type": "g_counter"}'

# Create OR-Set
curl -X POST http://localhost:8080/crdt/sets/tags \
  -d '{"type": "or_set"}'

# Add to set
curl -X POST http://localhost:8080/crdt/sets/tags/add \
  -d '{"element": "distributed-systems"}'

# Create LWW-Register
curl -X POST http://localhost:8080/crdt/registers/config \
  -d '{"type": "lww_register", "value": "production"}'
```

### Multi-Region Operations
```bash
# Write to specific region
curl -X POST http://localhost:8081/crdt/registers/user_status \
  -d '{"value": "online", "region": "us-east"}'

# Read with consistency level
curl "http://localhost:8080/crdt/registers/user_status?consistency=eventual"

# Force synchronization
curl -X POST http://localhost:8080/admin/sync/regions/eu-west
```

### Administrative Operations
```bash
# Cluster status
curl http://localhost:8080/admin/status

# Replication lag
curl http://localhost:8080/admin/replication/lag

# Trigger anti-entropy
curl -X POST http://localhost:8080/admin/anti-entropy/full-sync

# View conflicts
curl http://localhost:8080/admin/conflicts
```

## 🔍 **Monitoring & Observability**

### Metrics (Prometheus)
- `geodatastore_operations_total`: Total CRDT operations by type and region
- `geodatastore_replication_lag_seconds`: Replication lag between regions
- `geodatastore_conflicts_resolved_total`: Number of conflicts resolved
- `geodatastore_anti_entropy_syncs_total`: Anti-entropy synchronization events
- `geodatastore_vector_clock_size`: Size of vector clocks

### Dashboards
- **Global Overview**: http://localhost:3000/d/geodatastore-global
- **Regional Health**: http://localhost:3000/d/geodatastore-regions
- **CRDT Operations**: http://localhost:3000/d/geodatastore-crdts
- **Conflict Resolution**: http://localhost:3000/d/geodatastore-conflicts

### Distributed Tracing
- **Cross-Region Operations**: Trace requests across multiple regions
- **Conflict Resolution**: Detailed tracing of merge operations
- **Anti-Entropy**: Synchronization process visualization

## 🎯 **Acceptance Criteria**

- ✅ **Convergence**: All replicas converge to the same state
- ✅ **Partition Tolerance**: Continues operating during network splits
- ✅ **Conflict Resolution**: Automatic resolution without data loss
- ✅ **Performance**: Meets latency and throughput targets
- ✅ **Scalability**: Linear scaling with number of regions
- ✅ **Correctness**: CRDT mathematical properties preserved

## 📚 **References**

- [CRDTs: Consistency without consensus](https://hal.inria.fr/inria-00609399v1/document)
- [A comprehensive study of CRDTs](https://hal.inria.fr/hal-00932836/document)
- [Dynamo: Amazon's Highly Available Key-value Store](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf)
- [Riak's approach to CRDTs](https://docs.riak.com/riak/kv/latest/learn/concepts/crdts/)
- [Vector Clocks in Distributed Systems](https://en.wikipedia.org/wiki/Vector_clock)
