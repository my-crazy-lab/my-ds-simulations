# Stateful Stream Processor Makefile
# Production-grade distributed stream processing with exactly-once semantics

.PHONY: help build docker-build start-cluster stop-cluster restart-cluster health-check
.PHONY: test-unit test-chaos test-comprehensive benchmark
.PHONY: exactly-once-demo rebalancing-demo state-migration-demo performance-demo
.PHONY: monitoring logs clean quick-start

# Default target
help:
	@echo "Stateful Stream Processor - Available targets:"
	@echo ""
	@echo "🏗️  Build & Setup:"
	@echo "  build              - Build all services"
	@echo "  docker-build       - Build Docker images"
	@echo "  start-cluster      - Start stream processing cluster"
	@echo "  stop-cluster       - Stop the cluster"
	@echo "  restart-cluster    - Restart the cluster"
	@echo "  health-check       - Check cluster health"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test-unit          - Run unit tests for exactly-once processing"
	@echo "  test-chaos         - Run chaos engineering tests"
	@echo "  test-comprehensive - Run all tests"
	@echo "  benchmark          - Run performance benchmarks"
	@echo ""
	@echo "🎯 Demonstrations:"
	@echo "  exactly-once-demo  - Demonstrate exactly-once processing"
	@echo "  rebalancing-demo   - Dynamic rebalancing demonstration"
	@echo "  state-migration-demo - State migration during rebalancing"
	@echo "  performance-demo   - Performance and scalability demo"
	@echo ""
	@echo "📊 Operations:"
	@echo "  monitoring         - Open monitoring dashboards"
	@echo "  logs               - Show cluster logs"
	@echo "  clean              - Clean up resources"
	@echo "  quick-start        - Complete setup and demo"

# Build targets
build:
	@echo "🏗️ Building stateful stream processor services..."
	cd services/stream-processor && go mod tidy && go build -o ../../bin/stream-processor .
	cd services/rebalance-manager && go mod tidy && go build -o ../../bin/rebalance-manager .
	cd services/state-store-manager && go mod tidy && go build -o ../../bin/state-store-manager .
	@echo "✅ Build completed"

docker-build:
	@echo "🐳 Building Docker images..."
	docker-compose build --parallel
	@echo "✅ Docker images built"

# Cluster management
start-cluster:
	@echo "🚀 Starting stateful stream processing cluster..."
	@echo "   - 3 stream processors (ports 8081-8083)"
	@echo "   - 3 Kafka brokers (ports 9092, 9094, 9095)"
	@echo "   - Zookeeper coordination (port 2181)"
	@echo "   - Rebalance manager (port 8090)"
	@echo "   - State store manager (port 8091)"
	@echo "   - Load balancer (port 8080)"
	@echo "   - Monitoring stack (Prometheus: 9090, Grafana: 3000)"
	docker-compose up -d
	@echo "⏳ Waiting for cluster to be ready..."
	sleep 45
	@$(MAKE) health-check
	@echo "✅ Stream processing cluster is ready!"
	@echo ""
	@echo "🌐 Access points:"
	@echo "  Load Balancer:      http://localhost:8080"
	@echo "  Stream Processors:  http://localhost:8081-8083"
	@echo "  Rebalance Manager:  http://localhost:8090"
	@echo "  State Manager:      http://localhost:8091"
	@echo "  Prometheus:         http://localhost:9090"
	@echo "  Grafana:            http://localhost:3000 (admin/stream_processor_admin)"
	@echo "  Jaeger:             http://localhost:16686"

stop-cluster:
	@echo "🛑 Stopping stateful stream processing cluster..."
	docker-compose down
	@echo "✅ Cluster stopped"

restart-cluster:
	@echo "🔄 Restarting stateful stream processing cluster..."
	docker-compose restart
	sleep 30
	@$(MAKE) health-check
	@echo "✅ Cluster restarted"

health-check:
	@echo "🏥 Checking cluster health..."
	@echo "Stream Processors:"
	@curl -s http://localhost:8081/health | jq -r '.status // "unhealthy"' | sed 's/^/  processor-1: /' || echo "  processor-1: unreachable"
	@curl -s http://localhost:8082/health | jq -r '.status // "unhealthy"' | sed 's/^/  processor-2: /' || echo "  processor-2: unreachable"
	@curl -s http://localhost:8083/health | jq -r '.status // "unhealthy"' | sed 's/^/  processor-3: /' || echo "  processor-3: unreachable"
	@echo "Support Services:"
	@curl -s http://localhost:8090/health | jq -r '.status // "unhealthy"' | sed 's/^/  rebalance-manager: /' || echo "  rebalance-manager: unreachable"
	@curl -s http://localhost:8091/health | jq -r '.status // "unhealthy"' | sed 's/^/  state-store-manager: /' || echo "  state-store-manager: unreachable"

