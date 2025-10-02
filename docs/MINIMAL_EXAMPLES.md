# 🎯 Minimal Working Examples

This document provides the smallest possible examples to demonstrate each key concept.

## 1. Basic Saga Pattern (5 minutes)

**Goal:** See how distributed transactions work with compensation.

### Setup
```bash
# Start only what you need
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Wait 10 seconds for startup
sleep 10
```

### Run Saga Orchestrator
```bash
cd services/saga-orchestrator
cat > .env << EOF
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
REDIS_URL=redis://localhost:6379
LOG_LEVEL=info
EOF

go mod tidy
go run main.go
```

### Test It
```bash
# Create a saga (in another terminal)
curl -X POST http://localhost:8080/api/v1/sagas \
  -H "Content-Type: application/json" \
  -d '{
    "type": "order_processing",
    "data": {
      "order_id": "test-001",
      "user_id": "user-123"
    }
  }'

# Check saga status
curl http://localhost:8080/api/v1/sagas

# You'll see the saga steps and their status
```

**What you learned:** Saga orchestrator coordinates steps and handles failures.

---

## 2. Database Sharding (3 minutes)

**Goal:** Route queries to different database shards.

### Setup
```bash
# Start 3 PostgreSQL instances
docker run -d --name pg-primary -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name pg-shard1 -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:15  
docker run -d --name pg-shard2 -p 5434:5432 -e POSTGRES_PASSWORD=postgres postgres:15

sleep 15
```

### Run Sharding Proxy
```bash
cd services/sharding-proxy
cat > .env << EOF
PRIMARY_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
REPLICA_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
SHARD1_URL=postgresql://postgres:postgres@localhost:5433/postgres?sslmode=disable
SHARD2_URL=postgresql://postgres:postgres@localhost:5434/postgres?sslmode=disable
EOF

go mod tidy
go run main.go
```

### Test It
```bash
# Connect to sharding proxy (port 5432 in the proxy)
# Queries with user_id get routed to specific shards
echo "SELECT * FROM users WHERE user_id = 'user123';" | nc localhost 5432

# The proxy will route based on the user_id hash
```

**What you learned:** Sharding proxy routes queries based on sharding keys.

---

## 3. CRDT Conflict Resolution (2 minutes)

**Goal:** See how conflicts are resolved automatically.

### Setup
```bash
# Start MongoDB
docker run -d --name mongo -p 27017:27017 mongo:7
docker run -d --name redis -p 6379:6379 redis:7-alpine

sleep 10
```

### Run Sync Service
```bash
cd services/sync-service
cat > .env << EOF
MONGO_URL=mongodb://localhost:27017/microservices
REDIS_URL=redis://localhost:6379
LOG_LEVEL=info
EOF

go mod tidy
go run main.go
```

### Test CRDT Merge
```bash
# Simulate conflict: two devices edited the same document
curl -X POST http://localhost:8091/api/v1/crdt/merge \
  -H "Content-Type: application/json" \
  -d '{
    "crdt_type": "LWWRegister",
    "local_state": {
      "value": "Hello from Device 1",
      "timestamp": "2024-01-01T10:00:00Z",
      "node_id": "device1"
    },
    "remote_state": {
      "value": "Hello from Device 2", 
      "timestamp": "2024-01-01T11:00:00Z",
      "node_id": "device2"
    }
  }'

# Result: Device 2's value wins (later timestamp)
# Output: {"value": "Hello from Device 2", "timestamp": "2024-01-01T11:00:00Z"}
```

**What you learned:** CRDTs automatically resolve conflicts using timestamps.

---

## 4. Event Sourcing & Time Travel (4 minutes)

**Goal:** Store events and reconstruct state at any point in time.

### Setup
```bash
# Start databases
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name mongo -p 27017:27017 mongo:7
docker run -d --name clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:latest

sleep 20
```

