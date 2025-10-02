# Microservices (Saga, Outbox, Kafka, k8s, tracing)

> Tập trung: transactional workflows, distributed transactions, event-driven reliability, observability.
>

## 🏗️ **Microservices Architecture Overview**

### **Core Services with Saga & Outbox Pattern**

Our microservices architecture implements distributed transactions using the Saga pattern with Outbox for reliable event publishing across MongoDB and PostgreSQL databases:

```mermaid
graph TB
    subgraph "API Gateway"
        GW[API Gateway<br/>Port: 8000]
    end

    subgraph "Core Business Services"
        OS[Order Service<br/>PostgreSQL + Outbox<br/>Port: 8001]
        IS[Inventory Service<br/>MongoDB + Outbox<br/>Port: 8002]
        PS[Payment Service<br/>PostgreSQL + Outbox<br/>Port: 8003]
        NS[Notification Service<br/>MongoDB + Outbox<br/>Port: 8004]
        US[User Service<br/>PostgreSQL + Outbox<br/>Port: 8005]
        WS[Wallet Service<br/>MongoDB + Outbox<br/>Port: 8006]
    end

    subgraph "Orchestration & Coordination"
        SO[Saga Orchestrator<br/>PostgreSQL<br/>Port: 8080]
        ES[Event Store<br/>PostgreSQL<br/>Port: 8081]
    end

    subgraph "Infrastructure Services"
        KAFKA[Kafka Cluster<br/>Ports: 9092-9094]
        REDIS[Redis Cluster<br/>Ports: 6379-6381]
        MONGO[MongoDB Replica Set<br/>Ports: 27017-27019]
        PG[PostgreSQL Cluster<br/>Ports: 5432-5434]
    end

    GW --> OS
    GW --> IS
    GW --> PS
    GW --> NS
    GW --> US
    GW --> WS

    SO --> OS
    SO --> IS
    SO --> PS
    SO --> NS
    SO --> US
    SO --> WS

    OS --> PG
    PS --> PG
    US --> PG
    ES --> PG
    SO --> PG

    IS --> MONGO
    NS --> MONGO
    WS --> MONGO

    OS --> KAFKA
    IS --> KAFKA
    PS --> KAFKA
    NS --> KAFKA
    US --> KAFKA
    WS --> KAFKA
    SO --> KAFKA
    ES --> KAFKA
```

### **Service Responsibilities**

| Service | Database | Outbox | Saga Role | Key Features |
|---------|----------|--------|-----------|--------------|
| **Order Service** | PostgreSQL | ✅ | Initiator | Order lifecycle, inventory reservation |
| **Inventory Service** | MongoDB | ✅ | Participant | Stock management, reservation tracking |
| **Payment Service** | PostgreSQL | ✅ | Participant | Payment processing, refunds |
| **Notification Service** | MongoDB | ✅ | Participant | Multi-channel notifications |
| **User Service** | PostgreSQL | ✅ | Participant | User profiles, preferences |
| **Wallet Service** | MongoDB | ✅ | Participant | Digital wallet, loyalty points |
| **Saga Orchestrator** | PostgreSQL | ✅ | Coordinator | Saga execution, compensation |
| **Event Store** | PostgreSQL | ✅ | Infrastructure | Event sourcing, audit trail |


### 1. End-to-end saga recovery & idempotency under failure (Expert)

- **Scenario:** Long-running saga across inventory, payments, notifications. Random service crashes and network partitions occur.
- **Mục tiêu:** Ensure eventually-consistent outcome and no double-charging.
- **Ràng buộc:** At-least-once delivery semantics, partial failures.
- **Success metrics:** No inconsistent state after failures; duplicate side-effects ≤0.1%.
- **Tools/gợi ý:** Saga pattern orchestration (Temporal/Zeebe), Outbox pattern with Debezium + Kafka, idempotency keys, distributed tracing (OpenTelemetry).
- **Test / Verify:** Chaos testing: kill orchestrator, partition network, restart; check DB states and external side effects (payments).
- **Tips:** Keep compensating transactions reversible, log full saga provenance.

#### 🔧 **Implementation in Codebase**

**Location**: `services/saga-orchestrator/` and related services

**Key Files**:
- `services/saga-orchestrator/main.go` - Main orchestrator service
- `services/saga-orchestrator/internal/saga/` - Saga execution engine
- `services/inventory-service/` - Inventory management with compensation
- `services/payment-service/` - Payment processing with idempotency
- `services/notification-service/` - Notification service

**Architecture**:
```go
// Saga Definition with Compensation
type SagaDefinition struct {
    ID    string
    Steps []SagaStep
}

type SagaStep struct {
    Service        string
    Action         string
    Compensation   string
    IdempotencyKey string
    Timeout        time.Duration
}
```

**Local Testing**:
```bash
# 1. Start all services
cd services/saga-orchestrator && docker-compose up -d

# 2. Run saga with failure injection
go run demo/simple-saga-demo.go

# 3. Test chaos scenarios
./scripts/chaos-test.sh

# 4. Verify idempotency
curl -X POST http://localhost:8080/saga/payment \
  -H "Idempotency-Key: test-123" \
  -d '{"amount": 100, "user_id": "user1"}'

# 5. Check saga state
curl http://localhost:8080/saga/status/saga-123
```

**Monitoring & Verification**:
- Jaeger traces: http://localhost:16686
- Prometheus metrics: http://localhost:9090
- Grafana dashboard: http://localhost:3000

**Key Features Implemented**:
- ✅ Outbox pattern for reliable event publishing
- ✅ Idempotency keys for duplicate prevention
- ✅ Compensation actions for rollback
- ✅ Distributed tracing with OpenTelemetry
- ✅ Chaos testing with network partitions

---

### 2. Outbox + exactly-once processing guarantee (Advanced)

- **Scenario:** Guarantee that state change in DB produces an event once, even on crashes.
- **Mục tiêu:** Implement transactional outbox, CDC to Kafka, consumer dedupe.
- **Ràng buộc:** DB must participate in transactional write + outbox write.
- **Success metrics:** Zero lost events; duplicate rate negligible.
- **Tools/gợi ý:** Outbox table + transactional writes; Debezium for CDC; Kafka with log compaction; consumer dedupe cache in Redis.
- **Test / Verify:** Simulate DB failover during transaction; ensure event appears exactly once in topic.
- **Tips:** Use message keys based on entity id + sequence; consumer dedupe cache in Redis.

#### 🔧 **Implementation in Codebase**

**Location**: `services/cqrs-event-store/` and `infrastructure/debezium/`

**Key Files**:
- `services/cqrs-event-store/outbox/outbox.go` - Outbox pattern implementation
- `services/cqrs-event-store/internal/publisher/` - Event publisher
- `infrastructure/debezium/connector-config.json` - CDC configuration
- `services/inventory-service/internal/outbox/` - Service-specific outbox

**Database Schema**:
```sql
-- Outbox table for transactional event publishing
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    event_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    version INTEGER NOT NULL
);

-- Index for CDC processing
CREATE INDEX idx_outbox_unprocessed ON outbox_events(created_at)
WHERE processed_at IS NULL;
```

**Go Implementation**:
```go
// Transactional outbox write
func (s *Service) UpdateInventoryWithEvent(ctx context.Context,
    inventoryID string, quantity int) error {

    return s.db.WithTransaction(ctx, func(tx *sql.Tx) error {
        // 1. Update business data
        if err := s.updateInventory(tx, inventoryID, quantity); err != nil {
            return err
        }

        // 2. Write to outbox in same transaction
        event := InventoryUpdatedEvent{
            InventoryID: inventoryID,
            NewQuantity: quantity,
            Timestamp:   time.Now(),
        }

        return s.outbox.Publish(tx, "inventory.updated", event)
    })
}
```

**Local Testing**:
```bash
# 1. Start PostgreSQL + Debezium + Kafka
cd infrastructure && docker-compose up -d postgres debezium kafka

# 2. Deploy outbox connector
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @infrastructure/debezium/outbox-connector.json

# 3. Test transactional write
cd services/cqrs-event-store
go test ./outbox -v -run TestOutboxTransaction

# 4. Simulate DB crash during transaction
./scripts/test-db-failover.sh

# 5. Verify exactly-once delivery
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic inventory.events --from-beginning | \
  jq '.payload.after' | sort | uniq -c
```

