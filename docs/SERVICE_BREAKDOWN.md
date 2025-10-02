# 🏗️ Service Breakdown & Usage Guide

This document breaks down each service so you can understand and use them individually.

## 📦 Core Services (Start Here)

### 1. Saga Orchestrator (`services/saga-orchestrator/`)

**What it does:** Coordinates distributed transactions across multiple services.

**Key files:**
- `main.go` - Entry point
- `internal/orchestrator/orchestrator.go` - Main saga logic
- `internal/models/saga.go` - Data structures

**How to run:**
```bash
# Dependencies: PostgreSQL, Redis, Kafka
docker-compose up -d postgres redis kafka
cd services/saga-orchestrator
go run main.go
```

**API Examples:**
```bash
# Create a saga
curl -X POST http://localhost:8080/api/v1/sagas \
  -H "Content-Type: application/json" \
  -d '{
    "type": "order_processing",
    "data": {"order_id": "123", "user_id": "user1"}
  }'

# Get saga status
curl http://localhost:8080/api/v1/sagas/{saga_id}

# List all sagas
curl http://localhost:8080/api/v1/sagas
```

**What to modify:**
- Add new saga types in `internal/orchestrator/definitions.go`
- Modify compensation logic in `internal/services/compensation_service.go`

### 2. Inventory Service (`services/inventory-service/`)

**What it does:** Manages product inventory with reservations.

**Key files:**
- `main.go` - Entry point
- `internal/handlers/inventory_handler.go` - HTTP endpoints
- `internal/models/inventory.go` - Data structures

**How to run:**
```bash
# Dependencies: PostgreSQL, Redis
docker-compose up -d postgres redis
cd services/inventory-service
go run main.go
```

**API Examples:**
```bash
# Get all items
curl http://localhost:8081/api/v1/items

# Create item
curl -X POST http://localhost:8081/api/v1/items \
  -H "Content-Type: application/json" \
  -d '{"sku": "LAPTOP001", "name": "Gaming Laptop", "quantity": 10}'

# Reserve items
curl -X POST http://localhost:8081/api/v1/items/LAPTOP001/reserve \
  -H "Content-Type: application/json" \
  -d '{"quantity": 2, "reservation_id": "res-123"}'
```

## 🗄️ Database Services

### 3. Sharding Proxy (`services/sharding-proxy/`)

**What it does:** Routes database queries to appropriate shards based on sharding keys.

**Key files:**
- `main.go` - Proxy server and routing logic

**How to run:**
```bash
# Dependencies: PostgreSQL primary + shards
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary postgres-shard1 postgres-shard2
cd services/sharding-proxy
go run main.go
```

**How to use:**
```bash
# Connect to proxy (acts like PostgreSQL)
psql -h localhost -p 5433 -U postgres -d microservices

# Queries with user_id are routed to appropriate shard
SELECT * FROM users WHERE user_id = 'user123';

# Queries without sharding key hit all shards
SELECT COUNT(*) FROM users;
```

**Sharding logic:**
- Queries with `user_id` or `sku` are routed to specific shards
- Hash-based routing using consistent hashing
- Analytical queries go to read replicas

### 4. CQRS Event Store (`services/cqrs-event-store/`)

**What it does:** Implements event sourcing with command/query separation.

**Key files:**
- `main.go` - Entry point
- `internal/eventstore/event_store.go` - Core event store logic
- `internal/timetravel/service.go` - Point-in-time queries

**How to run:**
```bash
# Dependencies: PostgreSQL, MongoDB, ClickHouse, Kafka
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary mongodb-primary clickhouse kafka
cd services/cqrs-event-store
go run main.go
```

**API Examples:**
```bash
# Execute command (write side)
curl -X POST http://localhost:8090/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "order-123",
    "command_type": "CreateOrder",
    "data": {"customer_id": "cust-456", "amount": 100}
  }'

# Query events
curl http://localhost:8090/api/v1/events/order-123

# Time-travel query
curl -X POST http://localhost:8090/api/v1/time-travel/restore \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "order-123",
    "point_in_time": "2024-01-01T12:00:00Z"
  }'
```

## 🔄 Data Sync Services

### 5. Sync Service (`services/sync-service/`)

**What it does:** Handles offline-online synchronization with conflict resolution using CRDTs.

**Key files:**
- `main.go` - Entry point
- `internal/crdt/` - CRDT implementations (LWW-Register, G-Counter, etc.)
- `internal/services/conflict_resolver.go` - Conflict resolution logic

**How to run:**
```bash
# Dependencies: MongoDB, Redis
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  mongodb-primary redis-node1
cd services/sync-service
go run main.go
```

**API Examples:**
```bash
# Register device for sync
curl -X POST http://localhost:8091/api/v1/sync/register-device \
  -H "Content-Type: application/json" \
  -d '{"device_id": "device-123", "user_id": "user-456"}'

# Upload changes from offline device
curl -X POST http://localhost:8091/api/v1/sync/upload \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "device-123",
    "changes": [
      {
        "entity_id": "doc-1",
        "crdt_type": "LWWRegister",
        "operations": [{"type": "set", "value": "hello", "timestamp": "2024-01-01T10:00:00Z"}]
      }
    ]
  }'

# Download changes for device
curl http://localhost:8091/api/v1/sync/download?device_id=device-123
```

