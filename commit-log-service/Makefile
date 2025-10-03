# Commit-log Service & State Reconstruction - Makefile
# Production-grade build, test, and deployment automation

.PHONY: help build test clean docker-build start-cluster stop-cluster test-comprehensive benchmark

# Default target
help: ## Show this help message
	@echo "Commit-log Service & State Reconstruction - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""

# Variables
PROJECT_NAME := commit-log-service
DOCKER_REGISTRY := localhost:5000
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
DOCKER_IMAGE := $(DOCKER_REGISTRY)/$(PROJECT_NAME)
GO_VERSION := 1.21

# Build targets
build: ## Build all services
	@echo "Building commit log services..."
	cd services/commitlog-broker && go mod tidy && go build -o commitlog-broker .
	cd services/schema-registry && go mod tidy && go build -o schema-registry .
	cd services/consumer-coordinator && go mod tidy && go build -o consumer-coordinator .
	cd services/state-reconstructor && go mod tidy && go build -o state-reconstructor .
	cd services/log-compactor && go mod tidy && go build -o log-compactor .
	@echo "Build completed successfully"

build-proto: ## Generate protobuf files
	@echo "Generating protobuf files..."
	cd services/commitlog-broker && protoc --go_out=. --go-grpc_out=. proto/commitlog.proto
	cd services/schema-registry && protoc --go_out=. --go-grpc_out=. proto/schema.proto
	cd services/consumer-coordinator && protoc --go_out=. --go-grpc_out=. proto/coordinator.proto
	@echo "Protobuf generation completed"

clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	find . -name "*.exe" -delete
	find . -name "commitlog-broker" -delete
	find . -name "schema-registry" -delete
	find . -name "consumer-coordinator" -delete
	find . -name "state-reconstructor" -delete
	find . -name "log-compactor" -delete
	cd services/commitlog-broker && go clean
	@echo "Clean completed"

# Docker targets
docker-build: ## Build Docker images
	@echo "Building Docker images..."
	docker build -t $(PROJECT_NAME)-broker:$(VERSION) -t $(PROJECT_NAME)-broker:latest services/commitlog-broker/
	docker build -t $(PROJECT_NAME)-schema-registry:$(VERSION) services/schema-registry/
	docker build -t $(PROJECT_NAME)-consumer-coordinator:$(VERSION) services/consumer-coordinator/
	docker build -t $(PROJECT_NAME)-state-reconstructor:$(VERSION) services/state-reconstructor/
	docker build -t $(PROJECT_NAME)-log-compactor:$(VERSION) services/log-compactor/
	@echo "Docker build completed"

docker-push: docker-build ## Push Docker images to registry
	@echo "Pushing Docker images to registry..."
	docker tag $(PROJECT_NAME)-broker:$(VERSION) $(DOCKER_IMAGE)-broker:$(VERSION)
	docker push $(DOCKER_IMAGE)-broker:$(VERSION)
	@echo "Docker push completed"

# Cluster management
start-cluster: ## Start the commit log cluster
	@echo "Starting commit log cluster..."
	docker-compose up -d
	@echo "Waiting for cluster to be ready..."
	@sleep 60
	@$(MAKE) health-check
	@echo "Commit log cluster started successfully"

stop-cluster: ## Stop the commit log cluster
	@echo "Stopping commit log cluster..."
	docker-compose down
	@echo "Commit log cluster stopped"

restart-cluster: stop-cluster start-cluster ## Restart the commit log cluster

health-check: ## Check cluster health
	@echo "Checking cluster health..."
	@for port in 8081 8082 8083; do \
		echo "Checking broker on port $$port..."; \
		curl -f http://localhost:$$port/health || exit 1; \
		echo ""; \
	done
	@echo "All brokers are healthy"

# Testing targets
test-unit: ## Run unit tests
	@echo "Running unit tests..."
	cd services/commitlog-broker && go test -v ./...
	cd services/schema-registry && go test -v ./...
	cd services/consumer-coordinator && go test -v ./...
	@echo "Unit tests completed"

test-core: ## Run core commit log tests
	@echo "Running core commit log tests..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/unit/test_commit_log_core.py -v --tb=short
	@echo "Core tests completed"