**Monitoring & Verification**:
```bash
# Check Debezium connector status
curl http://localhost:8083/connectors/outbox-connector/status

# Monitor Kafka topic
kafka-topics --bootstrap-server localhost:9092 --describe --topic inventory.events

# Check consumer lag
kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group inventory-processor
```

**Key Features Implemented**:
- ✅ Transactional outbox pattern
- ✅ Debezium CDC connector
- ✅ Kafka exactly-once semantics
- ✅ Consumer-side deduplication
- ✅ Message ordering guarantees

---

### 3. Event schema evolution & contract testing at scale (Intermediate)

- **Scenario:** Multiple teams consume Kafka topics; schema changes break consumers.
- **Mục tiêu:** Enforce backward/forward compatibility, automated contract tests in CI.
- **Ràng buộc:** Multiple consumers, gradual rollout.
- **Success metrics:** Zero production schema breakages; CI fails on incompatible changes.
- **Tools/gợi ý:** Confluent Schema Registry (Avro/JSON Schema), Pact or Spring Cloud Contract, CI gating.
- **Test / Verify:** Create incompatible schema in CI; assert CI blocked. Inject consumer that expects old schema in staging.
- **Tips:** Version topics or use tolerant deserialization.

#### 🔧 **Implementation in Codebase**

**Location**: `schemas/` and `infrastructure/schema-registry/`

**Key Files**:
- `schemas/avro/inventory-events.avsc` - Avro schema definitions
- `schemas/contracts/inventory-service.yml` - Contract tests
- `infrastructure/schema-registry/docker-compose.yml` - Schema registry setup
- `.github/workflows/schema-validation.yml` - CI pipeline

**Schema Evolution Example**:
```json
// Version 1 - Initial schema
{
  "type": "record",
  "name": "InventoryUpdated",
  "namespace": "com.example.inventory",
  "fields": [
    {"name": "inventoryId", "type": "string"},
    {"name": "quantity", "type": "int"},
    {"name": "timestamp", "type": "long"}
  ]
}

// Version 2 - Backward compatible (added optional field)
{
  "type": "record",
  "name": "InventoryUpdated",
  "namespace": "com.example.inventory",
  "fields": [
    {"name": "inventoryId", "type": "string"},
    {"name": "quantity", "type": "int"},
    {"name": "timestamp", "type": "long"},
    {"name": "location", "type": ["null", "string"], "default": null}
  ]
}
```

**Contract Testing**:
```yaml
# schemas/contracts/inventory-service.yml
interactions:
  - description: "Inventory updated event"
    providerState: "inventory exists"
    request:
      method: POST
      path: /events/inventory-updated
      headers:
        Content-Type: application/json
      body:
        inventoryId: "inv-123"
        quantity: 50
        timestamp: 1640995200000
    response:
      status: 200
```

**Local Testing**:
```bash
# 1. Start Schema Registry
cd infrastructure/schema-registry
docker-compose up -d

# 2. Register initial schema
curl -X POST http://localhost:8081/subjects/inventory-events-value/versions \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d @schemas/avro/inventory-events-v1.avsc

# 3. Test schema compatibility
cd schemas
./scripts/test-schema-compatibility.sh

# 4. Run contract tests
pact-go test --provider inventory-service \
  --pact-dir ./contracts \
  --provider-base-url http://localhost:8080

# 5. Test schema evolution
./scripts/test-schema-evolution.sh
```

**CI Pipeline Integration**:
```yaml
# .github/workflows/schema-validation.yml
name: Schema Validation
on: [push, pull_request]

jobs:
  schema-compatibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Test Schema Compatibility
        run: |
          docker-compose -f infrastructure/schema-registry/docker-compose.yml up -d
          ./schemas/scripts/validate-compatibility.sh

  contract-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run Pact Tests
        run: |
          pact-go test --provider inventory-service
          pact-go publish --consumer-app-version $GITHUB_SHA
```

**Key Features Implemented**:
- ✅ Confluent Schema Registry integration
- ✅ Avro schema evolution rules
- ✅ Contract testing with Pact
- ✅ CI/CD schema validation
- ✅ Backward/forward compatibility checks

---

### 4. Tracing & distributed root cause analysis (Advanced)

- **Scenario:** Intermittent high latency traced to unknown microservice chain.
- **Mục tiêu:** Instrument services with OpenTelemetry, collect traces, detect slow spans, correlate with logs/metrics.
- **Ràng buộc:** High cardinality traces → storage cost.
- **Success metrics:** Mean time to identify root cause reduced by 70% in tests.
- **Tools/gợi ý:** Jaeger/Tempo, Prometheus, Grafana, Loki, sampling strategies.
- **Test / Verify:** Introduce synthetic latency in a service; verify trace finds slow span and alerts.
- **Tips:** Use adaptive sampling; tag traces with business context (user_id, request_id).

#### 🔧 **Implementation in Codebase**

**Location**: `monitoring/` and service instrumentation

**Key Files**:
- `monitoring/jaeger/docker-compose.yml` - Jaeger setup
- `monitoring/prometheus/prometheus.yml` - Metrics configuration
- `services/*/internal/tracing/` - OpenTelemetry instrumentation
- `monitoring/grafana/dashboards/` - Correlation dashboards

**OpenTelemetry Instrumentation**:
```go
// services/inventory-service/internal/tracing/tracer.go
package tracing

import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/jaeger"
    "go.opentelemetry.io/otel/sdk/trace"
)

func InitTracer(serviceName string) error {
    exporter, err := jaeger.New(jaeger.WithCollectorEndpoint(
        jaeger.WithEndpoint("http://localhost:14268/api/traces"),
    ))
    if err != nil {
        return err
    }

    tp := trace.NewTracerProvider(
        trace.WithBatcher(exporter),
        trace.WithSampler(trace.TraceIDRatioBased(0.1)), // 10% sampling
        trace.WithResource(resource.NewWithAttributes(
            semconv.ServiceNameKey.String(serviceName),
            semconv.ServiceVersionKey.String("1.0.0"),
        )),
    )

    otel.SetTracerProvider(tp)
    return nil
}
```

**Service Instrumentation**:
```go
// HTTP middleware with tracing
func TracingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        tracer := otel.Tracer("inventory-service")
        ctx, span := tracer.Start(r.Context(), r.URL.Path)
        defer span.End()

        // Add business context
        span.SetAttributes(
            attribute.String("user.id", r.Header.Get("X-User-ID")),
            attribute.String("request.id", r.Header.Get("X-Request-ID")),
            attribute.String("http.method", r.Method),
        )

        // Inject trace context
        r = r.WithContext(ctx)
        next.ServeHTTP(w, r)
    })
}
```

**Local Testing**:
```bash
# 1. Start observability stack
cd monitoring
docker-compose up -d jaeger prometheus grafana

# 2. Run services with tracing
cd services/inventory-service
JAEGER_ENDPOINT=http://localhost:14268/api/traces go run main.go

# 3. Generate test traffic
./scripts/generate-test-traffic.sh

# 4. Inject synthetic latency
curl -X POST http://localhost:8080/debug/latency \
  -d '{"service": "payment", "delay_ms": 2000}'

# 5. View traces in Jaeger
open http://localhost:16686

# 6. Check correlation in Grafana
open http://localhost:3000/d/distributed-tracing
```

**Alerting Rules**:
```yaml
# monitoring/prometheus/alerts/latency.yml
groups:
  - name: latency_alerts
    rules:
      - alert: HighLatencyDetected
        expr: histogram_quantile(0.95, http_request_duration_seconds) > 1.0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected in {{ $labels.service }}"
          description: "95th percentile latency is {{ $value }}s"

      - alert: SlowSpanDetected
        expr: jaeger_span_duration_seconds > 5.0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Slow span detected"
          runbook: "Check Jaeger trace: {{ $labels.trace_id }}"
```

**Correlation Dashboard**:
```json
{
  "dashboard": {
    "title": "Distributed Tracing Correlation",
    "panels": [
      {
        "title": "Request Latency vs Trace Duration",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, http_request_duration_seconds)",
            "legendFormat": "HTTP P95"
          },
          {
            "expr": "histogram_quantile(0.95, jaeger_span_duration_seconds)",
            "legendFormat": "Trace P95"
          }
        ]
      }
    ]
  }
}
```

**Key Features Implemented**:
- ✅ OpenTelemetry instrumentation
- ✅ Jaeger distributed tracing
- ✅ Adaptive sampling strategies
- ✅ Trace-metrics correlation
- ✅ Automated alerting on slow spans