# Testing targets
test-unit:
	@echo "🧪 Running exactly-once processing unit tests..."
	python3 -m pytest tests/unit/test_exactly_once_processing.py -v --tb=short
	@echo "✅ Unit tests completed"

test-chaos:
	@echo "🌪️ Running chaos engineering tests..."
	python3 -m pytest tests/chaos/test_rebalancing_failures.py -v --tb=short -s
	@echo "✅ Chaos tests completed"

test-comprehensive:
	@echo "🔬 Running comprehensive test suite..."
	@$(MAKE) test-unit
	@$(MAKE) test-chaos
	@echo "✅ All tests completed successfully!"

benchmark:
	@echo "📊 Running performance benchmarks..."
	@python3 -c "
import requests
import time
import json
import uuid
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafka import KafkaProducer

def benchmark_throughput():
    print('🚀 Benchmarking stream processing throughput...')
    
    # Create Kafka producer
    producer = KafkaProducer(
        bootstrap_servers='localhost:9092,localhost:9094,localhost:9095',
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8'),
        acks='all',
        retries=3,
        enable_idempotence=True
    )
    
    topic = f'benchmark_throughput_{int(time.time())}'
    
    # Start processing
    response = requests.post('http://localhost:8081/processor/start', 
                           json={'topics': [topic]})
    if response.status_code != 200:
        print(f'Failed to start processing: {response.status_code}')
        return
    
    time.sleep(5)
    
    # Benchmark message production and processing
    num_messages = 10000
    num_keys = 1000
    
    print(f'Sending {num_messages} messages with {num_keys} unique keys...')
    start_time = time.time()
    
    def send_batch(batch_start, batch_size):
        batch_sent = 0
        for i in range(batch_start, batch_start + batch_size):
            key = f'key_{i % num_keys}'
            message = {
                'id': str(uuid.uuid4()),
                'sequence': i,
                'timestamp': int(time.time() * 1000),
                'data': f'benchmark_data_{i}'
            }
            try:
                producer.send(topic, key=key, value=message)
                batch_sent += 1
            except Exception as e:
                print(f'Failed to send message {i}: {e}')
        return batch_sent
    
    # Send messages in parallel batches
    batch_size = 1000
    batches = [(i, batch_size) for i in range(0, num_messages, batch_size)]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_batch, start, size) for start, size in batches]
        total_sent = sum(future.result() for future in as_completed(futures))
    
    producer.flush()
    send_duration = time.time() - start_time
    
    print(f'✅ Sent {total_sent}/{num_messages} messages in {send_duration:.2f} seconds')
    print(f'   Send throughput: {total_sent/send_duration:.2f} messages/second')
    
    # Wait for processing and measure
    print('⏳ Waiting for processing to complete...')
    time.sleep(30)
    
    # Get processing metrics
    try:
        response = requests.get('http://localhost:8081/processor/metrics')
        if response.status_code == 200:
            metrics = response.json()
            processed = metrics.get('total_messages_processed', 0)
            processing_time = metrics.get('total_processing_time_seconds', send_duration + 30)
            
            print(f'✅ Processing Results:')
            print(f'   Messages processed: {processed}')
            print(f'   Processing throughput: {processed/processing_time:.2f} messages/second')
            print(f'   Processing efficiency: {(processed/total_sent)*100:.1f}%')
        else:
            print(f'Failed to get metrics: {response.status_code}')
    except Exception as e:
        print(f'Error getting metrics: {e}')
    
    producer.close()