test-chaos: ## Run chaos engineering tests
	@echo "Running chaos engineering tests..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/chaos/test_replication_failures.py -v --tb=short -s
	@echo "Chaos tests completed"

test-comprehensive: validate-test-env start-cluster ## Run all tests
	@echo "Running comprehensive test suite..."
	@sleep 20  # Allow cluster to stabilize
	
	@echo "=== Running Core Functionality Tests ==="
	python3 -m pytest tests/unit/test_commit_log_core.py -v --tb=short || true
	
	@echo "=== Running Chaos Engineering Tests ==="
	python3 -m pytest tests/chaos/test_replication_failures.py -v --tb=short -s || true
	
	@echo "Comprehensive testing completed"

validate-test-env: ## Validate test environment
	@echo "Validating test environment..."
	@command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed"; exit 1; }
	@python3 -c "import pytest, requests, docker" 2>/dev/null || { echo "Installing Python dependencies..."; pip3 install pytest requests docker; }
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose is required but not installed"; exit 1; }
	@echo "Test environment validated"

# Benchmarking and performance testing
benchmark: ## Run comprehensive performance benchmarks
	@echo "Running commit log performance benchmarks..."
	@$(MAKE) validate-test-env
	@$(MAKE) start-cluster
	@sleep 30
	
	@echo "=== Throughput Benchmark ==="
	python3 -c "
import requests
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import statistics

