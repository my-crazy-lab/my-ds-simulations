# Chaos Lab: Jepsen-style Distributed Systems Analysis

A comprehensive chaos engineering laboratory implementing Jepsen-style distributed systems testing and analysis. This implementation demonstrates rigorous testing methodologies for distributed systems, focusing on consistency, availability, and partition tolerance under various failure scenarios.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Chaos Lab Environment                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Test Runner   │  │  Target System  │  │   Nemesis       │ │
│  │   (Jepsen)      │  │   (Database)    │  │  (Failures)     │ │
│  │                 │  │                 │  │                 │ │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │ │
│  │ │ Workload    │ │  │ │   Node 1    │ │  │ │ Network     │ │ │
│  │ │ Generator   │ │  │ │   Node 2    │ │  │ │ Partitions  │ │ │
│  │ │             │ │  │ │   Node 3    │ │  │ │             │ │ │
│  │ └─────────────┘ │  │ │   Node 4    │ │  │ └─────────────┘ │ │
│  │ ┌─────────────┐ │  │ │   Node 5    │ │  │ ┌─────────────┐ │ │
│  │ │ History     │ │  │ └─────────────┘ │  │ │ Process     │ │ │
│  │ │ Checker     │ │  └─────────────────┘  │ │ Failures    │ │ │
│  │ └─────────────┘ │                       │ └─────────────┘ │ │
│  └─────────────────┘                       └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Analysis & Reporting                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Consistency │  │ Linearizab. │  │ Causality   │             │
│  │ Analysis    │  │ Checker     │  │ Checker     │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Performance │  │ Availability│  │ Safety      │             │
│  │ Metrics     │  │ Analysis    │  │ Violations  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## 🎯 Key Features

### Jepsen-style Testing Framework
- **Workload Generation**: Concurrent operations with realistic access patterns
- **Failure Injection**: Network partitions, process crashes, clock skew, disk failures
- **History Analysis**: Linearizability, serializability, and causal consistency checking
- **Nemesis System**: Sophisticated failure injection with timing control
- **Result Visualization**: Interactive graphs and detailed analysis reports

### Target Systems Under Test
- **Distributed Databases**: Consensus-based systems (Raft, PBFT)
- **Key-Value Stores**: Eventually consistent and strongly consistent systems
- **Message Queues**: Ordering and delivery guarantee validation
- **Coordination Services**: Leader election and distributed locking
- **Cache Systems**: Consistency and coherence validation

### Analysis Capabilities
- **Consistency Models**: Linearizability, sequential consistency, causal consistency
- **Safety Properties**: Invariant checking and violation detection
- **Liveness Properties**: Progress guarantees and deadlock detection
- **Performance Analysis**: Latency, throughput, and availability metrics
- **Fault Tolerance**: Recovery time and data loss analysis

## 🚀 Quick Start

```bash
# Start the chaos lab
make start-lab

# Run comprehensive tests
make test-all              # All distributed systems tests
make test-consistency      # Consistency model validation
make test-partition        # Network partition scenarios
make test-crash            # Process crash scenarios

# Interactive demonstrations
make jepsen-demo           # Complete Jepsen-style analysis
make consistency-demo      # Consistency model demonstration
make partition-demo        # Network partition testing
make performance-demo      # Performance under chaos
```

## 📊 Performance Targets

- **Test Coverage**: 95%+ of consistency scenarios and failure modes
- **Analysis Speed**: <10 minutes for comprehensive consistency analysis
- **Failure Detection**: 99%+ accuracy in detecting consistency violations
- **Scalability**: Support for 100+ concurrent operations and 10+ node clusters
- **Reproducibility**: 100% reproducible test results with deterministic scheduling

## 🔧 Technology Stack

- **Testing Framework**: Clojure-based Jepsen framework with custom extensions
- **Target Systems**: Multiple distributed systems (databases, caches, queues)
- **Failure Injection**: Custom nemesis implementations with precise timing control
- **Analysis Engine**: Linearizability checkers, consistency model validators
- **Visualization**: Interactive web-based result visualization and reporting
- **Orchestration**: Docker Compose for multi-node cluster management

## 🎮 Test Configuration Examples

### Linearizability Test
```clojure
{:name "linearizability-test"
 :nodes ["n1" "n2" "n3" "n4" "n5"]
 :concurrency 10
 :time-limit 300
 :workload {:type :register
            :read-write-ratio 0.5}
 :nemesis {:type :partition-majorities-ring
           :interval 30}
 :checker [:linearizable :perf]}
```

### Bank Account Test
```clojure
{:name "bank-test"
 :nodes ["n1" "n2" "n3"]
 :concurrency 5
 :time-limit 180
 :workload {:type :bank
            :accounts 8
            :max-transfer 100}
 :nemesis {:type :kill-random-processes
           :interval 45}
 :checker [:bank-checker :timeline]}
```

