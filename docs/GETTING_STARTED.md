# 🚀 Getting Started Guide

This guide helps you run specific parts of the system without deploying everything at once.

## 📋 Prerequisites

```bash
# Required tools
- Docker & Docker Compose
- Go 1.21+
- Make (optional)

# Check versions
docker --version
docker-compose --version
go version
```

## 🎯 Quick Start Options

### Option 1: Basic Saga Pattern Demo (Recommended)

Start with just the core saga orchestrator and one business service:

```bash
# 1. Start minimal infrastructure
docker-compose up -d postgres redis kafka zookeeper

# 2. Wait for services to be ready (30 seconds)
sleep 30

# 3. Start saga orchestrator only
cd services/saga-orchestrator
go mod tidy
go run main.go

# 4. In another terminal, start inventory service
cd services/inventory-service  
go mod tidy
go run main.go

# 5. Test the saga
curl -X POST http://localhost:8080/api/v1/sagas \
  -H "Content-Type: application/json" \
  -d '{
    "type": "order_processing",
    "data": {
      "order_id": "test-001",
      "user_id": "user-123",
      "items": [{"sku": "LAPTOP001", "quantity": 1}]
    }
  }'
```

**What you'll see:**
- Saga orchestrator coordinates the transaction
- Inventory service reserves items
- Events flow through Kafka
- Compensation if anything fails

### Option 2: Database Sharding Demo

Test the sharding proxy with PostgreSQL:

```bash
# 1. Start PostgreSQL cluster
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary postgres-shard1 postgres-shard2

# 2. Wait for databases
sleep 20

# 3. Start sharding proxy
cd services/sharding-proxy
go mod tidy
go run main.go

# 4. Test sharding (proxy runs on port 5433)
# Connect with any PostgreSQL client to localhost:5433
psql -h localhost -p 5433 -U postgres -d microservices
```

### Option 3: CRDT Sync Demo

Test offline-online synchronization:

```bash
# 1. Start MongoDB and Redis
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  mongodb-primary redis-node1

# 2. Start sync service
cd services/sync-service
go mod tidy
go run main.go

# 3. Test CRDT operations
curl -X POST http://localhost:8091/api/v1/crdt/merge \
  -H "Content-Type: application/json" \
  -d '{
    "crdt_type": "LWWRegister",
    "local_state": {"value": "hello", "timestamp": "2024-01-01T10:00:00Z"},
    "remote_state": {"value": "world", "timestamp": "2024-01-01T11:00:00Z"}
  }'
```

## 🔧 Individual Service Testing

### Saga Orchestrator
```bash
# Start dependencies
docker-compose up -d postgres redis kafka

# Run service
cd services/saga-orchestrator
go run main.go

# Test endpoints
curl http://localhost:8080/health
curl http://localhost:8080/api/v1/sagas
```

### Inventory Service
```bash
# Start dependencies  
docker-compose up -d postgres redis

# Run service
cd services/inventory-service
go run main.go

# Test endpoints
curl http://localhost:8081/health
curl http://localhost:8081/api/v1/items
```

### Analytics ETL
```bash
# Start dependencies
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary clickhouse kafka

# Run service
cd services/analytics-etl
go run main.go

# Check pipeline status
curl http://localhost:8092/api/v1/pipeline/status
```

## 🐛 Troubleshooting

### Common Issues

**1. Port conflicts**
```bash
# Check what's using ports
lsof -i :8080
lsof -i :5432

# Kill processes if needed
kill -9 <PID>
```

**2. Database connection errors**
```bash
# Check if PostgreSQL is ready
docker-compose logs postgres

# Test connection
psql -h localhost -p 5432 -U postgres -d microservices
```

**3. Kafka not ready**
```bash
# Check Kafka logs
docker-compose logs kafka

# List topics
docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

**4. Go module issues**
```bash
# Clean and rebuild
go clean -modcache
go mod download
go mod tidy
```

### Service Dependencies

| Service | Requires |
|---------|----------|
| saga-orchestrator | postgres, redis, kafka |
| inventory-service | postgres, redis |
| payment-service | postgres, redis |
| sync-service | mongodb, redis |
| analytics-etl | postgres, clickhouse, kafka |
| sharding-proxy | postgres-primary, postgres-shard1, postgres-shard2 |

## 📊 Monitoring

### Basic Health Checks
```bash
# Check all service health
curl http://localhost:8080/health  # saga-orchestrator
curl http://localhost:8081/health  # inventory-service
curl http://localhost:8082/health  # payment-service
curl http://localhost:8091/health  # sync-service
```

### View Metrics
```bash
# Prometheus metrics for each service
curl http://localhost:8080/metrics
curl http://localhost:8081/metrics
```

### View Logs
```bash
# Docker logs
docker-compose logs -f saga-orchestrator
docker-compose logs -f postgres

# Application logs (if running locally)
tail -f logs/saga-orchestrator.log
```

## 🎯 Next Steps

1. **Start Small**: Begin with Option 1 (Basic Saga Demo)
2. **Add Services**: Gradually add payment-service, notification-service
3. **Add Monitoring**: Start Grafana and Prometheus
4. **Test Failures**: Use chaos testing to see recovery
5. **Scale Up**: Try the distributed database options

## 📚 Key Concepts to Understand

- **Saga Pattern**: Distributed transactions with compensation
- **Outbox Pattern**: Reliable event publishing
- **CQRS**: Separate read/write models
- **Event Sourcing**: Audit trail of all changes
- **Sharding**: Horizontal database partitioning
- **CRDT**: Conflict-free data replication

Each concept is demonstrated in isolated, runnable examples above.