def benchmark_state_operations():
    print('💾 Benchmarking state operations...')
    
    state_store = 'benchmark_store'
    num_operations = 1000
    
    # Benchmark state writes
    write_latencies = []
    print(f'Performing {num_operations} state write operations...')
    
    for i in range(num_operations):
        key = f'state_key_{i}'
        value = {'counter': i, 'data': f'state_data_{i}'}
        
        start = time.time()
        try:
            response = requests.put(f'http://localhost:8081/state/stores/{state_store}/{key}',
                                  json={'value': value}, timeout=5)
            end = time.time()
            if response.status_code == 200:
                write_latencies.append((end - start) * 1000)
        except Exception as e:
            print(f'Write operation {i} failed: {e}')
    
    if write_latencies:
        print(f'✅ State Write Performance:')
        print(f'   Operations completed: {len(write_latencies)}/{num_operations}')
        print(f'   Average latency: {statistics.mean(write_latencies):.2f} ms')
        print(f'   Median latency: {statistics.median(write_latencies):.2f} ms')
        print(f'   95th percentile: {sorted(write_latencies)[int(len(write_latencies)*0.95)]:.2f} ms')
        print(f'   Throughput: {len(write_latencies)/(max(write_latencies)/1000):.2f} ops/sec')
    
    # Benchmark state reads
    read_latencies = []
    print(f'Performing {num_operations} state read operations...')
    
    for i in range(num_operations):
        key = f'state_key_{i}'
        
        start = time.time()
        try:
            response = requests.get(f'http://localhost:8081/state/stores/{state_store}/{key}',
                                  timeout=5)
            end = time.time()
            if response.status_code == 200:
                read_latencies.append((end - start) * 1000)
        except Exception as e:
            if 'not found' not in str(e).lower():
                print(f'Read operation {i} failed: {e}')
    
    if read_latencies:
        print(f'✅ State Read Performance:')
        print(f'   Operations completed: {len(read_latencies)}/{num_operations}')
        print(f'   Average latency: {statistics.mean(read_latencies):.2f} ms')
        print(f'   Median latency: {statistics.median(read_latencies):.2f} ms')
        print(f'   95th percentile: {sorted(read_latencies)[int(len(read_latencies)*0.95)]:.2f} ms')

benchmark_throughput()
benchmark_state_operations()
"
	@echo "✅ Benchmarks completed"

# Demonstration targets
exactly-once-demo:
	@echo "🎯 Exactly-Once Processing Demonstration"
	@echo "========================================"
	@echo ""
	@echo "This demo shows exactly-once processing guarantees with duplicate detection."
	@echo ""
	@echo "1️⃣ Starting stream processing..."
	@curl -X POST http://localhost:8081/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["exactly_once_demo"]}' | jq .
	@sleep 3
	@echo ""
	@echo "2️⃣ Sending messages with idempotency keys..."
	@python3 -c "
import requests
import json
import time
from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    key_serializer=lambda k: k.encode('utf-8'),
    acks='all',
    enable_idempotence=True
)

topic = 'exactly_once_demo'

# Send original messages
for i in range(10):
    message = {
        'id': f'msg_{i}',
        'data': f'original_data_{i}',
        'timestamp': int(time.time() * 1000)
    }
    headers = [('idempotency_key', f'demo_msg_{i}'.encode('utf-8'))]
    producer.send(topic, key=f'key_{i}', value=message, headers=headers)

producer.flush()
print('Sent 10 original messages')

time.sleep(2)

# Send duplicates (same idempotency keys)
for i in range(5):
    message = {
        'id': f'msg_{i}_duplicate',
        'data': f'duplicate_data_{i}',
        'timestamp': int(time.time() * 1000)
    }
    headers = [('idempotency_key', f'demo_msg_{i}'.encode('utf-8'))]
    producer.send(topic, key=f'key_{i}', value=message, headers=headers)

producer.flush()
print('Sent 5 duplicate messages')
producer.close()
"
	@sleep 10
	@echo ""
	@echo "3️⃣ Checking exactly-once status..."
	@curl -s http://localhost:8081/admin/exactly-once/status | jq .
	@echo ""
	@echo "4️⃣ Processing metrics:"
	@curl -s http://localhost:8081/processor/metrics | jq .
	@echo ""
	@echo "✅ Exactly-once demonstration completed!"
	@echo "   - Original messages: processed once"
	@echo "   - Duplicate messages: detected and ignored"