### Set Consistency Test
```clojure
{:name "set-test"
 :nodes ["n1" "n2" "n3" "n4" "n5"]
 :concurrency 8
 :time-limit 240
 :workload {:type :set
            :element-count 100}
 :nemesis {:type :partition-bridge
           :targets #{:n1 :n2}}
 :checker [:set-checker :availability]}
```

## 🧪 Testing Strategy

### Consistency Models
- **Linearizability**: Strong consistency with real-time ordering
- **Sequential Consistency**: Program order preservation across processes
- **Causal Consistency**: Causally related operations ordering
- **Eventual Consistency**: Convergence guarantees and conflict resolution
- **Session Consistency**: Per-session consistency guarantees

### Failure Scenarios
- **Network Partitions**: Majority/minority splits, bridge partitions, isolate nodes
- **Process Failures**: Crash-stop, crash-recovery, Byzantine failures
- **Clock Issues**: Clock skew, time jumps, NTP failures
- **Disk Failures**: Corruption, full disks, slow I/O
- **Resource Exhaustion**: Memory pressure, CPU starvation, network congestion

### Workload Patterns
- **CRUD Operations**: Create, read, update, delete with various patterns
- **Bank Transfers**: Multi-account transactions with invariant checking
- **Counter Operations**: Increment/decrement with linearizability requirements
- **Set Operations**: Add/remove elements with membership consistency
- **Queue Operations**: Enqueue/dequeue with ordering guarantees

## 📈 Analysis & Reporting

### Consistency Analysis
- **Linearizability Checking**: Real-time operation ordering validation
- **Serializability Analysis**: Transaction isolation level verification
- **Causal Consistency**: Happens-before relationship validation
- **Monotonic Consistency**: Read monotonicity and write monotonicity
- **Session Guarantees**: Read-your-writes, monotonic reads/writes

### Performance Metrics
- **Latency Analysis**: P50, P95, P99 latencies under various conditions
- **Throughput Measurement**: Operations per second during failures
- **Availability Calculation**: Uptime percentage and recovery times
- **Consistency Lag**: Time to consistency after partition healing
- **Error Rates**: Operation failure rates and error categorization

### Visualization
- **Timeline Graphs**: Operation history with failure injection points
- **Consistency Graphs**: Linearizability violations and consistency models
- **Performance Charts**: Latency and throughput over time
- **Network Topology**: Partition scenarios and node connectivity
- **Error Analysis**: Failure modes and recovery patterns

## 🎯 Demonstration Scenarios

### 1. Linearizability Violation Detection
Demonstrates detection of linearizability violations in distributed registers:
- Deploy 5-node distributed register system
- Generate concurrent read/write operations
- Inject network partitions during operations
- Analyze operation history for linearizability violations
- Visualize consistency model violations

### 2. Bank Account Invariant Checking
Shows invariant preservation during failures:
- Deploy distributed banking system with account balances
- Generate concurrent transfer operations
- Inject process crashes and network partitions
- Verify total balance invariant preservation
- Analyze transaction isolation levels

### 3. Partition Tolerance Analysis
Tests system behavior under network partitions:
- Deploy multi-node distributed system
- Create various partition scenarios (majority/minority, bridge, isolate)
- Measure availability and consistency during partitions
- Analyze partition healing and recovery behavior
- Validate CAP theorem trade-offs

### 4. Performance Under Chaos
Measures performance degradation during failures:
- Establish baseline performance metrics
- Inject various failure scenarios
- Measure latency and throughput impact
- Analyze recovery time and performance restoration
- Compare different failure injection strategies

## 🔍 Implementation Highlights

### Jepsen Framework Integration
- **Test Definition**: Declarative test specifications with workloads and nemeses
- **History Collection**: Comprehensive operation history with precise timestamps
- **Checker Pipeline**: Pluggable consistency checkers and analysis modules
- **Result Aggregation**: Statistical analysis and report generation
- **Reproducibility**: Deterministic test execution with seed control

### Advanced Failure Injection
- **Network Partitions**: Sophisticated partition scenarios with healing
- **Process Management**: Controlled process crashes and restarts
- **Clock Manipulation**: Time skew injection and NTP disruption
- **Resource Constraints**: Memory, CPU, and I/O limitation
- **Byzantine Failures**: Malicious behavior simulation

### Consistency Checking
- **Linearizability**: Real-time ordering validation with efficient algorithms
- **Serializability**: Transaction history analysis and cycle detection
- **Causal Consistency**: Vector clock-based causality validation
- **Eventual Consistency**: Convergence detection and conflict resolution
- **Custom Invariants**: Domain-specific consistency property checking

### Performance Analysis
- **Latency Tracking**: High-resolution timestamp collection and analysis
- **Throughput Measurement**: Operation rate calculation under various conditions
- **Availability Metrics**: Uptime calculation and failure impact assessment
- **Resource Utilization**: System resource usage during tests
- **Scalability Analysis**: Performance characteristics under load

This chaos lab implementation provides a comprehensive foundation for understanding distributed systems testing, demonstrating advanced concepts including consistency model validation, sophisticated failure injection, and rigorous analysis methodologies used in production systems validation.
