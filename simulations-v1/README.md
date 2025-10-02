# 🧪 Comprehensive Distributed Systems Simulations

This directory contains comprehensive simulations for testing distributed systems, microservices, database infrastructure, data warehousing, and self-hosted cloud platforms. The simulations are designed to test real-world failure scenarios and validate system resilience.

## 🎯 **Simulation Overview**

### **Supported Platforms**
- **Docker**: Container-based simulations using Docker Compose
- **Kubernetes**: Cloud-native simulations using Kubernetes manifests and operators

### **Simulation Categories**

1. **🔄 Consistency & CAP Theorem** - Raft consensus, CRDT, eventual consistency
2. **🛡️ Availability & Fault Tolerance** - Failover, recovery, graceful degradation  
3. **📈 Scalability & Performance** - Auto-scaling, load testing, performance optimization
4. **🌐 Network Partitions & Failures** - Partition tolerance, latency, packet loss
5. **🔒 Concurrency & Coordination** - Distributed locks, deadlock detection, coordination
6. **💾 State Management & Migration** - Checkpointing, migration, snapshots
7. **👁️ Observability & Debugging** - Monitoring, tracing, alerting
8. **🔐 Security & Compliance** - Authentication, encryption, audit
9. **🗄️ Database Infrastructure** - ACID, sharding, replication, backup/recovery
10. **📊 Data Warehousing & Analytics** - ETL, real-time processing, query optimization
11. **🔧 Microservices Architecture** - Service mesh, API gateway, distributed transactions
12. **☁️ Self-Hosted Cloud Platform** - Container orchestration, infrastructure automation

## 🚀 **Quick Start**

### **Prerequisites**

```bash
# For Docker simulations
docker --version
docker-compose --version

# For Kubernetes simulations  
kubectl version
helm version

# Python dependencies
python3 -m pip install -r simulations/scripts/requirements.txt
```

### **Run All Simulations**

```bash
# Run all simulations on Docker
./simulations/run-all-simulations.sh

# Run all simulations on Kubernetes
./simulations/run-all-simulations.sh --platform kubernetes

# Run specific categories
./simulations/run-all-simulations.sh --categories consistency,availability,scalability

# Keep resources running after tests
./simulations/run-all-simulations.sh --no-cleanup
```

### **Run Individual Simulations**

```bash
# Consistency & CAP Theorem
python3 simulations/scripts/run-consistency-simulation.py --platform docker

# Database Infrastructure (using existing microservices)
./scripts/run-integration-tests.sh --cleanup

# Microservices Architecture
cd infrastructure && docker-compose up -d --build
```

## 📁 **Directory Structure**

```
simulations/
├── README.md                          # This file
├── run-all-simulations.sh            # Main simulation runner
├── docker/                           # Docker-based simulations
│   ├── consistency-cap-simulation/   # CAP theorem & consensus
│   ├── availability-simulation/      # Fault tolerance testing
│   ├── scalability-simulation/       # Performance & scaling
│   └── network-simulation/           # Network failure testing
├── kubernetes/                       # Kubernetes-based simulations
│   ├── consistency-cap-simulation/   # K8s CAP theorem testing
│   ├── availability-simulation/      # K8s fault tolerance
│   └── chaos-mesh/                   # Chaos engineering configs
├── scripts/                          # Simulation automation scripts
│   ├── requirements.txt              # Python dependencies
│   ├── run-consistency-simulation.py # Consistency test runner
│   ├── run-availability-tests.py     # Availability test runner
│   ├── run-scalability-tests.py      # Scalability test runner
│   └── run-network-tests.py          # Network test runner
└── simulation-results/               # Generated reports and results
```

## 🧪 **Detailed Simulation Descriptions**

### **1. Consistency & CAP Theorem Simulations**

**Location**: `simulations/docker/consistency-cap-simulation/`

**Components**:
- **etcd cluster** (3 nodes) for Raft consensus testing
- **PostgreSQL** with streaming replication
- **MongoDB** replica set (3 nodes)
- **CRDT service** (Node.js) implementing G-Counter, PN-Counter, OR-Set
- **Chaos controller** (Python) for network partition injection

**Test Scenarios**:
- ✅ Leader election during node failures
- ✅ Log replication consistency under load
- ✅ Network partition tolerance (split-brain prevention)
- ✅ CRDT convergence under concurrent updates
- ✅ Clock skew handling with logical clocks

**Usage**:
```bash
cd simulations/docker/consistency-cap-simulation
docker-compose up -d --build

# Run automated tests
python3 ../../scripts/run-consistency-simulation.py --platform docker --tests all
```

### **2. Database Infrastructure Simulations**

**Location**: Uses existing microservices system in `infrastructure/`

**Components**:
- **PostgreSQL cluster** with Patroni for HA
- **MongoDB replica set** with sharding
- **Redis cluster** for caching
- **ClickHouse** for analytics
- **Multiple microservices** in different languages (Rust, Java, Node.js, Go, Python)