---

### 5. Rolling upgrades with stateful services (Advanced)

- **Scenario:** Upgrade stateful services (Kafka Connect, DB pods) with zero data loss.
- **Mục tiêu:** Implement safe rolling upgrades with readiness checks & data migration hooks.
- **Ràng buộc:** StatefulSets + leader election.
- **Success metrics:** Zero message loss; no consumer group downtime > threshold.
- **Tools/gợi ý:** Kubernetes statefulset patterns, Pod Disruption Budgets, kafka rolling upgrade recipes.
- **Test / Verify:** Simulate rolling upgrade; measure commit lags, consumer offsets.
- **Tips:** Use graceful shutdown hooks to drain messages.

#### 🔧 **Implementation in Codebase**

**Location**: `infrastructure/k8s/` and `scripts/`

**Key Files**:
- `infrastructure/k8s/statefulsets/` - StatefulSet configurations
- `infrastructure/k8s/pdb/` - Pod Disruption Budgets
- `scripts/rolling-upgrade.sh` - Upgrade automation
- `services/*/internal/graceful/` - Graceful shutdown

**StatefulSet Configuration**:
```yaml
# infrastructure/k8s/statefulsets/kafka-connect.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kafka-connect
spec:
  serviceName: kafka-connect-headless
  replicas: 3
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  template:
    spec:
      containers:
      - name: kafka-connect
        image: confluentinc/cp-kafka-connect:7.4.0
        readinessProbe:
          httpGet:
            path: /connectors
            port: 8083
          initialDelaySeconds: 30
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /
            port: 8083
          initialDelaySeconds: 60
          periodSeconds: 30
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "/opt/graceful-shutdown.sh"]
```

**Pod Disruption Budget**:
```yaml
# infrastructure/k8s/pdb/kafka-connect-pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kafka-connect-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: kafka-connect
```

**Graceful Shutdown Implementation**:
```go
// services/saga-orchestrator/internal/graceful/shutdown.go
package graceful

import (
    "context"
    "os"
    "os/signal"
    "syscall"
    "time"
)

type Server struct {
    httpServer *http.Server
    consumer   *kafka.Consumer
    shutdown   chan os.Signal
}

func (s *Server) Start() error {
    // Setup signal handling
    s.shutdown = make(chan os.Signal, 1)
    signal.Notify(s.shutdown, syscall.SIGTERM, syscall.SIGINT)

    go func() {
        <-s.shutdown
        s.gracefulShutdown()
    }()

    return s.httpServer.ListenAndServe()
}

func (s *Server) gracefulShutdown() {
    log.Info("Starting graceful shutdown...")

    // 1. Stop accepting new requests
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    // 2. Drain Kafka consumer
    s.consumer.Close()

    // 3. Finish processing current requests
    if err := s.httpServer.Shutdown(ctx); err != nil {
        log.Error("Server shutdown error:", err)
    }

    log.Info("Graceful shutdown completed")
}
```

**Rolling Upgrade Script**:
```bash
#!/bin/bash
# scripts/rolling-upgrade.sh

set -e

NAMESPACE=${1:-default}
STATEFULSET=${2:-kafka-connect}
NEW_IMAGE=${3}

echo "Starting rolling upgrade of $STATEFULSET to $NEW_IMAGE"

# 1. Check current status
kubectl get statefulset $STATEFULSET -n $NAMESPACE

# 2. Update image
kubectl patch statefulset $STATEFULSET -n $NAMESPACE \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"'$STATEFULSET'","image":"'$NEW_IMAGE'"}]}}}}'

# 3. Monitor rollout
kubectl rollout status statefulset/$STATEFULSET -n $NAMESPACE --timeout=600s

# 4. Verify all pods are ready
kubectl wait --for=condition=ready pod -l app=$STATEFULSET -n $NAMESPACE --timeout=300s

# 5. Check consumer lag
./scripts/check-consumer-lag.sh

echo "Rolling upgrade completed successfully"
```

**Local Testing**:
```bash
# 1. Deploy StatefulSet locally (kind/minikube)
kubectl apply -f infrastructure/k8s/statefulsets/
kubectl apply -f infrastructure/k8s/pdb/

# 2. Test rolling upgrade
./scripts/rolling-upgrade.sh default kafka-connect confluentinc/cp-kafka-connect:7.5.0

# 3. Monitor during upgrade
watch kubectl get pods -l app=kafka-connect

# 4. Check consumer lag
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group connect-cluster

# 5. Verify zero message loss
./scripts/verify-message-integrity.sh
```

**Monitoring & Verification**:
```bash
# Check StatefulSet status
kubectl describe statefulset kafka-connect

# Monitor consumer lag during upgrade
kubectl exec -it kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group connect-cluster

# Check Pod Disruption Budget
kubectl get pdb kafka-connect-pdb -o yaml
```

**Key Features Implemented**:
- ✅ StatefulSet rolling update strategy
- ✅ Pod Disruption Budgets
- ✅ Graceful shutdown hooks
- ✅ Readiness/liveness probes
- ✅ Consumer lag monitoring

---

### 6. Backpressure & circuit breaking in event-driven flows (Intermediate)

- **Scenario:** Downstream slow service causes upstream producers to overwhelm queues.
- **Mục tiêu:** Implement backpressure propagation, circuit breakers, queue depth controls.
- **Ràng buộc:** Must preserve durability and eventual delivery.
- **Success metrics:** Queue growth bounded; system stays responsive.
- **Tools/gợi ý:** Kafka quotas, consumer lag monitoring, envoy circuit breakers, backpressure-aware clients.
- **Test / Verify:** Slow down consumer artificially; measure queue sizes and throttle behavior.
- **Tips:** Consider rate-limited dead-letter queue policies.

#### 🔧 **Implementation in Codebase**

**Location**: `services/*/internal/circuit/` and `infrastructure/envoy/`

**Key Files**:
- `services/payment-service/internal/circuit/breaker.go` - Circuit breaker implementation
- `services/notification-service/internal/backpressure/` - Backpressure handling
- `infrastructure/envoy/envoy.yaml` - Envoy circuit breaker config
- `infrastructure/kafka/quotas.properties` - Kafka quotas

**Circuit Breaker Implementation**:
```go
// services/payment-service/internal/circuit/breaker.go
package circuit

import (
    "context"
    "errors"
    "sync"
    "time"
)

type State int

const (
    StateClosed State = iota
    StateOpen
    StateHalfOpen
)

type CircuitBreaker struct {
    maxRequests    uint32
    interval       time.Duration
    timeout        time.Duration
    readyToTrip    func(counts Counts) bool
    onStateChange  func(name string, from State, to State)

    mutex      sync.Mutex
    state      State
    generation uint64
    counts     Counts
    expiry     time.Time
}

func (cb *CircuitBreaker) Execute(req func() (interface{}, error)) (interface{}, error) {
    generation, err := cb.beforeRequest()
    if err != nil {
        return nil, err
    }

    defer func() {
        e := recover()
        if e != nil {
            cb.afterRequest(generation, false)
            panic(e)
        }
    }()

    result, err := req()
    cb.afterRequest(generation, err == nil)
    return result, err
}
```

**Backpressure-Aware Consumer**:
```go
// services/notification-service/internal/backpressure/consumer.go
package backpressure

import (
    "context"
    "time"
    "github.com/confluentinc/confluent-kafka-go/kafka"
)

type BackpressureConsumer struct {
    consumer        *kafka.Consumer
    maxQueueSize    int
    processingQueue chan *kafka.Message
    rateLimiter     *time.Ticker
}

func (bc *BackpressureConsumer) Start(ctx context.Context) error {
    bc.processingQueue = make(chan *kafka.Message, bc.maxQueueSize)
    bc.rateLimiter = time.NewTicker(100 * time.Millisecond) // 10 msg/sec max

    go bc.consumeLoop(ctx)
    go bc.processLoop(ctx)

    return nil
}

func (bc *BackpressureConsumer) consumeLoop(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            return
        default:
            msg, err := bc.consumer.ReadMessage(1 * time.Second)
            if err != nil {
                continue
            }

            // Apply backpressure if queue is full
            select {
            case bc.processingQueue <- msg:
                // Message queued successfully
            default:
                // Queue full - apply backpressure
                log.Warn("Processing queue full, applying backpressure")
                time.Sleep(1 * time.Second)

                // Try again or send to DLQ
                select {
                case bc.processingQueue <- msg:
                default:
                    bc.sendToDLQ(msg)
                }
            }
        }
    }
}
```