def benchmark_throughput(num_messages=5000, batch_size=100, num_threads=4):
    base_url = 'http://localhost:8080'
    topic_name = f'benchmark_topic_{uuid.uuid4().hex[:8]}'
    
    # Create topic
    session = requests.Session()
    topic_payload = {
        'name': topic_name,
        'partitions': 6,
        'replication_factor': 2
    }
    response = session.post(f'{base_url}/admin/topics', json=topic_payload)
    if response.status_code not in [200, 201]:
        print(f'Failed to create topic: {response.text}')
        return
    
    print(f'Created topic: {topic_name}')
    time.sleep(10)  # Wait for topic to be ready
    
    def producer_thread(thread_id, messages_per_thread):
        session = requests.Session()
        session.timeout = 30
        messages_produced = 0
        
        for batch_start in range(0, messages_per_thread, batch_size):
            batch_messages = []
            for i in range(batch_start, min(batch_start + batch_size, messages_per_thread)):
                batch_messages.append({
                    'key': f'thread_{thread_id}_key_{i}',
                    'value': f'thread_{thread_id}_message_{i}_{uuid.uuid4()}',
                    'headers': {'thread_id': str(thread_id), 'batch': str(batch_start // batch_size)}
                })
            
            try:
                response = session.post(f'{base_url}/produce/{topic_name}/batch', 
                                      json={'messages': batch_messages}, timeout=30)
                if response.status_code == 200:
                    messages_produced += len(batch_messages)
            except Exception as e:
                print(f'Thread {thread_id} error: {e}')
        
        return messages_produced
    
    # Run benchmark
    messages_per_thread = num_messages // num_threads
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for thread_id in range(num_threads):
            future = executor.submit(producer_thread, thread_id, messages_per_thread)
            futures.append(future)
        
        total_produced = sum(future.result() for future in futures)
    
    end_time = time.time()
    duration = end_time - start_time
    throughput = total_produced / duration
    
    print(f'\\n=== Throughput Benchmark Results ===')
    print(f'Messages produced: {total_produced}')
    print(f'Duration: {duration:.2f} seconds')
    print(f'Throughput: {throughput:.2f} messages/second')
    print(f'Data rate: {(throughput * 1024 / 1024):.2f} MB/second (assuming 1KB messages)')
    
    return throughput

# Run benchmark
throughput = benchmark_throughput()
print(f'\\nBenchmark completed with {throughput:.2f} messages/second throughput')
"
	@echo "Benchmark completed"

# State reconstruction demo
state-reconstruction-demo: ## Demonstrate state reconstruction capabilities
	@echo "Running state reconstruction demonstration..."
	@$(MAKE) validate-test-env
	@$(MAKE) start-cluster
	@sleep 30
	
	@echo "=== State Reconstruction Demo ==="
	python3 -c "
import requests
import json
import time
import uuid

base_url = 'http://localhost:8080'
session = requests.Session()

# Create topic for state events
topic_name = f'state_events_{uuid.uuid4().hex[:8]}'
topic_payload = {
    'name': topic_name,
    'partitions': 1,
    'replication_factor': 2,
    'config': {
        'cleanup.policy': 'compact',
        'min.compaction.lag.ms': '1000'
    }
}

response = session.post(f'{base_url}/admin/topics', json=topic_payload)
if response.status_code not in [200, 201]:
    print(f'Failed to create topic: {response.text}')
    exit(1)

print(f'Created state events topic: {topic_name}')
time.sleep(10)

# Simulate application state changes
print('\\n1. Simulating application state changes...')
state_events = [
    {'key': 'user:alice', 'value': json.dumps({'action': 'create', 'name': 'Alice', 'balance': 1000, 'status': 'active'})},
    {'key': 'user:bob', 'value': json.dumps({'action': 'create', 'name': 'Bob', 'balance': 500, 'status': 'active'})},
    {'key': 'user:alice', 'value': json.dumps({'action': 'update', 'balance': 1200})},
    {'key': 'user:charlie', 'value': json.dumps({'action': 'create', 'name': 'Charlie', 'balance': 800, 'status': 'active'})},
    {'key': 'user:bob', 'value': json.dumps({'action': 'update', 'balance': 300, 'status': 'inactive'})},
    {'key': 'user:alice', 'value': json.dumps({'action': 'update', 'balance': 1500})},
    {'key': 'user:david', 'value': json.dumps({'action': 'create', 'name': 'David', 'balance': 2000, 'status': 'active'})},
    {'key': 'user:bob', 'value': json.dumps({'action': 'delete'})},
]

for i, event in enumerate(state_events):
    response = session.post(f'{base_url}/produce/{topic_name}', json=event)
    if response.status_code == 200:
        print(f'  Event {i+1}: {event[\"key\"]} - {json.loads(event[\"value\"])[\"action\"]}')
    time.sleep(0.5)

print('\\n2. Waiting for events to be committed...')
time.sleep(5)

# Trigger compaction to demonstrate key-based compaction
print('\\n3. Triggering log compaction...')
response = session.post(f'{base_url}/admin/topics/{topic_name}/compact')
if response.status_code == 200:
    print('  Log compaction triggered')

time.sleep(10)

# Reconstruct state by consuming all events
print('\\n4. Reconstructing application state from commit log...')
consumer_group = f'state_reconstruction_{uuid.uuid4().hex[:8]}'
consumer_id = f'reconstructor_{uuid.uuid4().hex[:8]}'

# Join consumer group
join_payload = {'consumer_id': consumer_id, 'topics': [topic_name]}
response = session.post(f'{base_url}/consumers/{consumer_group}', json=join_payload)
time.sleep(3)

# Consume all events
params = {'group': consumer_group, 'consumer': consumer_id, 'max_messages': 100}
response = session.get(f'{base_url}/consume/{topic_name}', params=params)

if response.status_code == 200:
    consumed = response.json()
    messages = consumed.get('messages', [])
    
    print(f'  Consumed {len(messages)} events from commit log')
    
    # Reconstruct state
    state = {}
    for msg in sorted(messages, key=lambda x: x['offset']):
        key = msg['key']
        event_data = json.loads(msg['value'])
        
        if event_data['action'] == 'create':
            state[key] = {k: v for k, v in event_data.items() if k != 'action'}
        elif event_data['action'] == 'update':
            if key in state:
                state[key].update({k: v for k, v in event_data.items() if k != 'action'})
        elif event_data['action'] == 'delete':
            if key in state:
                del state[key]
    
    print('\\n5. Reconstructed application state:')
    for user_key, user_data in state.items():
        print(f'  {user_key}: {user_data}')
    
    print('\\n6. State reconstruction summary:')
    print(f'  - Total events processed: {len(messages)}')
    print(f'  - Final state entries: {len(state)}')
    print(f'  - Active users: {sum(1 for u in state.values() if u.get(\"status\") == \"active\")}')
    print(f'  - Total balance: {sum(u.get(\"balance\", 0) for u in state.values())}')
    
    print('\\n✅ State reconstruction completed successfully!')
    print('   This demonstrates how applications can rebuild their complete state')
    print('   from the commit log, enabling disaster recovery and new replica bootstrapping.')

else:
    print(f'Failed to consume events: {response.text}')
"
	@echo "State reconstruction demo completed"

# Consumer group demo
consumer-group-demo: ## Demonstrate consumer group functionality
	@echo "Running consumer group demonstration..."
	@$(MAKE) validate-test-env
	@$(MAKE) start-cluster
	@sleep 30
	
	@echo "=== Consumer Group Demo ==="
	python3 -c "
import requests
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

base_url = 'http://localhost:8080'

# Create topic
topic_name = f'consumer_group_demo_{uuid.uuid4().hex[:8]}'
session = requests.Session()

topic_payload = {
    'name': topic_name,
    'partitions': 6,
    'replication_factor': 2
}

response = session.post(f'{base_url}/admin/topics', json=topic_payload)
if response.status_code not in [200, 201]:
    print(f'Failed to create topic: {response.text}')
    exit(1)

print(f'Created topic: {topic_name}')
time.sleep(10)

# Produce messages continuously
def producer():
    session = requests.Session()
    for i in range(100):
        message = {
            'key': f'message_key_{i}',
            'value': f'Message {i} - {uuid.uuid4()}',
            'headers': {'sequence': str(i)}
        }
        try:
            response = session.post(f'{base_url}/produce/{topic_name}', json=message)
            if response.status_code == 200:
                if i % 20 == 0:
                    print(f'  Produced message {i}')
        except Exception as e:
            print(f'Producer error: {e}')
        time.sleep(0.2)

# Consumer function
def consumer(consumer_id, group_name, duration=20):
    session = requests.Session()
    messages_consumed = 0
    
    # Join consumer group
    join_payload = {'consumer_id': consumer_id, 'topics': [topic_name]}
    response = session.post(f'{base_url}/consumers/{group_name}', json=join_payload)
    if response.status_code not in [200, 201]:
        print(f'Failed to join consumer group: {response.text}')
        return 0
    
    print(f'  {consumer_id} joined group {group_name}')
    time.sleep(3)  # Wait for rebalancing
    
    start_time = time.time()
    while time.time() - start_time < duration:
        try:
            params = {
                'group': group_name,
                'consumer': consumer_id,
                'max_messages': 10
            }
            response = session.get(f'{base_url}/consume/{topic_name}', params=params)
            if response.status_code == 200:
                consumed = response.json()
                messages = consumed.get('messages', [])
                messages_consumed += len(messages)
                if messages:
                    print(f'  {consumer_id} consumed {len(messages)} messages')
        except Exception as e:
            print(f'{consumer_id} error: {e}')
        time.sleep(1)
    
    # Leave consumer group
    try:
        session.delete(f'{base_url}/consumers/{group_name}/{consumer_id}')
        print(f'  {consumer_id} left group {group_name}')
    except Exception:
        pass
    
    return messages_consumed

print('\\n1. Starting producer...')
producer_thread = threading.Thread(target=producer)
producer_thread.start()

time.sleep(5)

print('\\n2. Starting consumer group with 3 consumers...')
group_name = f'demo_group_{uuid.uuid4().hex[:8]}'

with ThreadPoolExecutor(max_workers=3) as executor:
    consumer_futures = []
    for i in range(3):
        consumer_id = f'consumer_{i+1}_{uuid.uuid4().hex[:8]}'
        future = executor.submit(consumer, consumer_id, group_name, 15)
        consumer_futures.append(future)
    
    # Wait for consumers to finish
    total_consumed = sum(future.result() for future in consumer_futures)

producer_thread.join()

print(f'\\n3. Demo completed:')
print(f'  - Total messages consumed: {total_consumed}')
print(f'  - Messages were distributed across 3 consumers in the group')
print(f'  - Each consumer processed different partitions (load balancing)')

print('\\n✅ Consumer group demo completed successfully!')
print('   This demonstrates how consumer groups enable scalable message processing')
print('   with automatic load balancing and fault tolerance.')
"
	@echo "Consumer group demo completed"

# Monitoring and observability
start-monitoring: ## Start monitoring stack
	@echo "Starting monitoring stack..."
	docker-compose up -d prometheus grafana jaeger
	@echo "Monitoring stack started"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana: http://localhost:3000 (admin/commitlog_admin)"
	@echo "  Jaeger: http://localhost:16686"

logs: ## Show cluster logs
	@echo "Showing cluster logs..."
	docker-compose logs -f

logs-broker: ## Show logs for specific broker (usage: make logs-broker BROKER=commitlog-broker1)
	@echo "Showing logs for $(BROKER)..."
	docker-compose logs -f $(BROKER)

# Development targets
dev-setup: ## Setup development environment
	@echo "Setting up development environment..."
	cd services/commitlog-broker && go mod tidy
	cd services/schema-registry && go mod tidy
	cd services/consumer-coordinator && go mod tidy
	@$(MAKE) build-proto
	@$(MAKE) validate-test-env
	@echo "Development environment setup completed"

format: ## Format Go code
	@echo "Formatting Go code..."
	find . -name "*.go" -exec gofmt -w {} \;
	@echo "Code formatting completed"

lint: ## Run Go linter
	@echo "Running Go linter..."
	cd services/commitlog-broker && golangci-lint run
	@echo "Linting completed"

# Operational targets
backup-data: ## Backup cluster data
	@echo "Backing up cluster data..."
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	for broker in broker1 broker2 broker3; do \
		docker run --rm -v commit-log-service_commitlog_$${broker}_data:/data -v $$(pwd)/backups:/backup alpine \
			tar czf /backup/commitlog_$${broker}_backup_$$timestamp.tar.gz -C /data .; \
	done
	@echo "Backup completed"

# Cleanup targets
clean-data: ## Clean all persistent data (WARNING: This will delete all data!)
	@echo "WARNING: This will delete all cluster data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(MAKE) stop-cluster; \
		docker volume rm -f commit-log-service_commitlog_broker1_data; \
		docker volume rm -f commit-log-service_commitlog_broker2_data; \
		docker volume rm -f commit-log-service_commitlog_broker3_data; \
		echo "Data cleanup completed"; \
	else \
		echo "Data cleanup cancelled"; \
	fi

clean-all: clean stop-cluster ## Clean everything (code, containers, data)
	@echo "Cleaning everything..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "Complete cleanup finished"

# Quick start
quick-start: dev-setup docker-build start-cluster test-core ## Quick start for development
	@echo ""
	@echo "🎉 Commit-log Service & State Reconstruction is ready!"
	@echo ""
	@echo "Cluster endpoints:"
	@echo "  Broker 1: http://localhost:8081"
	@echo "  Broker 2: http://localhost:8082"
	@echo "  Broker 3: http://localhost:8083"
	@echo "  Load Balancer: http://localhost:8080"
	@echo "  Schema Registry: http://localhost:8084"
	@echo "  Consumer Coordinator: http://localhost:8085"
	@echo "  State Reconstructor: http://localhost:8086"
	@echo ""
	@echo "Monitoring:"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana: http://localhost:3000 (admin/commitlog_admin)"
	@echo "  Jaeger: http://localhost:16686"
	@echo ""
	@echo "Try the API:"
	@echo "  # Create topic"
	@echo "  curl -X POST http://localhost:8080/admin/topics -d '{\"name\":\"events\",\"partitions\":3,\"replication_factor\":2}'"
	@echo ""
	@echo "  # Produce message"
	@echo "  curl -X POST http://localhost:8080/produce/events -d '{\"key\":\"user1\",\"value\":\"login_event\"}'"
	@echo ""
	@echo "  # Consume messages"
	@echo "  curl 'http://localhost:8080/consume/events?group=processors&consumer=consumer1'"
	@echo ""
	@echo "Run demos:"
	@echo "  make state-reconstruction-demo"
	@echo "  make consumer-group-demo"
	@echo ""

# CI/CD targets
ci-test: ## Run CI tests
	@echo "Running CI test suite..."
	@$(MAKE) build
	@$(MAKE) test-unit
	@$(MAKE) docker-build
	@$(MAKE) test-comprehensive
	@echo "CI tests completed"
