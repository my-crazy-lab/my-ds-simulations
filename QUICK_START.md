# 🚀 QUICK START - Choose Your Path

This codebase is **large and complex**. Here are the best ways to get started:

## 🎯 **Path 1: Learn Concepts (Recommended)**

Start with individual concepts in isolation:

### **1. Basic Saga Pattern (5 minutes)**
```bash
# Start PostgreSQL
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15

# Run saga orchestrator
cd services/saga-orchestrator
go run main.go

# Test it (in another terminal)
curl -X POST http://localhost:8080/api/v1/sagas \
  -H "Content-Type: application/json" \
  -d '{"type": "order_processing", "data": {"order_id": "test-001"}}'
```

### **2. Database Sharding (3 minutes)**
```bash
# Start 3 PostgreSQL instances
docker run -d --name pg-primary -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name pg-shard1 -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name pg-shard2 -p 5434:5432 -e POSTGRES_PASSWORD=postgres postgres:15

# Run sharding proxy
cd services/sharding-proxy
go run main.go

# Queries get routed to appropriate shards based on user_id
```

### **3. CRDT Conflict Resolution (2 minutes)**
```bash
# Start MongoDB and Redis
docker run -d --name mongo -p 27017:27017 mongo:7
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Run sync service
cd services/sync-service
go run main.go

# Test conflict resolution
curl -X POST http://localhost:8091/api/v1/crdt/merge \
  -H "Content-Type: application/json" \
  -d '{
    "crdt_type": "LWWRegister",
    "local_state": {"value": "hello", "timestamp": "2024-01-01T10:00:00Z"},
    "remote_state": {"value": "world", "timestamp": "2024-01-01T11:00:00Z"}
  }'
```

**See all examples:** `cat docs/MINIMAL_EXAMPLES.md`

---

## 🏗️ **Path 2: Use Makefile Commands**

```bash
# Show all available commands
make help

# Learn concepts step by step
make examples

# Try specific demos
make basic-saga     # Saga pattern demo
make sharding       # Database sharding demo
make sync          # CRDT sync demo
make analytics     # Real-time ETL demo
make eventsourcing # Event sourcing demo

# Check service health
make status

# Clean up everything
make clean
```

---

## 📚 **Path 3: Read Documentation First**

1. **[Getting Started](docs/GETTING_STARTED.md)** - Step-by-step setup guide
2. **[Minimal Examples](docs/MINIMAL_EXAMPLES.md)** - 5-minute demos of each concept
3. **[Service Breakdown](docs/SERVICE_BREAKDOWN.md)** - Individual service details
4. **[Simplified Docker](docs/DOCKER_SIMPLIFIED.md)** - Focused Docker Compose files

---

## 🐳 **Path 4: Full System (Advanced)**

Only attempt this after understanding individual concepts:

```bash
# Deploy complete distributed system (requires significant resources)
./scripts/deploy-distributed.sh deploy

# Check status
./scripts/deploy-distributed.sh status

# Access services:
# - Saga Orchestrator: http://localhost:8080
# - CQRS Event Store: http://localhost:8090
# - Sync Service: http://localhost:8091
# - Analytics ETL: http://localhost:8092
# - Disaster Recovery: http://localhost:8093
# - Schema Migration: http://localhost:8094
# - Consistency Testing: http://localhost:8095
```

---

## ⚠️ **Important Notes**

### **System Requirements**
- **Docker**: For running databases and infrastructure
- **Go 1.21+**: For running services
- **8GB+ RAM**: For full distributed system
- **Available Ports**: 5432-5435, 6379, 7001-7003, 8080-8095, 9000, 9092, 27017-27019

### **Start Small**
- ❌ Don't start with the full distributed system
- ✅ Start with individual concepts (Path 1)
- ✅ Use minimal examples first
- ✅ Gradually add complexity

### **Common Issues**
```bash
# Port conflicts
lsof -i :8080
kill -9 <PID>

# Database not ready
docker logs postgres

# Go module issues
go clean -modcache
go mod tidy
```

### **Getting Help**
- Check service health: `curl http://localhost:8080/health`
- View logs: `docker logs <container_name>`
- Clean up: `make clean`

---

## 🎯 **What You'll Learn**

### **Distributed Systems Patterns**
- **Saga Pattern**: Distributed transactions with compensation
- **Outbox Pattern**: Reliable event publishing
- **CQRS**: Command-Query Responsibility Segregation
- **Event Sourcing**: Complete audit trail
- **Circuit Breaker**: Fault tolerance

### **Database Patterns**
- **Sharding**: Horizontal partitioning
- **Replication**: Master-slave, replica sets
- **CRDT**: Conflict-free data types
- **CDC**: Change Data Capture
- **Time-travel**: Point-in-time queries

### **Operational Patterns**
- **Disaster Recovery**: Backup and restore
- **Schema Migration**: Zero-downtime changes
- **Chaos Testing**: Fault injection
- **Observability**: Metrics, tracing, logging
- **Consistency Testing**: Distributed systems validation

---

## 🚀 **Recommended Learning Path**

1. **Start**: `make examples` (read the guide)
2. **Try**: Basic saga pattern (5 minutes)
3. **Explore**: CRDT conflict resolution (2 minutes)
4. **Learn**: Database sharding (3 minutes)
5. **Understand**: Event sourcing (4 minutes)
6. **Advanced**: Full distributed system

Each step builds on the previous one. Take your time to understand each concept before moving to the next.

---

## 📖 **Key Files to Understand**

- `services/saga-orchestrator/main.go` - Saga coordination
- `services/sync-service/internal/crdt/` - CRDT implementations
- `services/sharding-proxy/main.go` - Database routing
- `services/cqrs-event-store/main.go` - Event sourcing
- `infrastructure/docker-compose-distributed.yml` - Full system setup

**Remember**: This is a learning project. Focus on understanding the concepts rather than running everything at once.