**Envoy Circuit Breaker Configuration**:
```yaml
# infrastructure/envoy/envoy.yaml
static_resources:
  listeners:
  - name: listener_0
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8080
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          route_config:
            virtual_hosts:
            - name: payment_service
              domains: ["*"]
              routes:
              - match:
                  prefix: "/payment"
                route:
                  cluster: payment_cluster
                  timeout: 30s
  clusters:
  - name: payment_cluster
    connect_timeout: 5s
    type: LOGICAL_DNS
    circuit_breakers:
      thresholds:
      - priority: DEFAULT
        max_connections: 100
        max_pending_requests: 50
        max_requests: 200
        max_retries: 3
        track_remaining: true
    outlier_detection:
      consecutive_5xx: 3
      interval: 30s
      base_ejection_time: 30s
      max_ejection_percent: 50
    load_assignment:
      cluster_name: payment_cluster
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: payment-service
                port_value: 8080
```

**Kafka Quotas Configuration**:
```properties
# infrastructure/kafka/quotas.properties
# Producer quotas (bytes/sec)
producer_byte_rate=1048576  # 1MB/sec per client

# Consumer quotas (bytes/sec)
consumer_byte_rate=2097152  # 2MB/sec per client

# Request quotas (requests/sec)
request_percentage=50       # 50% of request handler threads
```

**Local Testing**:
```bash
# 1. Start services with circuit breakers
cd services/payment-service
CIRCUIT_BREAKER_ENABLED=true go run main.go

# 2. Start Envoy proxy
cd infrastructure/envoy
envoy -c envoy.yaml

# 3. Apply Kafka quotas
kafka-configs --bootstrap-server localhost:9092 \
  --alter --add-config 'producer_byte_rate=1048576,consumer_byte_rate=2097152' \
  --entity-type clients --entity-name payment-service

# 4. Test backpressure
./scripts/test-backpressure.sh

# 5. Monitor circuit breaker state
curl http://localhost:8080/debug/circuit-breaker/status
```

**Load Testing Script**:
```bash
#!/bin/bash
# scripts/test-backpressure.sh

echo "Testing backpressure and circuit breaking..."

# 1. Generate high load
for i in {1..1000}; do
  curl -X POST http://localhost:8080/payment \
    -H "Content-Type: application/json" \
    -d '{"amount": 100, "user_id": "user'$i'"}' &
done

# 2. Monitor queue sizes
watch -n 1 'kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group notification-service | grep LAG'

# 3. Check circuit breaker metrics
curl http://localhost:9090/api/v1/query?query=circuit_breaker_state

# 4. Verify no message loss
./scripts/verify-message-integrity.sh
```

**Key Features Implemented**:
- ✅ Circuit breaker pattern
- ✅ Backpressure propagation
- ✅ Kafka producer/consumer quotas
- ✅ Envoy circuit breakers
- ✅ Dead letter queue handling

---

### 7. Multi-cluster k8s service discovery and cross-cluster event routing (Expert)

- **Scenario:** Two k8s clusters in different regions; you must route events/services gracefully.
- **Mục tiêu:** Cross-cluster Kafka replication, service failover, low latency.
- **Ràng buộc:** Network latency, security, consistency.
- **Success metrics:** Failover time < defined RTO; replicated topics consistent.
- **Tools/gợi ý:** MirrorMaker 2, Confluent Replicator, Istio multi-cluster, Consul, cross-cluster service mesh.
- **Test / Verify:** Simulate cluster outage; measure failover correctness.
- **Tips:** Prefer async replication for throughput; careful with leader elections.

#### 🔧 **Implementation in Codebase**

**Location**: `infrastructure/k8s/multi-cluster/` and `infrastructure/kafka/replication/`

**Key Files**:
- `infrastructure/k8s/multi-cluster/istio-multicluster.yaml` - Istio multi-cluster setup
- `infrastructure/kafka/replication/mirrormaker2.yaml` - MirrorMaker 2 configuration
- `services/*/internal/discovery/` - Service discovery implementation
- `infrastructure/consul/` - Consul service mesh

**Istio Multi-Cluster Setup**:
```yaml
# infrastructure/k8s/multi-cluster/istio-multicluster.yaml
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: primary-cluster
spec:
  values:
    pilot:
      env:
        EXTERNAL_ISTIOD: true
        CROSS_NETWORK_POLICY: true
    global:
      meshID: mesh1
      clusterName: primary
      network: network1
---
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: cross-network-gateway
spec:
  selector:
    istio: eastwestgateway
  servers:
  - port:
      number: 15443
      name: tls
      protocol: TLS
    tls:
      mode: ISTIO_MUTUAL
    hosts:
    - cross-network.local
```

**MirrorMaker 2 Configuration**:
```yaml
# infrastructure/kafka/replication/mirrormaker2.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaMirrorMaker2
metadata:
  name: cross-cluster-mirror
spec:
  version: 3.5.0
  replicas: 3
  connectCluster: "target"
  clusters:
  - alias: "source"
    bootstrapServers: source-kafka:9092
    config:
      config.storage.replication.factor: 3
      offset.storage.replication.factor: 3
      status.storage.replication.factor: 3
  - alias: "target"
    bootstrapServers: target-kafka:9092
    config:
      config.storage.replication.factor: 3
      offset.storage.replication.factor: 3
      status.storage.replication.factor: 3
  mirrors:
  - sourceCluster: "source"
    targetCluster: "target"
    sourceConnector:
      config:
        replication.factor: 3
        offset-syncs.topic.replication.factor: 3
        sync.topic.acls.enabled: "false"
        refresh.topics.interval.seconds: 60
    heartbeatConnector:
      config:
        heartbeats.topic.replication.factor: 3
    checkpointConnector:
      config:
        checkpoints.topic.replication.factor: 3
    topicsPattern: "inventory.*|payment.*|notification.*"
```

**Cross-Cluster Service Discovery**:
```go
// services/inventory-service/internal/discovery/consul.go
package discovery

import (
    "context"
    "fmt"
    "github.com/hashicorp/consul/api"
)

type ConsulDiscovery struct {
    client *api.Client
    config *Config
}

type Config struct {
    ServiceName    string
    DataCenter     string
    Tags           []string
    HealthCheck    string
    CrossCluster   bool
}

func (cd *ConsulDiscovery) Register(ctx context.Context) error {
    registration := &api.AgentServiceRegistration{
        ID:      fmt.Sprintf("%s-%s", cd.config.ServiceName, cd.config.DataCenter),
        Name:    cd.config.ServiceName,
        Tags:    cd.config.Tags,
        Port:    8080,
        Address: cd.getLocalIP(),
        Meta: map[string]string{
            "cluster":    cd.config.DataCenter,
            "region":     cd.getRegion(),
            "version":    "1.0.0",
        },
        Check: &api.AgentServiceCheck{
            HTTP:                           cd.config.HealthCheck,
            Interval:                       "10s",
            Timeout:                        "3s",
            DeregisterCriticalServiceAfter: "30s",
        },
    }

    return cd.client.Agent().ServiceRegister(registration)
}

func (cd *ConsulDiscovery) Discover(serviceName string) ([]*api.ServiceEntry, error) {
    services, _, err := cd.client.Health().Service(serviceName, "", true, &api.QueryOptions{
        Datacenter: cd.config.DataCenter,
    })

    if err != nil {
        // Fallback to cross-cluster discovery
        if cd.config.CrossCluster {
            return cd.discoverCrossCluster(serviceName)
        }
        return nil, err
    }

    return services, nil
}
```

