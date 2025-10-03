# Distributed Cache with Consistent Hashing

A production-grade distributed cache system implementing consistent hashing, hot-key mitigation, tiered eviction, and advanced caching strategies. This implementation demonstrates the complexities of building scalable, fault-tolerant caching systems that handle real-world operational challenges.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Load Balancer (Nginx)                        │
│                     Port: 8080                                  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                 │
┌───▼────┐       ┌───▼────┐       ┌───▼────┐
│Cache-1 │       │Cache-2 │       │Cache-3 │
│:8081   │◄─────►│:8082   │◄─────►│:8083   │
└────────┘       └────────┘       └────────┘
    │                 │                 │
    └─────────────────┼─────────────────┘
                      │
┌─────────────────────▼─────────────────────┐
│           Consistent Hash Ring             │
│  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐      │
│  │ N1  │  │ N2  │  │ N3  │  │ N1  │ ...  │
│  └─────┘  └─────┘  └─────┘  └─────┘      │
└───────────────────────────────────────────┘

Supporting Services:
├── Hot-Key Detector (Port: 8090)
├── Circuit Breaker Manager (Port: 8091) 
├── Replication Coordinator (Port: 8092)
└── Monitoring Stack (Prometheus: 9090, Grafana: 3000)
```

## 🎯 Key Features

### Core Caching
- **Consistent Hashing**: Deterministic key distribution with minimal reshuffling during node changes
- **Replication**: Configurable replication factor with read/write quorum support
- **Multi-Level Storage**: In-memory L1 cache + persistent L2 cache with intelligent promotion
- **Advanced Eviction**: LRU, LFU, TTL-based, and adaptive eviction policies

### Hot-Key Mitigation
- **Real-time Detection**: Statistical analysis and threshold-based hot-key identification
- **Request Coalescing**: Batch similar requests to reduce backend load
- **Circuit Breakers**: Automatic protection against cascading failures
- **Write-Through Caching**: Immediate persistence for critical hot keys
- **Local Replication**: Hot-key replication to multiple nodes for load distribution

### Operational Excellence
- **Cache Stampede Protection**: Distributed locking and request deduplication
- **Graceful Degradation**: Fallback strategies during partial failures
- **Dynamic Scaling**: Add/remove nodes with automatic rebalancing
- **Comprehensive Monitoring**: Real-time metrics, alerting, and performance analysis

## 🚀 Quick Start

```bash
# Start the distributed cache cluster
make start-cluster

# Run demonstrations
make hot-key-demo          # Hot-key detection and mitigation
make consistent-hash-demo  # Consistent hashing behavior
make replication-demo      # Data replication and consistency
make performance-demo      # Performance under load

# Testing
make test-unit            # Unit tests for core functionality
make test-chaos           # Chaos engineering tests
make benchmark            # Performance benchmarks
```

## 📊 Performance Targets

- **Throughput**: 1M+ operations/second across cluster
- **Latency**: <1ms p99 for cache hits, <5ms p99 for cache misses
- **Availability**: 99.9% uptime with automatic failover
- **Consistency**: Configurable consistency levels (eventual, strong)
- **Hot-Key Handling**: 100K+ requests/second per hot key without degradation

## 🔧 Technology Stack

- **Language**: Go 1.21+ with high-performance networking
- **Storage**: Redis-compatible protocol with custom storage engine
- **Networking**: gRPC for inter-node communication, HTTP for client APIs
- **Monitoring**: Prometheus metrics, Grafana dashboards, Jaeger tracing
- **Load Balancing**: Nginx with consistent hashing support
- **Container Orchestration**: Docker Compose with health checks

## 🎮 API Examples

### Basic Cache Operations
```bash
# Set a key-value pair
curl -X PUT "http://localhost:8080/cache/user:123" \
  -H "Content-Type: application/json" \
  -d '{"value": {"name": "John", "age": 30}, "ttl": 3600}'

# Get a value
curl "http://localhost:8080/cache/user:123"

# Delete a key
curl -X DELETE "http://localhost:8080/cache/user:123"

# Batch operations
curl -X POST "http://localhost:8080/cache/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "operations": [
      {"op": "set", "key": "user:1", "value": {"name": "Alice"}},
      {"op": "set", "key": "user:2", "value": {"name": "Bob"}},
      {"op": "get", "key": "user:1"}
    ]
  }'
```

### Advanced Features
```bash
# Configure hot-key detection
curl -X POST "http://localhost:8080/admin/hot-key-config" \
  -H "Content-Type: application/json" \
  -d '{
    "threshold_requests_per_second": 1000,
    "detection_window_seconds": 60,
    "mitigation_strategy": "replicate_and_coalesce"
  }'

# Get cluster status
curl "http://localhost:8080/admin/cluster/status"