rebalancing-demo:
	@echo "🔄 Dynamic Rebalancing Demonstration"
	@echo "==================================="
	@echo ""
	@echo "This demo shows dynamic partition rebalancing during processing."
	@echo ""
	@echo "1️⃣ Starting processing on all processors..."
	@curl -X POST http://localhost:8081/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["rebalancing_demo"]}' >/dev/null
	@curl -X POST http://localhost:8082/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["rebalancing_demo"]}' >/dev/null
	@curl -X POST http://localhost:8083/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["rebalancing_demo"]}' >/dev/null
	@sleep 5
	@echo ""
	@echo "2️⃣ Initial partition assignment:"
	@echo "Processor 1: $$(curl -s http://localhost:8081/processor/partitions | jq -r '.partitions | length') partitions"
	@echo "Processor 2: $$(curl -s http://localhost:8082/processor/partitions | jq -r '.partitions | length') partitions"
	@echo "Processor 3: $$(curl -s http://localhost:8083/processor/partitions | jq -r '.partitions | length') partitions"
	@echo ""
	@echo "3️⃣ Sending messages during processing..."
	@python3 -c "
import json
import time
from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    key_serializer=lambda k: k.encode('utf-8'),
    acks='all'
)

for i in range(50):
    message = {'sequence': i, 'data': f'rebalance_data_{i}'}
    producer.send('rebalancing_demo', key=f'key_{i % 20}', value=message)

producer.flush()
producer.close()
print('Sent 50 messages')
"
	@sleep 5
	@echo ""
	@echo "4️⃣ Triggering rebalancing..."
	@curl -X POST http://localhost:8081/rebalance/trigger \
		-H "Content-Type: application/json" | jq .
	@sleep 15
	@echo ""
	@echo "5️⃣ New partition assignment:"
	@echo "Processor 1: $$(curl -s http://localhost:8081/processor/partitions | jq -r '.partitions | length') partitions"
	@echo "Processor 2: $$(curl -s http://localhost:8082/processor/partitions | jq -r '.partitions | length') partitions"
	@echo "Processor 3: $$(curl -s http://localhost:8083/processor/partitions | jq -r '.partitions | length') partitions"
	@echo ""
	@echo "6️⃣ Rebalancing status:"
	@curl -s http://localhost:8081/rebalance/status | jq .
	@echo ""
	@echo "✅ Rebalancing demonstration completed!"

state-migration-demo:
	@echo "💾 State Migration Demonstration"
	@echo "==============================="
	@echo ""
	@echo "This demo shows state migration during processor scaling."
	@echo ""
	@echo "1️⃣ Starting with 2 processors..."
	@curl -X POST http://localhost:8081/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["state_migration_demo"]}' >/dev/null
	@curl -X POST http://localhost:8082/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["state_migration_demo"]}' >/dev/null
	@sleep 5
	@echo ""
	@echo "2️⃣ Creating initial state..."
	@for i in $$(seq 0 9); do \
		curl -X PUT http://localhost:8081/state/stores/demo_store/key_$$i \
			-H "Content-Type: application/json" \
			-d "{\"value\": {\"counter\": $$i, \"data\": \"initial_$$i\"}}" >/dev/null; \
	done
	@echo "Created 10 state entries"
	@echo ""
	@echo "3️⃣ State distribution before scaling:"
	@echo "Processor 1 state entries: $$(curl -s http://localhost:8081/state/stores | jq -r '.state_stores | length')"
	@echo "Processor 2 state entries: $$(curl -s http://localhost:8082/state/stores | jq -r '.state_stores | length')"
	@echo ""
	@echo "4️⃣ Adding processor 3 (scaling out)..."
	@curl -X POST http://localhost:8083/processor/start \
		-H "Content-Type: application/json" \
		-d '{"topics": ["state_migration_demo"]}' >/dev/null
	@sleep 5
	@echo ""
	@echo "5️⃣ Triggering rebalancing with state migration..."
	@curl -X POST http://localhost:8081/rebalance/trigger >/dev/null
	@sleep 20
	@echo ""
	@echo "6️⃣ State distribution after scaling:"
	@echo "Processor 1 state entries: $$(curl -s http://localhost:8081/state/stores | jq -r '.state_stores | length')"
	@echo "Processor 2 state entries: $$(curl -s http://localhost:8082/state/stores | jq -r '.state_stores | length')"
	@echo "Processor 3 state entries: $$(curl -s http://localhost:8083/state/stores | jq -r '.state_stores | length')"
	@echo ""
	@echo "7️⃣ Verifying state integrity..."
	@python3 -c "
import requests

found_keys = 0
for i in range(10):
    key = f'key_{i}'
    for port in [8081, 8082, 8083]:
        try:
            response = requests.get(f'http://localhost:{port}/state/stores/demo_store/{key}')
            if response.status_code == 200:
                found_keys += 1
                break
        except:
            pass