**Cross-Cluster Event Router**:
```go
// services/saga-orchestrator/internal/routing/cross_cluster.go
package routing

import (
    "context"
    "fmt"
)

type CrossClusterRouter struct {
    localProducer  *kafka.Producer
    remoteProducer *kafka.Producer
    failoverConfig *FailoverConfig
}

type FailoverConfig struct {
    PrimaryCluster   string
    SecondaryCluster string
    FailoverTimeout  time.Duration
    HealthCheckURL   string
}

func (ccr *CrossClusterRouter) RouteEvent(ctx context.Context, event *Event) error {
    // Try primary cluster first
    if ccr.isClusterHealthy(ccr.failoverConfig.PrimaryCluster) {
        return ccr.localProducer.Produce(&kafka.Message{
            TopicPartition: kafka.TopicPartition{
                Topic:     &event.Topic,
                Partition: kafka.PartitionAny,
            },
            Key:   []byte(event.Key),
            Value: event.Payload,
            Headers: []kafka.Header{
                {Key: "source-cluster", Value: []byte(ccr.failoverConfig.PrimaryCluster)},
                {Key: "timestamp", Value: []byte(fmt.Sprintf("%d", time.Now().Unix()))},
            },
        }, nil)
    }

    // Failover to secondary cluster
    log.Warn("Primary cluster unhealthy, failing over to secondary")
    return ccr.remoteProducer.Produce(&kafka.Message{
        TopicPartition: kafka.TopicPartition{
            Topic:     &event.Topic,
            Partition: kafka.PartitionAny,
        },
        Key:   []byte(event.Key),
        Value: event.Payload,
        Headers: []kafka.Header{
            {Key: "source-cluster", Value: []byte(ccr.failoverConfig.SecondaryCluster)},
            {Key: "failover", Value: []byte("true")},
        },
    }, nil)
}
```

**Local Testing (Multi-Cluster Simulation)**:
```bash
# 1. Create two kind clusters
kind create cluster --name primary --config infrastructure/k8s/multi-cluster/primary-cluster.yaml
kind create cluster --name secondary --config infrastructure/k8s/multi-cluster/secondary-cluster.yaml

# 2. Install Istio on both clusters
kubectl --context kind-primary apply -f infrastructure/k8s/multi-cluster/istio-primary.yaml
kubectl --context kind-secondary apply -f infrastructure/k8s/multi-cluster/istio-secondary.yaml

# 3. Setup cross-cluster networking
./scripts/setup-cross-cluster-networking.sh

# 4. Deploy MirrorMaker 2
kubectl --context kind-primary apply -f infrastructure/kafka/replication/mirrormaker2.yaml

# 5. Test cross-cluster service discovery
./scripts/test-cross-cluster-discovery.sh

# 6. Simulate cluster failover
./scripts/simulate-cluster-failover.sh primary secondary
```

**Failover Testing Script**:
```bash
#!/bin/bash
# scripts/simulate-cluster-failover.sh

PRIMARY_CLUSTER=$1
SECONDARY_CLUSTER=$2

echo "Testing failover from $PRIMARY_CLUSTER to $SECONDARY_CLUSTER"

# 1. Generate baseline traffic
./scripts/generate-cross-cluster-traffic.sh &
TRAFFIC_PID=$!

# 2. Monitor replication lag
kubectl --context kind-$PRIMARY_CLUSTER exec -it kafka-0 -- \
  kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group mirrormaker2-cluster &

# 3. Simulate primary cluster failure
echo "Simulating primary cluster failure..."
kubectl --context kind-$PRIMARY_CLUSTER scale deployment kafka --replicas=0

# 4. Measure failover time
start_time=$(date +%s)
while ! curl -f http://secondary-cluster-lb/health; do
  sleep 1
done
end_time=$(date +%s)
failover_time=$((end_time - start_time))

echo "Failover completed in ${failover_time} seconds"

# 5. Verify data consistency
./scripts/verify-cross-cluster-consistency.sh

# 6. Cleanup
kill $TRAFFIC_PID
kubectl --context kind-$PRIMARY_CLUSTER scale deployment kafka --replicas=3
```

**Key Features Implemented**:
- ✅ Istio multi-cluster service mesh
- ✅ MirrorMaker 2 cross-cluster replication
- ✅ Consul cross-cluster service discovery
- ✅ Automated failover mechanisms
- ✅ Cross-cluster consistency verification

---

### 8. Observability costs optimization (Intermediate)

- **Scenario:** Traces/logs explode and cost skyrockets.
- **Mục tiêu:** Reduce observability cost while retaining SRE effectiveness.
- **Ràng buộc:** Keep essential traces/logs for business-critical flows.
- **Success metrics:** Reduce storage cost by 50% while keeping 95% of useful alerts.
- **Tools/gợi ý:** Adaptive sampling, log aggregation, retention policies, metric rollups, Grafana Loki.
- **Test / Verify:** Apply sampling, verify critical traces still captured.

#### 🔧 **Implementation in Codebase**

**Location**: `monitoring/` and `services/*/internal/observability/`

**Key Files**:
- `monitoring/jaeger/sampling-config.json` - Adaptive sampling configuration
- `monitoring/loki/loki-config.yaml` - Log aggregation and retention
- `monitoring/prometheus/recording-rules.yaml` - Metric rollups
- `services/*/internal/observability/sampling.go` - Custom sampling logic

**Adaptive Sampling Configuration**:
```json
{
  "service_strategies": [
    {
      "service": "inventory-service",
      "type": "probabilistic",
      "param": 0.1,
      "operation_strategies": [
        {
          "operation": "GET /inventory/critical",
          "type": "probabilistic",
          "param": 1.0
        },
        {
          "operation": "POST /inventory/update",
          "type": "probabilistic",
          "param": 0.5
        }
      ]
    },
    {
      "service": "payment-service",
      "type": "adaptive",
      "max_traces_per_second": 100,
      "operation_strategies": [
        {
          "operation": "POST /payment/process",
          "type": "probabilistic",
          "param": 1.0
        }
      ]
    }
  ],
  "default_strategy": {
    "type": "probabilistic",
    "param": 0.01
  }
}
```

**Smart Sampling Implementation**:
```go
// services/inventory-service/internal/observability/sampling.go
package observability

import (
    "context"
    "math/rand"
    "strings"
    "go.opentelemetry.io/otel/trace"
)

type SmartSampler struct {
    baseSampleRate    float64
    errorSampleRate   float64
    criticalEndpoints map[string]float64
    costBudget        float64
    currentCost       float64
}

func (s *SmartSampler) ShouldSample(parameters trace.SamplingParameters) trace.SamplingResult {
    ctx := parameters.ParentContext
    spanName := parameters.Name

    // Always sample errors
    if s.isErrorSpan(parameters) {
        return trace.SamplingResult{
            Decision: trace.RecordAndSample,
            Tracestate: trace.TraceState{},
        }
    }

    // Always sample critical business operations
    if rate, isCritical := s.criticalEndpoints[spanName]; isCritical {
        if rand.Float64() < rate {
            return trace.SamplingResult{
                Decision: trace.RecordAndSample,
                Tracestate: trace.TraceState{},
            }
        }
    }

    // Adaptive sampling based on cost budget
    if s.currentCost > s.costBudget {
        // Reduce sampling rate when over budget
        adjustedRate := s.baseSampleRate * 0.1
        if rand.Float64() < adjustedRate {
            return trace.SamplingResult{
                Decision: trace.RecordAndSample,
                Tracestate: trace.TraceState{},
            }
        }
    }

    // Default sampling
    if rand.Float64() < s.baseSampleRate {
        return trace.SamplingResult{
            Decision: trace.RecordAndSample,
            Tracestate: trace.TraceState{},
        }
    }

    return trace.SamplingResult{
        Decision: trace.Drop,
        Tracestate: trace.TraceState{},
    }
}
```

**Loki Configuration with Retention**:
```yaml
# monitoring/loki/loki-config.yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    address: 127.0.0.1
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    cache_location: /loki/boltdb-shipper-cache
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  retention_period: 720h  # 30 days

# Retention by log level
table_manager:
  retention_deletes_enabled: true
  retention_period: 720h

# Custom retention rules
compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
```

**Prometheus Recording Rules for Cost Optimization**:
```yaml
# monitoring/prometheus/recording-rules.yaml
groups:
  - name: cost_optimization
    interval: 30s
    rules:
      # High-level business metrics (keep forever)
      - record: business:payment_success_rate
        expr: |
          sum(rate(payment_processed_total{status="success"}[5m])) /
          sum(rate(payment_processed_total[5m]))

      # Medium-level operational metrics (keep 30 days)
      - record: ops:service_error_rate_5m
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) by (service) /
          sum(rate(http_requests_total[5m])) by (service)

      # Detailed metrics (keep 7 days, high resolution)
      - record: detailed:request_duration_p99_1m
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service, endpoint)
          )

  - name: adaptive_sampling
    interval: 60s
    rules:
      # Calculate current trace volume
      - record: observability:trace_volume_per_minute
        expr: sum(rate(jaeger_spans_received_total[1m]))

      # Calculate storage cost proxy
      - record: observability:storage_cost_proxy
        expr: |
          (observability:trace_volume_per_minute * 60 * 24 * 30) +
          (sum(loki_ingester_streams) * 1000)
```