# Trigger rebalancing
curl -X POST "http://localhost:8080/admin/rebalance"

# Get hot-key statistics
curl "http://localhost:8080/admin/hot-keys"

# Circuit breaker status
curl "http://localhost:8080/admin/circuit-breakers"
```

## 🧪 Testing Strategy

### Unit Tests
- **Consistent Hashing**: Hash ring construction, node addition/removal, key distribution
- **Cache Operations**: Basic CRUD operations, TTL handling, eviction policies
- **Hot-Key Detection**: Statistical analysis, threshold detection, mitigation strategies
- **Replication**: Data consistency, quorum operations, conflict resolution

### Integration Tests
- **Multi-Node Operations**: Cross-node consistency, replication validation
- **Failure Scenarios**: Node failures, network partitions, split-brain prevention
- **Performance Tests**: Throughput benchmarks, latency measurements, scalability limits

### Chaos Engineering
- **Node Failures**: Random node crashes, graceful shutdowns, recovery testing
- **Network Issues**: Partitions, latency injection, packet loss simulation
- **Load Testing**: Hot-key scenarios, cache stampedes, extreme load conditions
- **Data Corruption**: Consistency validation, repair mechanisms, backup/restore

## 📈 Monitoring & Observability

### Key Metrics
- **Cache Performance**: Hit ratio, miss ratio, operation latency, throughput
- **Hot-Key Detection**: Hot-key count, request distribution, mitigation effectiveness
- **Cluster Health**: Node status, replication lag, network connectivity
- **Resource Usage**: Memory utilization, CPU usage, network bandwidth, disk I/O

### Dashboards
- **Cache Overview**: Cluster-wide performance and health metrics
- **Hot-Key Analysis**: Real-time hot-key detection and mitigation status
- **Node Details**: Per-node performance, resource usage, and error rates
- **Replication Status**: Data consistency, replication lag, conflict resolution

### Alerting
- **High Latency**: P99 latency exceeds thresholds
- **Low Hit Ratio**: Cache effectiveness degradation
- **Hot-Key Overload**: Excessive load on specific keys
- **Node Failures**: Automatic failover and recovery alerts
- **Replication Issues**: Data consistency problems

## 🎯 Demonstration Scenarios

### 1. Hot-Key Mitigation Demo
Demonstrates real-time hot-key detection and automatic mitigation strategies:
- Generate high load on specific keys
- Observe automatic detection and replication
- Show request coalescing and circuit breaker activation
- Validate performance maintenance under hot-key load

### 2. Consistent Hashing Demo
Shows consistent hashing behavior during cluster changes:
- Display initial key distribution across nodes
- Add/remove nodes and observe minimal key movement
- Demonstrate automatic rebalancing and data migration
- Validate consistent key routing after changes

### 3. Replication and Consistency Demo
Illustrates data replication and consistency guarantees:
- Configure different replication factors
- Demonstrate read/write quorum operations
- Show conflict resolution during network partitions
- Validate eventual consistency convergence

### 4. Performance Under Load Demo
Tests system behavior under various load patterns:
- Sustained high throughput testing
- Burst load handling
- Mixed read/write workloads
- Cache stampede protection

## 🔍 Implementation Highlights

### Consistent Hashing Algorithm
- **Virtual Nodes**: Multiple hash points per physical node for better distribution
- **Configurable Hash Function**: Support for MD5, SHA1, and custom hash functions
- **Rebalancing**: Minimal data movement during topology changes
- **Fault Tolerance**: Automatic failover to replica nodes

### Hot-Key Detection Engine
- **Statistical Analysis**: Real-time request frequency analysis
- **Adaptive Thresholds**: Dynamic threshold adjustment based on cluster load
- **Multi-Level Detection**: Key-level, pattern-level, and cluster-level analysis
- **Mitigation Strategies**: Replication, coalescing, circuit breaking, and load shedding

### Advanced Eviction Policies
- **LRU (Least Recently Used)**: Traditional time-based eviction
- **LFU (Least Frequently Used)**: Frequency-based eviction for stable workloads
- **Adaptive Replacement Cache (ARC)**: Balances recency and frequency
- **TTL-Based**: Time-to-live expiration with background cleanup
- **Size-Based**: Memory pressure-driven eviction with configurable limits

### Circuit Breaker Implementation
- **Request-Level**: Per-key circuit breakers for hot-key protection
- **Node-Level**: Per-node circuit breakers for failure isolation
- **Cluster-Level**: Global circuit breakers for system protection
- **Adaptive Thresholds**: Dynamic threshold adjustment based on error rates

This distributed cache implementation provides a comprehensive foundation for understanding the complexities of building production-grade caching systems, demonstrating advanced concepts like consistent hashing, hot-key mitigation, and operational resilience.