**Test Scenarios**:
- ✅ Cross-service Saga transactions
- ✅ Outbox pattern reliability (PostgreSQL + MongoDB)
- ✅ CQRS with Event Sourcing (Java/Axon)
- ✅ Database failover and recovery
- ✅ Distributed transaction coordination

**Usage**:
```bash
# Start all services
cd infrastructure
docker-compose up -d --build

# Run comprehensive integration tests
../scripts/run-integration-tests.sh --cleanup
```

### **3. Microservices Architecture Simulations**

**Location**: Uses existing microservices in `services/`

**Components**:
- **Transaction Coordinator** (Rust) - 2PC and Saga orchestration
- **Account Service** (Java) - CQRS/Event Sourcing with Axon
- **Billing Service** (Node.js) - MongoDB-based billing lifecycle
- **Outbox Publisher** (Go) - Reliable event publishing
- **Fraud Detection** (Python) - ML-powered fraud scoring

**Test Scenarios**:
- ✅ End-to-end order processing saga
- ✅ Service mesh traffic management (Istio/Linkerd)
- ✅ API gateway functionality
- ✅ Circuit breaker and retry policies
- ✅ Distributed tracing and monitoring

**Usage**:
```bash
# Use existing microservices system
./scripts/run-integration-tests.sh

# Or run specific service tests
cd tests/integration
python3 cross_service_saga_test.py
python3 outbox_pattern_test.py
python3 cqrs_flow_test.py
```

## 📊 **Monitoring and Observability**

All simulations include comprehensive monitoring:

- **Prometheus** - Metrics collection and alerting
- **Grafana** - Visualization and dashboards  
- **Jaeger** - Distributed tracing
- **ELK Stack** - Log aggregation and analysis

**Access URLs** (when running locally):
- Grafana: http://localhost:3000 (admin/admin123)
- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686

## 🔧 **Chaos Engineering**

### **Docker Platform**
- Custom chaos controller with network partition injection
- Container failure simulation (pause/unpause)
- Network latency and packet loss injection
- Clock skew simulation

### **Kubernetes Platform**  
- **Chaos Mesh** integration for advanced chaos experiments
- Pod failures, network chaos, I/O chaos
- Time chaos for clock skew testing
- Stress testing with CPU/memory pressure

## 📈 **Results and Reporting**

Simulation results are automatically generated in JSON format:

```json
{
  "simulation_id": "consistency_sim_1703123456",
  "platform": "docker",
  "start_time": "2023-12-20T10:30:00Z",
  "tests": [
    {
      "test_name": "raft_consensus",
      "scenarios": [
        {
          "scenario_name": "leader_election",
          "success": true,
          "duration_seconds": 45.2
        }
      ]
    }
  ],
  "summary": {
    "total_tests": 12,
    "successful_tests": 11,
    "success_rate": 0.92
  }
}
```

## 🎯 **Success Criteria**

Each simulation category has specific success criteria:

- **Availability**: 99.9% uptime during chaos experiments
- **Consistency**: No data loss or corruption under partitions
- **Performance**: Sub-second response times under 10x load
- **Recovery**: RTO < 60 seconds, RPO < 5 seconds
- **Scalability**: Linear scaling up to 10x baseline load

## 🔍 **Troubleshooting**

### **Common Issues**

1. **Docker daemon not running**
   ```bash
   sudo systemctl start docker
   ```

2. **Kubernetes cluster not accessible**
   ```bash
   kubectl cluster-info
   kubectl get nodes
   ```

3. **Port conflicts**
   ```bash
   # Check for port usage
   netstat -tulpn | grep :5432
   
   # Stop conflicting services
   sudo systemctl stop postgresql
   ```

4. **Insufficient resources**
   ```bash
   # Check available resources
   docker system df
   kubectl top nodes
   
   # Clean up unused resources
   docker system prune -a
   ```

### **Debug Mode**

Enable debug logging for detailed troubleshooting:

```bash
export LOG_LEVEL=DEBUG
./simulations/run-all-simulations.sh --categories consistency
```

## 🤝 **Contributing**

To add new simulations:

1. Create simulation directory under `docker/` or `kubernetes/`
2. Add Docker Compose or Kubernetes manifests
3. Create test automation script in `scripts/`
4. Update `run-all-simulations.sh` with new category
5. Add documentation and success criteria

## 📚 **References**

- [CAP Theorem](https://en.wikipedia.org/wiki/CAP_theorem)
- [Raft Consensus Algorithm](https://raft.github.io/)
- [CRDT Research](https://crdt.tech/)
- [Chaos Engineering Principles](https://principlesofchaos.org/)
- [Microservices Patterns](https://microservices.io/patterns/)
- [Database Reliability Engineering](https://www.oreilly.com/library/view/database-reliability-engineering/9781491925935/)

---

**🎉 Happy Testing! Build resilient distributed systems with confidence.**