### Run CQRS Event Store
```bash
cd services/cqrs-event-store
cat > .env << EOF
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
MONGO_URL=mongodb://localhost:27017/microservices
CLICKHOUSE_URL=tcp://localhost:9000/default
LOG_LEVEL=info
EOF

go mod tidy
go run main.go
```

### Test Event Sourcing
```bash
# Create some events
curl -X POST http://localhost:8090/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "account-123",
    "command_type": "CreateAccount",
    "data": {"owner": "John Doe", "initial_balance": 1000}
  }'

curl -X POST http://localhost:8090/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "account-123", 
    "command_type": "Withdraw",
    "data": {"amount": 200}
  }'

# View all events
curl http://localhost:8090/api/v1/events/account-123

# Time travel: restore state at specific time
curl -X POST http://localhost:8090/api/v1/time-travel/restore \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "account-123",
    "point_in_time": "2024-01-01T12:00:00Z"
  }'
```

**What you learned:** Events are stored permanently and state can be reconstructed at any time.

---

## 5. Real-time Analytics Pipeline (3 minutes)

**Goal:** Stream data from operational DB to analytics warehouse.

### Setup
```bash
# Start databases
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:latest
docker run -d --name kafka -p 9092:9092 -e KAFKA_ZOOKEEPER_CONNECT=localhost:2181 confluentinc/cp-kafka:latest

sleep 30
```

### Run Analytics ETL
```bash
cd services/analytics-etl
cat > .env << EOF
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
CLICKHOUSE_URL=tcp://localhost:9000/default
KAFKA_BROKERS=localhost:9092
LOG_LEVEL=info
EOF

go mod tidy
go run main.go
```

### Test Pipeline
```bash
# Check pipeline status
curl http://localhost:8092/api/v1/pipeline/status

# The ETL will automatically:
# 1. Listen for changes in PostgreSQL
# 2. Transform the data
# 3. Load into ClickHouse for analytics
```

**What you learned:** ETL pipelines move data from OLTP to OLAP systems in real-time.

---

## 6. Chaos Testing (2 minutes)

**Goal:** Test system resilience by injecting failures.

### Setup
```bash
# Start test databases
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name postgres-replica -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:15

sleep 15
```

### Run Consistency Testing
```bash
cd services/consistency-testing
cat > .env << EOF
PRIMARY_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
REPLICA_DATABASE_URLS=postgresql://postgres:postgres@localhost:5433/postgres?sslmode=disable
LOG_LEVEL=info
EOF

go mod tidy
go run main.go
```

### Test Chaos
```bash
# Start a simple consistency test
curl -X POST http://localhost:8095/api/v1/tests \
  -H "Content-Type: application/json" \
  -d '{
    "name": "simple_test",
    "workload": "register",
    "nemesis": "process_killer",
    "duration": "30s",
    "client_count": 2
  }'

# Inject a failure
curl -X POST http://localhost:8095/api/v1/nemesis/process/kill \
  -H "Content-Type: application/json" \
  -d '{"process": "postgres"}'

# Check results
curl http://localhost:8095/api/v1/results
```

**What you learned:** Chaos testing finds bugs by simulating real-world failures.

---

## 🧹 Cleanup

After testing, clean up:
```bash
# Stop all containers
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)

# Or clean up specific containers
docker stop postgres redis mongo clickhouse kafka
docker rm postgres redis mongo clickhouse kafka
```

## 🎯 Key Takeaways

1. **Saga Pattern**: Coordinates distributed transactions with compensation
2. **Sharding**: Routes queries to appropriate database partitions  
3. **CRDT**: Resolves conflicts automatically using mathematical properties
4. **Event Sourcing**: Stores all changes as events for complete audit trail
5. **ETL Pipeline**: Moves data from operational to analytical systems
6. **Chaos Testing**: Validates system resilience under failure conditions

Each example demonstrates a core distributed systems concept in isolation. You can combine them as needed for your use case.