### 6. Analytics ETL (`services/analytics-etl/`)

**What it does:** Streams data from operational databases to analytics warehouse in real-time.

**Key files:**
- `main.go` - Entry point
- `internal/pipeline/etl_pipeline.go` - ETL orchestration
- `internal/processors/` - Data transformation logic

**How to run:**
```bash
# Dependencies: PostgreSQL, ClickHouse, Kafka
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary clickhouse kafka
cd services/analytics-etl
go run main.go
```

**API Examples:**
```bash
# Check pipeline status
curl http://localhost:8092/api/v1/pipeline/status

# Get analytics metrics
curl http://localhost:8092/api/v1/analytics/saga-metrics

# Start backfill job
curl -X POST http://localhost:8092/api/v1/backfill/start \
  -H "Content-Type: application/json" \
  -d '{"table": "saga_instances", "start_date": "2024-01-01"}'
```

## 🛠️ Operations Services

### 7. Disaster Recovery (`services/disaster-recovery/`)

**What it does:** Manages backups, point-in-time recovery, and automated failover.

**Key files:**
- `main.go` - Entry point
- `internal/backup/manager.go` - Backup orchestration
- `internal/failover/manager.go` - Failover logic

**How to run:**
```bash
# Dependencies: PostgreSQL primary + replica
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary postgres-replica
cd services/disaster-recovery
go run main.go
```

**API Examples:**
```bash
# Create backup
curl -X POST http://localhost:8093/api/v1/backups \
  -H "Content-Type: application/json" \
  -d '{"type": "full", "databases": ["microservices"]}'

# List backups
curl http://localhost:8093/api/v1/backups

# Restore backup
curl -X POST http://localhost:8093/api/v1/backups/{backup_id}/restore \
  -H "Content-Type: application/json" \
  -d '{"target_database": "microservices_restored"}'

# Check DR status
curl http://localhost:8093/api/v1/dr/status
```

### 8. Schema Migration (`services/schema-migration/`)

**What it does:** Performs zero-downtime database schema changes.

**Key files:**
- `main.go` - Entry point
- `internal/migration/online_engine.go` - Online migration logic

**How to run:**
```bash
# Dependencies: PostgreSQL primary + replica, Redis
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary postgres-replica redis-node1
cd services/schema-migration
go run main.go
```

**API Examples:**
```bash
# Create migration
curl -X POST http://localhost:8094/api/v1/migrations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "add_email_column",
    "up_sql": "ALTER TABLE users ADD COLUMN email VARCHAR(255)",
    "down_sql": "ALTER TABLE users DROP COLUMN email"
  }'

# Execute migration
curl -X POST http://localhost:8094/api/v1/migrations/{migration_id}/execute

# Check migration status
curl http://localhost:8094/api/v1/migrations/{migration_id}/status
```

## 🧪 Testing Services

### 9. Consistency Testing (`services/consistency-testing/`)

**What it does:** Jepsen-style testing for distributed system consistency.

**Key files:**
- `main.go` - Entry point
- `internal/jepsen/framework.go` - Test framework
- `internal/nemesis/` - Fault injection

**How to run:**
```bash
# Dependencies: All databases for testing
docker-compose -f infrastructure/docker-compose-distributed.yml up -d \
  postgres-primary postgres-replica mongodb-primary clickhouse
cd services/consistency-testing
go run main.go
```

**API Examples:**
```bash
# Start consistency test
curl -X POST http://localhost:8095/api/v1/tests \
  -H "Content-Type: application/json" \
  -d '{
    "name": "bank_test",
    "workload": "bank",
    "nemesis": "network_partition",
    "duration": "5m",
    "client_count": 10
  }'

# Check test results
curl http://localhost:8095/api/v1/results/{test_id}

# Inject network partition
curl -X POST http://localhost:8095/api/v1/nemesis/network/partition \
  -H "Content-Type: application/json" \
  -d '{"nodes": ["postgres-primary", "postgres-replica"]}'
```

## 🔧 Configuration Tips

### Environment Variables
Each service uses these common environment variables:
```bash
# Database connections
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/microservices
MONGO_URL=mongodb://localhost:27017/microservices
CLICKHOUSE_URL=tcp://localhost:9000/analytics
REDIS_URL=redis://localhost:6379

# Messaging
KAFKA_BROKERS=localhost:9092

# Observability
JAEGER_ENDPOINT=http://localhost:14268/api/traces
LOG_LEVEL=info
```

### Service Ports
- Saga Orchestrator: 8080
- Inventory Service: 8081
- Payment Service: 8082
- Notification Service: 8083
- CQRS Event Store: 8090
- Sync Service: 8091
- Analytics ETL: 8092
- Disaster Recovery: 8093
- Schema Migration: 8094
- Consistency Testing: 8095

### Development Tips
1. Start with just 1-2 services and their dependencies
2. Use `go run main.go` for development
3. Check `/health` endpoints to verify services are running
4. Use `/metrics` endpoints to see Prometheus metrics
5. Check logs for debugging: most services log to stdout in JSON format