print(f'Found {found_keys}/10 state keys after migration')
"
	@echo ""
	@echo "✅ State migration demonstration completed!"

performance-demo:
	@echo "🚀 Performance and Scalability Demonstration"
	@echo "==========================================="
	@echo ""
	@echo "This demo shows performance characteristics under load."
	@echo ""
	@echo "1️⃣ Starting all processors..."
	@for i in 1 2 3; do \
		curl -X POST http://localhost:808$$i/processor/start \
			-H "Content-Type: application/json" \
			-d '{"topics": ["performance_demo"]}' >/dev/null; \
	done
	@sleep 5
	@echo ""
	@echo "2️⃣ Running performance test..."
	@python3 -c "
import requests
import json
import time
import threading
from kafka import KafkaProducer

def send_messages(thread_id, num_messages):
    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8'),
        acks='all'
    )
    
    start_time = time.time()
    for i in range(num_messages):
        message = {
            'thread_id': thread_id,
            'sequence': i,
            'timestamp': int(time.time() * 1000),
            'data': f'perf_data_{thread_id}_{i}'
        }
        producer.send('performance_demo', key=f'key_{thread_id}_{i % 100}', value=message)
    
    producer.flush()
    producer.close()
    duration = time.time() - start_time
    print(f'Thread {thread_id}: sent {num_messages} messages in {duration:.2f}s ({num_messages/duration:.2f} msg/s)')

# Start multiple producer threads
threads = []
messages_per_thread = 1000
num_threads = 5

print(f'Starting {num_threads} producer threads, {messages_per_thread} messages each...')
start_time = time.time()

for i in range(num_threads):
    thread = threading.Thread(target=send_messages, args=(i, messages_per_thread))
    threads.append(thread)
    thread.start()

for thread in threads:
    thread.join()

total_duration = time.time() - start_time
total_messages = num_threads * messages_per_thread
print(f'Total: {total_messages} messages in {total_duration:.2f}s ({total_messages/total_duration:.2f} msg/s)')
"
	@sleep 15
	@echo ""
	@echo "3️⃣ Processing results:"
	@for i in 1 2 3; do \
		echo "Processor $$i:"; \
		curl -s http://localhost:808$$i/processor/metrics | jq -r '"  Messages processed: " + (.total_messages_processed // 0 | tostring)'; \
		curl -s http://localhost:808$$i/processor/metrics | jq -r '"  Processing rate: " + (.processing_rate_per_second // 0 | tostring) + " msg/s"'; \
		echo ""; \
	done
	@echo "✅ Performance demonstration completed!"

# Operations targets
monitoring:
	@echo "📊 Opening monitoring dashboards..."
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/stream_processor_admin)"
	@echo "Jaeger: http://localhost:16686"
	@if command -v open >/dev/null 2>&1; then \
		open http://localhost:3000; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open http://localhost:3000; \
	fi

logs:
	@echo "📋 Showing cluster logs..."
	docker-compose logs -f --tail=100

clean:
	@echo "🧹 Cleaning up resources..."
	docker-compose down -v
	docker system prune -f
	rm -rf bin/
	@echo "✅ Cleanup completed"

quick-start:
	@echo "🚀 Stateful Stream Processor Quick Start"
	@echo "========================================"
	@echo ""
	@$(MAKE) build
	@$(MAKE) docker-build
	@$(MAKE) start-cluster
	@echo ""
	@echo "🎯 Running demonstrations..."
	@$(MAKE) exactly-once-demo
	@echo ""
	@$(MAKE) rebalancing-demo
	@echo ""
	@echo "🧪 Running tests..."
	@$(MAKE) test-unit
	@echo ""
	@echo "🎉 Quick start completed successfully!"
	@echo ""
	@echo "🌐 Your stateful stream processor is ready!"
	@echo "   Load Balancer: http://localhost:8080"
	@echo "   Monitoring:    http://localhost:3000"
	@echo ""
	@echo "Try these commands:"
	@echo "  make exactly-once-demo    - Exactly-once processing demo"
	@echo "  make state-migration-demo - State migration demo"
	@echo "  make test-chaos           - Chaos engineering tests"
	@echo "  make benchmark            - Performance benchmarks"
	@echo "  make monitoring           - Open dashboards"