**Log Sampling and Aggregation**:
```go
// services/payment-service/internal/observability/logging.go
package observability

import (
    "context"
    "fmt"
    "math/rand"
    "time"
    "github.com/sirupsen/logrus"
)

type CostAwareLogger struct {
    logger       *logrus.Logger
    sampleRates  map[logrus.Level]float64
    costBudget   float64
    currentCost  float64
    aggregator   *LogAggregator
}

func (cal *CostAwareLogger) Log(level logrus.Level, msg string, fields logrus.Fields) {
    // Always log errors and warnings
    if level >= logrus.WarnLevel {
        cal.logger.WithFields(fields).Log(level, msg)
        return
    }

    // Sample info and debug logs
    sampleRate := cal.sampleRates[level]
    if cal.currentCost > cal.costBudget {
        sampleRate *= 0.1 // Reduce sampling when over budget
    }

    if rand.Float64() < sampleRate {
        cal.logger.WithFields(fields).Log(level, msg)
    } else {
        // Aggregate instead of logging
        cal.aggregator.Aggregate(level, msg, fields)
    }
}

type LogAggregator struct {
    aggregates map[string]*AggregateEntry
    flushInterval time.Duration
}

type AggregateEntry struct {
    Count     int       `json:"count"`
    LastSeen  time.Time `json:"last_seen"`
    Sample    string    `json:"sample"`
}

func (la *LogAggregator) Aggregate(level logrus.Level, msg string, fields logrus.Fields) {
    key := fmt.Sprintf("%s:%s", level.String(), msg)

    if entry, exists := la.aggregates[key]; exists {
        entry.Count++
        entry.LastSeen = time.Now()
    } else {
        la.aggregates[key] = &AggregateEntry{
            Count:    1,
            LastSeen: time.Now(),
            Sample:   msg,
        }
    }
}
```

**Local Testing**:
```bash
# 1. Start observability stack with cost optimization
cd monitoring
docker-compose -f docker-compose-cost-optimized.yml up -d

# 2. Configure adaptive sampling
curl -X POST http://localhost:14268/api/sampling \
  -d @monitoring/jaeger/sampling-config.json

# 3. Generate test load with different patterns
./scripts/generate-observability-load.sh

# 4. Monitor cost metrics
curl http://localhost:9090/api/v1/query?query=observability:storage_cost_proxy

# 5. Verify critical traces are still captured
./scripts/verify-critical-traces.sh

# 6. Check retention policies
curl http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service="payment-service"}' \
  --data-urlencode 'start=1640995200' \
  --data-urlencode 'end=1641081600'
```

**Cost Monitoring Dashboard**:
```json
{
  "dashboard": {
    "title": "Observability Cost Optimization",
    "panels": [
      {
        "title": "Trace Volume vs Cost Budget",
        "type": "graph",
        "targets": [
          {
            "expr": "observability:trace_volume_per_minute",
            "legendFormat": "Traces/min"
          },
          {
            "expr": "observability:storage_cost_proxy",
            "legendFormat": "Storage Cost Proxy"
          }
        ]
      },
      {
        "title": "Sampling Rates by Service",
        "type": "table",
        "targets": [
          {
            "expr": "jaeger_sampling_rate by (service)",
            "format": "table"
          }
        ]
      }
    ]
  }
}
```

**Key Features Implemented**:
- ✅ Adaptive sampling based on cost budget
- ✅ Critical path always-sample policies
- ✅ Log aggregation and retention policies
- ✅ Metric rollups for long-term storage
- ✅ Cost monitoring and alerting

---

## 🚀 **Additional Microservices Implementation**

### 9. Order Service with PostgreSQL Outbox (Advanced)

#### 🔧 **Implementation in Codebase**

**Location**: `services/order-service/`

**Key Files**:
- `services/order-service/main.go` - Main service with HTTP handlers
- `services/order-service/internal/domain/` - Domain models and business logic
- `services/order-service/internal/outbox/` - PostgreSQL outbox implementation
- `services/order-service/internal/saga/` - Saga participant logic

