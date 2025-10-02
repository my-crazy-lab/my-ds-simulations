# 🐳 Simplified Docker Setup

Instead of running the full distributed system, use these simplified Docker Compose files for specific use cases.

## 1. Basic Saga Demo

**File:** `docker-compose-basic.yml`

```yaml
version: '3.8'
services:
  # Core infrastructure
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: microservices
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # Saga orchestrator
  saga-orchestrator:
    build: ./services/saga-orchestrator
    ports:
      - "8080:8080"
    environment:
      - POSTGRES_URL=postgresql://postgres:postgres@postgres:5432/microservices?sslmode=disable
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=info
    depends_on:
      - postgres
      - redis

  # One business service
  inventory-service:
    build: ./services/inventory-service
    ports:
      - "8081:8081"
    environment:
      - POSTGRES_URL=postgresql://postgres:postgres@postgres:5432/microservices?sslmode=disable
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=info
    depends_on:
      - postgres
      - redis

volumes:
  postgres_data:
```

**Usage:**
```bash
# Create the file
cat > docker-compose-basic.yml << 'EOF'
# ... paste the YAML above ...
EOF

# Start services
docker-compose -f docker-compose-basic.yml up -d

# Test
curl -X POST http://localhost:8080/api/v1/sagas \
  -H "Content-Type: application/json" \
  -d '{"type": "order_processing", "data": {"order_id": "test-001"}}'
```

---

## 2. Database Sharding Demo

**File:** `docker-compose-sharding.yml`

```yaml
version: '3.8'
services:
  # PostgreSQL Primary
  postgres-primary:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: microservices
    volumes:
      - pg_primary_data:/var/lib/postgresql/data

  # PostgreSQL Shard 1
  postgres-shard1:
    image: postgres:15-alpine
    ports:
      - "5433:5432"
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: microservices_shard1
    volumes:
      - pg_shard1_data:/var/lib/postgresql/data

  # PostgreSQL Shard 2
  postgres-shard2:
    image: postgres:15-alpine
    ports:
      - "5434:5432"
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: microservices_shard2
    volumes:
      - pg_shard2_data:/var/lib/postgresql/data

  # Sharding Proxy
  sharding-proxy:
    build: ./services/sharding-proxy
    ports:
      - "5435:5432"
    environment:
      - PRIMARY_URL=postgresql://postgres:postgres@postgres-primary:5432/microservices?sslmode=disable
      - REPLICA_URL=postgresql://postgres:postgres@postgres-primary:5432/microservices?sslmode=disable
      - SHARD1_URL=postgresql://postgres:postgres@postgres-shard1:5432/microservices_shard1?sslmode=disable
      - SHARD2_URL=postgresql://postgres:postgres@postgres-shard2:5432/microservices_shard2?sslmode=disable
    depends_on:
      - postgres-primary
      - postgres-shard1
      - postgres-shard2

volumes:
  pg_primary_data:
  pg_shard1_data:
  pg_shard2_data:
```

**Usage:**
```bash
# Start sharding setup
docker-compose -f docker-compose-sharding.yml up -d

# Connect to sharding proxy
psql -h localhost -p 5435 -U postgres -d microservices
```

---

## 3. CRDT Sync Demo

**File:** `docker-compose-sync.yml`

```yaml
version: '3.8'
services:
  # MongoDB for user data
  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db

  # Redis for caching
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # Sync service
  sync-service:
    build: ./services/sync-service
    ports:
      - "8091:8080"
    environment:
      - MONGO_URL=mongodb://mongodb:27017/microservices
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=info
    depends_on:
      - mongodb
      - redis

volumes:
  mongodb_data:
```

**Usage:**
```bash
# Start sync services
docker-compose -f docker-compose-sync.yml up -d

# Test CRDT merge
curl -X POST http://localhost:8091/api/v1/crdt/merge \
  -H "Content-Type: application/json" \
  -d '{
    "crdt_type": "LWWRegister",
    "local_state": {"value": "hello", "timestamp": "2024-01-01T10:00:00Z"},
    "remote_state": {"value": "world", "timestamp": "2024-01-01T11:00:00Z"}
  }'
```

---

## 4. Analytics Pipeline Demo

**File:** `docker-compose-analytics.yml`

```yaml
version: '3.8'
services:
  # Source database
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: microservices
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Analytics database
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"
      - "9000:9000"
    environment:
      CLICKHOUSE_DB: analytics
      CLICKHOUSE_USER: admin
      CLICKHOUSE_PASSWORD: admin123
    volumes:
      - clickhouse_data:/var/lib/clickhouse

  # Message queue
  kafka:
    image: confluentinc/cp-kafka:latest
    ports:
      - "9092:9092"
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000

  # ETL service
  analytics-etl:
    build: ./services/analytics-etl
    ports:
      - "8092:8080"
    environment:
      - POSTGRES_URL=postgresql://postgres:postgres@postgres:5432/microservices?sslmode=disable
      - CLICKHOUSE_URL=tcp://clickhouse:9000/analytics
      - KAFKA_BROKERS=kafka:29092
      - LOG_LEVEL=info
    depends_on:
      - postgres
      - clickhouse
      - kafka

volumes:
  postgres_data:
  clickhouse_data:
```

**Usage:**
```bash
# Start analytics pipeline
docker-compose -f docker-compose-analytics.yml up -d

# Check pipeline status
curl http://localhost:8092/api/v1/pipeline/status
```

---

## 5. Event Sourcing Demo

**File:** `docker-compose-eventsourcing.yml`

```yaml
version: '3.8'
services:
  # Event store
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: microservices
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Read models
  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db

  # Analytics
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse

  # CQRS Event Store
  cqrs-event-store:
    build: ./services/cqrs-event-store
    ports:
      - "8090:8080"
    environment:
      - POSTGRES_URL=postgresql://postgres:postgres@postgres:5432/microservices?sslmode=disable
      - MONGO_URL=mongodb://mongodb:27017/microservices
      - CLICKHOUSE_URL=tcp://clickhouse:9000/default
      - LOG_LEVEL=info
    depends_on:
      - postgres
      - mongodb
      - clickhouse

volumes:
  postgres_data:
  mongodb_data:
  clickhouse_data:
```

**Usage:**
```bash
# Start event sourcing
docker-compose -f docker-compose-eventsourcing.yml up -d

# Create events
curl -X POST http://localhost:8090/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "order-123",
    "command_type": "CreateOrder",
    "data": {"customer": "John", "amount": 100}
  }'

# Time travel
curl -X POST http://localhost:8090/api/v1/time-travel/restore \
  -H "Content-Type: application/json" \
  -d '{
    "aggregate_id": "order-123",
    "point_in_time": "2024-01-01T12:00:00Z"
  }'
```

---

## 🚀 Quick Commands

```bash
# Create any of the above files and run:
docker-compose -f docker-compose-[name].yml up -d

# View logs
docker-compose -f docker-compose-[name].yml logs -f

# Stop services
docker-compose -f docker-compose-[name].yml down

# Clean up everything
docker-compose -f docker-compose-[name].yml down -v
docker system prune -f
```

## 🎯 Which One to Choose?

- **Basic Saga**: Start here to understand distributed transactions
- **Sharding**: When you need to scale database reads/writes
- **Sync**: For mobile apps with offline capabilities
- **Analytics**: For real-time reporting and dashboards
- **Event Sourcing**: For audit trails and time-travel queries

Each setup is independent and focuses on one core concept. You can run multiple setups simultaneously on different ports.