**Order Service Implementation**:
```go
// services/order-service/main.go
package main

import (
    "context"
    "database/sql"
    "encoding/json"
    "log"
    "net/http"
    "time"

    "github.com/gin-gonic/gin"
    "github.com/google/uuid"
    _ "github.com/lib/pq"
)

type OrderService struct {
    db          *sql.DB
    outbox      *OutboxPublisher
    sagaClient  *SagaClient
}

type Order struct {
    ID          string    `json:"id" db:"id"`
    UserID      string    `json:"user_id" db:"user_id"`
    Items       []OrderItem `json:"items"`
    TotalAmount float64   `json:"total_amount" db:"total_amount"`
    Status      string    `json:"status" db:"status"`
    CreatedAt   time.Time `json:"created_at" db:"created_at"`
    UpdatedAt   time.Time `json:"updated_at" db:"updated_at"`
}

type OrderItem struct {
    ProductID string  `json:"product_id"`
    Quantity  int     `json:"quantity"`
    Price     float64 `json:"price"`
}

func (os *OrderService) CreateOrder(c *gin.Context) {
    var req CreateOrderRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(400, gin.H{"error": "Invalid request"})
        return
    }

    // Start database transaction
    tx, err := os.db.BeginTx(c.Request.Context(), nil)
    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to start transaction"})
        return
    }
    defer tx.Rollback()

    // Create order
    order := &Order{
        ID:          uuid.New().String(),
        UserID:      req.UserID,
        Items:       req.Items,
        TotalAmount: calculateTotal(req.Items),
        Status:      "PENDING",
        CreatedAt:   time.Now(),
        UpdatedAt:   time.Now(),
    }

    // Insert order into database
    _, err = tx.ExecContext(c.Request.Context(), `
        INSERT INTO orders (id, user_id, items, total_amount, status, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    `, order.ID, order.UserID, toJSON(order.Items), order.TotalAmount,
       order.Status, order.CreatedAt, order.UpdatedAt)

    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to create order"})
        return
    }

    // Publish order created event via outbox
    event := OrderCreatedEvent{
        OrderID:     order.ID,
        UserID:      order.UserID,
        Items:       order.Items,
        TotalAmount: order.TotalAmount,
        Timestamp:   time.Now(),
    }

    if err := os.outbox.PublishInTx(tx, "order.created", event); err != nil {
        c.JSON(500, gin.H{"error": "Failed to publish event"})
        return
    }

    // Start saga for order processing
    sagaID := uuid.New().String()
    sagaData := OrderProcessingSagaData{
        OrderID:     order.ID,
        UserID:      order.UserID,
        Items:       order.Items,
        TotalAmount: order.TotalAmount,
    }

    if err := os.sagaClient.StartSaga(tx, sagaID, "order-processing", sagaData); err != nil {
        c.JSON(500, gin.H{"error": "Failed to start saga"})
        return
    }

    // Commit transaction
    if err := tx.Commit(); err != nil {
        c.JSON(500, gin.H{"error": "Failed to commit transaction"})
        return
    }

    c.JSON(201, gin.H{
        "order": order,
        "saga_id": sagaID,
    })
}

// Saga compensation handler
func (os *OrderService) CancelOrder(c *gin.Context) {
    orderID := c.Param("id")

    tx, err := os.db.BeginTx(c.Request.Context(), nil)
    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to start transaction"})
        return
    }
    defer tx.Rollback()

    // Update order status
    _, err = tx.ExecContext(c.Request.Context(), `
        UPDATE orders SET status = 'CANCELLED', updated_at = $1 WHERE id = $2
    `, time.Now(), orderID)

    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to cancel order"})
        return
    }

    // Publish cancellation event
    event := OrderCancelledEvent{
        OrderID:   orderID,
        Reason:    "saga_compensation",
        Timestamp: time.Now(),
    }

    if err := os.outbox.PublishInTx(tx, "order.cancelled", event); err != nil {
        c.JSON(500, gin.H{"error": "Failed to publish event"})
        return
    }

    if err := tx.Commit(); err != nil {
        c.JSON(500, gin.H{"error": "Failed to commit transaction"})
        return
    }

    c.JSON(200, gin.H{"status": "cancelled"})
}
```

**PostgreSQL Outbox Implementation**:
```go
// services/order-service/internal/outbox/postgres_outbox.go
package outbox

import (
    "database/sql"
    "encoding/json"
    "time"
)

type OutboxPublisher struct {
    db *sql.DB
}

type OutboxEvent struct {
    ID          string    `db:"id"`
    AggregateID string    `db:"aggregate_id"`
    EventType   string    `db:"event_type"`
    EventData   string    `db:"event_data"`
    CreatedAt   time.Time `db:"created_at"`
    ProcessedAt *time.Time `db:"processed_at"`
    Version     int       `db:"version"`
}

func NewOutboxPublisher(db *sql.DB) *OutboxPublisher {
    return &OutboxPublisher{db: db}
}

func (op *OutboxPublisher) PublishInTx(tx *sql.Tx, eventType string, eventData interface{}) error {
    eventJSON, err := json.Marshal(eventData)
    if err != nil {
        return err
    }

    // Extract aggregate ID from event data
    aggregateID := extractAggregateID(eventData)

    _, err = tx.Exec(`
        INSERT INTO outbox_events (id, aggregate_id, event_type, event_data, created_at, version)
        VALUES ($1, $2, $3, $4, $5, $6)
    `, generateID(), aggregateID, eventType, string(eventJSON), time.Now(), 1)

    return err
}

func (op *OutboxPublisher) GetUnprocessedEvents(limit int) ([]OutboxEvent, error) {
    rows, err := op.db.Query(`
        SELECT id, aggregate_id, event_type, event_data, created_at, version
        FROM outbox_events
        WHERE processed_at IS NULL
        ORDER BY created_at ASC
        LIMIT $1
    `, limit)

    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var events []OutboxEvent
    for rows.Next() {
        var event OutboxEvent
        err := rows.Scan(&event.ID, &event.AggregateID, &event.EventType,
                        &event.EventData, &event.CreatedAt, &event.Version)
        if err != nil {
            return nil, err
        }
        events = append(events, event)
    }

    return events, nil
}

func (op *OutboxPublisher) MarkAsProcessed(eventID string) error {
    _, err := op.db.Exec(`
        UPDATE outbox_events
        SET processed_at = $1
        WHERE id = $2
    `, time.Now(), eventID)

    return err
}
```

**Database Schema**:
```sql
-- services/order-service/migrations/001_create_orders.sql
CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    items JSONB NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_orders_user_id (user_id),
    INDEX idx_orders_status (status),
    INDEX idx_orders_created_at (created_at)
);

-- Outbox table for reliable event publishing
CREATE TABLE IF NOT EXISTS outbox_events (
    id VARCHAR(36) PRIMARY KEY,
    aggregate_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP NULL,
    version INTEGER NOT NULL DEFAULT 1,

    INDEX idx_outbox_unprocessed (created_at) WHERE processed_at IS NULL,
    INDEX idx_outbox_aggregate (aggregate_id, created_at)
);
```

**Local Testing**:
```bash
# 1. Start Order Service infrastructure
cd services/order-service
docker-compose up -d postgres kafka redis

# 2. Run database migrations
migrate -path migrations -database "postgres://user:pass@localhost:5432/orders?sslmode=disable" up

# 3. Build and start service
go build -o order-service main.go
./order-service

# 4. Test order creation
curl -X POST http://localhost:8001/orders \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "items": [
      {"product_id": "prod-1", "quantity": 2, "price": 29.99},
      {"product_id": "prod-2", "quantity": 1, "price": 49.99}
    ]
  }'

# 5. Check outbox events
curl http://localhost:8001/admin/outbox/events

# 6. Test saga compensation
curl -X POST http://localhost:8001/orders/order-123/cancel

# 7. Monitor order status
curl http://localhost:8001/orders/order-123
```

**Key Features Implemented**:
- ✅ PostgreSQL-based order management
- ✅ Transactional outbox pattern
- ✅ Saga orchestration integration
- ✅ Compensation transaction support
- ✅ Event-driven architecture
- ✅ ACID transaction guarantees

---

### 10. Inventory Service with MongoDB Outbox (Advanced)

#### 🔧 **Implementation in Codebase**

**Location**: `services/inventory-service/`

**Key Files**:
- `services/inventory-service/main.go` - Main service with HTTP handlers
- `services/inventory-service/internal/domain/` - Domain models and business logic
- `services/inventory-service/internal/outbox/` - MongoDB outbox implementation
- `services/inventory-service/internal/repository/` - MongoDB repository

**Inventory Service Implementation**:
```go
// services/inventory-service/main.go
package main

import (
    "context"
    "encoding/json"
    "log"
    "net/http"
    "time"

    "github.com/gin-gonic/gin"
    "github.com/google/uuid"
    "go.mongodb.org/mongo-driver/mongo"
    "go.mongodb.org/mongo-driver/mongo/options"
    "go.mongodb.org/mongo-driver/bson"
)

type InventoryService struct {
    db     *mongo.Database
    outbox *MongoOutboxPublisher
}

type InventoryItem struct {
    ID              string    `json:"id" bson:"_id"`
    ProductID       string    `json:"product_id" bson:"product_id"`
    AvailableStock  int       `json:"available_stock" bson:"available_stock"`
    ReservedStock   int       `json:"reserved_stock" bson:"reserved_stock"`
    TotalStock      int       `json:"total_stock" bson:"total_stock"`
    Location        string    `json:"location" bson:"location"`
    LastUpdated     time.Time `json:"last_updated" bson:"last_updated"`
    Version         int       `json:"version" bson:"version"`
}

type StockReservation struct {
    ID            string    `json:"id" bson:"_id"`
    ProductID     string    `json:"product_id" bson:"product_id"`
    OrderID       string    `json:"order_id" bson:"order_id"`
    Quantity      int       `json:"quantity" bson:"quantity"`
    Status        string    `json:"status" bson:"status"` // RESERVED, CONFIRMED, CANCELLED
    ExpiresAt     time.Time `json:"expires_at" bson:"expires_at"`
    CreatedAt     time.Time `json:"created_at" bson:"created_at"`
}

func (is *InventoryService) ReserveStock(c *gin.Context) {
    var req ReserveStockRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(400, gin.H{"error": "Invalid request"})
        return
    }

    // Start MongoDB session for transaction
    session, err := is.db.Client().StartSession()
    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to start session"})
        return
    }
    defer session.EndSession(c.Request.Context())

    // Execute transaction
    result, err := session.WithTransaction(c.Request.Context(), func(sc mongo.SessionContext) (interface{}, error) {
        // Check available stock
        var item InventoryItem
        filter := bson.M{"product_id": req.ProductID}
        err := is.db.Collection("inventory").FindOne(sc, filter).Decode(&item)
        if err != nil {
            return nil, err
        }

        if item.AvailableStock < req.Quantity {
            return nil, &InsufficientStockError{
                ProductID: req.ProductID,
                Available: item.AvailableStock,
                Requested: req.Quantity,
            }
        }

        // Create reservation
        reservation := &StockReservation{
            ID:        uuid.New().String(),
            ProductID: req.ProductID,
            OrderID:   req.OrderID,
            Quantity:  req.Quantity,
            Status:    "RESERVED",
            ExpiresAt: time.Now().Add(15 * time.Minute), // 15 min expiry
            CreatedAt: time.Now(),
        }

        // Insert reservation
        _, err = is.db.Collection("reservations").InsertOne(sc, reservation)
        if err != nil {
            return nil, err
        }

        // Update inventory (optimistic locking with version)
        updateFilter := bson.M{
            "product_id": req.ProductID,
            "version":    item.Version,
        }
        update := bson.M{
            "$inc": bson.M{
                "available_stock": -req.Quantity,
                "reserved_stock":  req.Quantity,
                "version":         1,
            },
            "$set": bson.M{
                "last_updated": time.Now(),
            },
        }

        updateResult, err := is.db.Collection("inventory").UpdateOne(sc, updateFilter, update)
        if err != nil {
            return nil, err
        }

        if updateResult.ModifiedCount == 0 {
            return nil, &OptimisticLockError{ProductID: req.ProductID}
        }

        // Publish event via outbox
        event := StockReservedEvent{
            ReservationID: reservation.ID,
            ProductID:     req.ProductID,
            OrderID:       req.OrderID,
            Quantity:      req.Quantity,
            ExpiresAt:     reservation.ExpiresAt,
            Timestamp:     time.Now(),
        }

        if err := is.outbox.PublishInTx(sc, "stock.reserved", event); err != nil {
            return nil, err
        }

        return reservation, nil
    })

    if err != nil {
        if insufficientErr, ok := err.(*InsufficientStockError); ok {
            c.JSON(409, gin.H{
                "error": "Insufficient stock",
                "details": insufficientErr,
            })
            return
        }
        c.JSON(500, gin.H{"error": err.Error()})
        return
    }

    c.JSON(200, gin.H{"reservation": result})
}

func (is *InventoryService) ConfirmReservation(c *gin.Context) {
    reservationID := c.Param("id")

    session, err := is.db.Client().StartSession()
    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to start session"})
        return
    }
    defer session.EndSession(c.Request.Context())

    _, err = session.WithTransaction(c.Request.Context(), func(sc mongo.SessionContext) (interface{}, error) {
        // Update reservation status
        filter := bson.M{"_id": reservationID, "status": "RESERVED"}
        update := bson.M{
            "$set": bson.M{
                "status": "CONFIRMED",
            },
        }

        result, err := is.db.Collection("reservations").UpdateOne(sc, filter, update)
        if err != nil {
            return nil, err
        }

        if result.ModifiedCount == 0 {
            return nil, &ReservationNotFoundError{ID: reservationID}
        }

        // Get reservation details
        var reservation StockReservation
        err = is.db.Collection("reservations").FindOne(sc, bson.M{"_id": reservationID}).Decode(&reservation)
        if err != nil {
            return nil, err
        }

        // Update inventory - move from reserved to confirmed (reduce total stock)
        inventoryFilter := bson.M{"product_id": reservation.ProductID}
        inventoryUpdate := bson.M{
            "$inc": bson.M{
                "reserved_stock": -reservation.Quantity,
                "total_stock":    -reservation.Quantity,
                "version":        1,
            },
            "$set": bson.M{
                "last_updated": time.Now(),
            },
        }

        _, err = is.db.Collection("inventory").UpdateOne(sc, inventoryFilter, inventoryUpdate)
        if err != nil {
            return nil, err
        }

        // Publish confirmation event
        event := StockConfirmedEvent{
            ReservationID: reservationID,
            ProductID:     reservation.ProductID,
            OrderID:       reservation.OrderID,
            Quantity:      reservation.Quantity,
            Timestamp:     time.Now(),
        }

        return nil, is.outbox.PublishInTx(sc, "stock.confirmed", event)
    })

    if err != nil {
        c.JSON(500, gin.H{"error": err.Error()})
        return
    }

    c.JSON(200, gin.H{"status": "confirmed"})
}

// Saga compensation handler
func (is *InventoryService) CancelReservation(c *gin.Context) {
    reservationID := c.Param("id")

    session, err := is.db.Client().StartSession()
    if err != nil {
        c.JSON(500, gin.H{"error": "Failed to start session"})
        return
    }
    defer session.EndSession(c.Request.Context())

    _, err = session.WithTransaction(c.Request.Context(), func(sc mongo.SessionContext) (interface{}, error) {
        // Get reservation details
        var reservation StockReservation
        filter := bson.M{"_id": reservationID}
        err := is.db.Collection("reservations").FindOne(sc, filter).Decode(&reservation)
        if err != nil {
            return nil, err
        }

        if reservation.Status != "RESERVED" {
            return nil, &InvalidReservationStateError{
                ID:     reservationID,
                Status: reservation.Status,
            }
        }

        // Cancel reservation
        update := bson.M{
            "$set": bson.M{
                "status": "CANCELLED",
            },
        }

        _, err = is.db.Collection("reservations").UpdateOne(sc, filter, update)
        if err != nil {
            return nil, err
        }

        // Restore inventory
        inventoryFilter := bson.M{"product_id": reservation.ProductID}
        inventoryUpdate := bson.M{
            "$inc": bson.M{
                "available_stock": reservation.Quantity,
                "reserved_stock":  -reservation.Quantity,
                "version":         1,
            },
            "$set": bson.M{
                "last_updated": time.Now(),
            },
        }

        _, err = is.db.Collection("inventory").UpdateOne(sc, inventoryFilter, inventoryUpdate)
        if err != nil {
            return nil, err
        }

        // Publish cancellation event
        event := StockCancelledEvent{
            ReservationID: reservationID,
            ProductID:     reservation.ProductID,
            OrderID:       reservation.OrderID,
            Quantity:      reservation.Quantity,
            Reason:        "saga_compensation",
            Timestamp:     time.Now(),
        }

        return nil, is.outbox.PublishInTx(sc, "stock.cancelled", event)
    })

    if err != nil {
        c.JSON(500, gin.H{"error": err.Error()})
        return
    }

    c.JSON(200, gin.H{"status": "cancelled"})
}
```

**MongoDB Outbox Implementation**:
```go
// services/inventory-service/internal/outbox/mongo_outbox.go
package outbox

import (
    "context"
    "encoding/json"
    "time"

    "go.mongodb.org/mongo-driver/bson"
    "go.mongodb.org/mongo-driver/mongo"
    "go.mongodb.org/mongo-driver/mongo/options"
)

type MongoOutboxPublisher struct {
    db *mongo.Database
}

type MongoOutboxEvent struct {
    ID          string    `bson:"_id"`
    AggregateID string    `bson:"aggregate_id"`
    EventType   string    `bson:"event_type"`
    EventData   string    `bson:"event_data"`
    CreatedAt   time.Time `bson:"created_at"`
    ProcessedAt *time.Time `bson:"processed_at,omitempty"`
    Version     int       `bson:"version"`
}

func NewMongoOutboxPublisher(db *mongo.Database) *MongoOutboxPublisher {
    return &MongoOutboxPublisher{db: db}
}

func (mop *MongoOutboxPublisher) PublishInTx(ctx mongo.SessionContext, eventType string, eventData interface{}) error {
    eventJSON, err := json.Marshal(eventData)
    if err != nil {
        return err
    }

    aggregateID := extractAggregateID(eventData)

    event := MongoOutboxEvent{
        ID:          generateID(),
        AggregateID: aggregateID,
        EventType:   eventType,
        EventData:   string(eventJSON),
        CreatedAt:   time.Now(),
        Version:     1,
    }

    _, err = mop.db.Collection("outbox_events").InsertOne(ctx, event)
    return err
}

func (mop *MongoOutboxPublisher) GetUnprocessedEvents(ctx context.Context, limit int) ([]MongoOutboxEvent, error) {
    filter := bson.M{"processed_at": bson.M{"$exists": false}}
    opts := options.Find().SetLimit(int64(limit)).SetSort(bson.M{"created_at": 1})

    cursor, err := mop.db.Collection("outbox_events").Find(ctx, filter, opts)
    if err != nil {
        return nil, err
    }
    defer cursor.Close(ctx)

    var events []MongoOutboxEvent
    if err := cursor.All(ctx, &events); err != nil {
        return nil, err
    }

    return events, nil
}

func (mop *MongoOutboxPublisher) MarkAsProcessed(ctx context.Context, eventID string) error {
    filter := bson.M{"_id": eventID}
    update := bson.M{
        "$set": bson.M{
            "processed_at": time.Now(),
        },
    }

    _, err := mop.db.Collection("outbox_events").UpdateOne(ctx, filter, update)
    return err
}
```

**Local Testing**:
```bash
# 1. Start Inventory Service infrastructure
cd services/inventory-service
docker-compose up -d mongodb kafka redis

# 2. Build and start service
go build -o inventory-service main.go
./inventory-service

# 3. Test stock reservation
curl -X POST http://localhost:8002/inventory/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "prod-123",
    "order_id": "order-456",
    "quantity": 5
  }'

# 4. Test reservation confirmation
curl -X POST http://localhost:8002/inventory/reservations/reservation-id/confirm

# 5. Test saga compensation (cancellation)
curl -X POST http://localhost:8002/inventory/reservations/reservation-id/cancel

# 6. Check inventory status
curl http://localhost:8002/inventory/products/prod-123

# 7. Monitor outbox events
curl http://localhost:8002/admin/outbox/events
```

**Key Features Implemented**:
- ✅ MongoDB-based inventory management
- ✅ Stock reservation with expiry
- ✅ Optimistic locking with versioning
- ✅ MongoDB transactions and outbox
- ✅ Saga compensation support
- ✅ Event-driven stock updates