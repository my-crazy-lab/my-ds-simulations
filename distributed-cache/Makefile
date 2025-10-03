# Distributed Cache with Consistent Hashing Makefile
# Production-grade distributed cache with hot-key mitigation and advanced caching strategies

.PHONY: help build docker-build start-cluster stop-cluster restart-cluster health-check
.PHONY: test-unit test-chaos test-comprehensive benchmark
.PHONY: hot-key-demo consistent-hash-demo replication-demo performance-demo
.PHONY: monitoring logs clean quick-start

# Default target
help:
	@echo "Distributed Cache - Available targets:"
	@echo ""
	@echo "🏗️  Build & Setup:"
	@echo "  build              - Build all services"
	@echo "  docker-build       - Build Docker images"
	@echo "  start-cluster      - Start distributed cache cluster"
	@echo "  stop-cluster       - Stop the cluster"
	@echo "  restart-cluster    - Restart the cluster"
	@echo "  health-check       - Check cluster health"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test-unit          - Run unit tests for consistent hashing"
	@echo "  test-chaos         - Run chaos engineering tests"
	@echo "  test-comprehensive - Run all tests"
	@echo "  benchmark          - Run performance benchmarks"
	@echo ""
	@echo "🎯 Demonstrations:"
	@echo "  hot-key-demo       - Hot-key detection and mitigation"
	@echo "  consistent-hash-demo - Consistent hashing behavior"
	@echo "  replication-demo   - Data replication and consistency"
	@echo "  performance-demo   - Performance under load"
	@echo ""
	@echo "📊 Operations:"
	@echo "  monitoring         - Open monitoring dashboards"
	@echo "  logs               - Show cluster logs"
	@echo "  clean              - Clean up resources"
	@echo "  quick-start        - Complete setup and demo"

# Build targets
build:
	@echo "🏗️ Building distributed cache services..."
	cd services/cache-node && go mod tidy && go build -o ../../bin/cache-node .
	cd services/hot-key-detector && go mod tidy && go build -o ../../bin/hot-key-detector .
	cd services/circuit-breaker-manager && go mod tidy && go build -o ../../bin/circuit-breaker-manager .
	cd services/replication-coordinator && go mod tidy && go build -o ../../bin/replication-coordinator .
	@echo "✅ Build completed"

docker-build:
	@echo "🐳 Building Docker images..."
	docker-compose build --parallel
	@echo "✅ Docker images built"

# Cluster management
start-cluster:
	@echo "🚀 Starting distributed cache cluster..."
	@echo "   - 3 cache nodes (ports 8081-8083)"
	@echo "   - Hot-key detector (port 8090)"
	@echo "   - Circuit breaker manager (port 8091)"
	@echo "   - Replication coordinator (port 8092)"
	@echo "   - Load balancer (port 8080)"
	@echo "   - Redis coordination (port 6379)"
	@echo "   - Monitoring stack (Prometheus: 9090, Grafana: 3000)"
	docker-compose up -d
	@echo "⏳ Waiting for cluster to be ready..."
	sleep 30
	@$(MAKE) health-check
	@echo "✅ Distributed cache cluster is ready!"
	@echo ""
	@echo "🌐 Access points:"
	@echo "  Load Balancer:      http://localhost:8080"
	@echo "  Cache Nodes:        http://localhost:8081-8083"
	@echo "  Hot-Key Detector:   http://localhost:8090"
	@echo "  Circuit Breaker:    http://localhost:8091"
	@echo "  Replication Coord:  http://localhost:8092"
	@echo "  Prometheus:         http://localhost:9090"
	@echo "  Grafana:            http://localhost:3000 (admin/cache_admin_2024)"
	@echo "  Jaeger:             http://localhost:16686"

stop-cluster:
	@echo "🛑 Stopping distributed cache cluster..."
	docker-compose down
	@echo "✅ Cluster stopped"

restart-cluster:
	@echo "🔄 Restarting distributed cache cluster..."
	docker-compose restart
	sleep 20
	@$(MAKE) health-check
	@echo "✅ Cluster restarted"

health-check:
	@echo "🏥 Checking cluster health..."
	@echo "Cache Nodes:"
	@curl -s http://localhost:8081/health | jq -r '.status // "unhealthy"' | sed 's/^/  cache-node-1: /' || echo "  cache-node-1: unreachable"
	@curl -s http://localhost:8082/health | jq -r '.status // "unhealthy"' | sed 's/^/  cache-node-2: /' || echo "  cache-node-2: unreachable"
	@curl -s http://localhost:8083/health | jq -r '.status // "unhealthy"' | sed 's/^/  cache-node-3: /' || echo "  cache-node-3: unreachable"
	@echo "Support Services:"
	@curl -s http://localhost:8090/health | jq -r '.status // "unhealthy"' | sed 's/^/  hot-key-detector: /' || echo "  hot-key-detector: unreachable"
	@curl -s http://localhost:8091/health | jq -r '.status // "unhealthy"' | sed 's/^/  circuit-breaker: /' || echo "  circuit-breaker: unreachable"
	@curl -s http://localhost:8092/health | jq -r '.status // "unhealthy"' | sed 's/^/  replication-coord: /' || echo "  replication-coord: unreachable"

# Testing targets
test-unit:
	@echo "🧪 Running consistent hashing unit tests..."
	python3 -m pytest tests/unit/test_consistent_hashing.py -v --tb=short
	@echo "✅ Unit tests completed"

test-chaos:
	@echo "🌪️ Running hot-key chaos engineering tests..."
	python3 -m pytest tests/chaos/test_hot_key_scenarios.py -v --tb=short -s
	@echo "✅ Chaos tests completed"

test-comprehensive:
	@echo "🔬 Running comprehensive test suite..."
	@$(MAKE) test-unit
	@$(MAKE) test-chaos
	@echo "✅ All tests completed successfully!"

benchmark:
	@echo "📊 Running cache performance benchmarks..."
	@python3 -c "
import requests
import time
import json
import uuid
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

def benchmark_cache_operations():
    print('🚀 Benchmarking cache operations...')
    
    base_url = 'http://localhost:8080'
    
    # Benchmark SET operations
    print('Testing SET operations...')
    set_latencies = []
    
    for i in range(1000):
        key = f'benchmark_key_{i}'
        value = {'data': f'benchmark_value_{i}', 'timestamp': time.time()}
        
        start = time.time()
        try:
            response = requests.put(f'{base_url}/cache/{key}',
                                  json={'value': value, 'ttl': 3600}, timeout=5)
            end = time.time()
            if response.status_code == 200:
                set_latencies.append((end - start) * 1000)
        except Exception as e:
            print(f'SET operation {i} failed: {e}')
    
    if set_latencies:
        print(f'✅ SET Performance:')
        print(f'   Operations completed: {len(set_latencies)}/1000')
        print(f'   Average latency: {statistics.mean(set_latencies):.2f} ms')
        print(f'   Median latency: {statistics.median(set_latencies):.2f} ms')
        print(f'   95th percentile: {sorted(set_latencies)[int(len(set_latencies)*0.95)]:.2f} ms')
        print(f'   Throughput: {len(set_latencies)/(max(set_latencies)/1000):.2f} ops/sec')
    
    # Benchmark GET operations
    print('Testing GET operations...')
    get_latencies = []
    
    for i in range(1000):
        key = f'benchmark_key_{i}'
        
        start = time.time()
        try:
            response = requests.get(f'{base_url}/cache/{key}', timeout=5)
            end = time.time()
            if response.status_code == 200:
                get_latencies.append((end - start) * 1000)
        except Exception as e:
            if 'not found' not in str(e).lower():
                print(f'GET operation {i} failed: {e}')
    
    if get_latencies:
        print(f'✅ GET Performance:')
        print(f'   Operations completed: {len(get_latencies)}/1000')
        print(f'   Average latency: {statistics.mean(get_latencies):.2f} ms')
        print(f'   Median latency: {statistics.median(get_latencies):.2f} ms')
        print(f'   95th percentile: {sorted(get_latencies)[int(len(get_latencies)*0.95)]:.2f} ms')

def benchmark_concurrent_operations():
    print('💥 Benchmarking concurrent operations...')
    
    base_url = 'http://localhost:8080'
    
    def concurrent_operation(thread_id, num_ops):
        latencies = []
        for i in range(num_ops):
            key = f'concurrent_key_{thread_id}_{i}'
            value = {'thread': thread_id, 'sequence': i}
            
            start = time.time()
            try:
                # Mix of SET and GET operations
                if i % 2 == 0:
                    response = requests.put(f'{base_url}/cache/{key}',
                                          json={'value': value, 'ttl': 300}, timeout=5)
                else:
                    response = requests.get(f'{base_url}/cache/{key}', timeout=5)
                
                end = time.time()
                if response.status_code in [200, 404]:  # 404 is OK for GET
                    latencies.append((end - start) * 1000)
            except Exception as e:
                pass
        
        return latencies
    
    # Run concurrent operations
    num_threads = 10
    ops_per_thread = 100
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(concurrent_operation, i, ops_per_thread) 
                  for i in range(num_threads)]
        
        all_latencies = []
        for future in as_completed(futures):
            all_latencies.extend(future.result())
    
    if all_latencies:
        print(f'✅ Concurrent Performance:')
        print(f'   Total operations: {len(all_latencies)}')
        print(f'   Average latency: {statistics.mean(all_latencies):.2f} ms')
        print(f'   95th percentile: {sorted(all_latencies)[int(len(all_latencies)*0.95)]:.2f} ms')
        print(f'   Throughput: {len(all_latencies)/(max(all_latencies)/1000):.2f} ops/sec')

def benchmark_hot_key_performance():
    print('🔥 Benchmarking hot key performance...')
    
    base_url = 'http://localhost:8080'
    hot_key = 'benchmark_hot_key'
    
    # Set up hot key
    requests.put(f'{base_url}/cache/{hot_key}',
                json={'value': {'data': 'hot_key_data'}, 'ttl': 3600})
    
    # Generate hot key load
    def hot_key_load(duration_seconds):
        start_time = time.time()
        request_count = 0
        latencies = []
        
        while time.time() - start_time < duration_seconds:
            start = time.time()
            try:
                response = requests.get(f'{base_url}/cache/{hot_key}', timeout=5)
                end = time.time()
                if response.status_code == 200:
                    latencies.append((end - start) * 1000)
                    request_count += 1
            except:
                pass
            
            time.sleep(0.001)  # 1ms between requests
        
        return request_count, latencies
    
    # Run hot key test
    request_count, latencies = hot_key_load(10)
    
    if latencies:
        print(f'✅ Hot Key Performance:')
        print(f'   Requests completed: {request_count}')
        print(f'   Average latency: {statistics.mean(latencies):.2f} ms')
        print(f'   95th percentile: {sorted(latencies)[int(len(latencies)*0.95)]:.2f} ms')
        print(f'   Effective RPS: {request_count/10:.2f}')

benchmark_cache_operations()
benchmark_concurrent_operations()
benchmark_hot_key_performance()
"
	@echo "✅ Benchmarks completed"

# Demonstration targets
hot-key-demo:
	@echo "🔥 Hot-Key Detection and Mitigation Demonstration"
	@echo "================================================"
	@echo ""
	@echo "This demo shows real-time hot-key detection and automatic mitigation."
	@echo ""
	@echo "1️⃣ Configuring hot-key detection..."
	@curl -X POST http://localhost:8081/admin/hot-key-config \
		-H "Content-Type: application/json" \
		-d '{"threshold_requests_per_second": 100, "detection_window_seconds": 30, "mitigation_strategy": "replicate_and_coalesce"}' | jq .
	@echo ""
	@echo "2️⃣ Creating test keys..."
	@for i in $$(seq 1 5); do \
		curl -X PUT http://localhost:8080/cache/hot_key_$$i \
			-H "Content-Type: application/json" \
			-d "{\"value\": {\"data\": \"hot_data_$$i\", \"created\": \"$$(date)\"}, \"ttl\": 3600}" >/dev/null; \
	done
	@echo "Created 5 test keys"
	@echo ""
	@echo "3️⃣ Generating hot-key load..."
	@python3 -c "
import requests
import threading
import time
import random

def generate_hot_key_load():
    base_url = 'http://localhost:8080'
    hot_keys = ['hot_key_1', 'hot_key_2']
    
    def hit_hot_key(key, duration):
        start_time = time.time()
        count = 0
        while time.time() - start_time < duration:
            try:
                requests.get(f'{base_url}/cache/{key}', timeout=1)
                count += 1
                time.sleep(0.01)  # 100 RPS per key
            except:
                pass
        print(f'Generated {count} requests for {key}')
    
    # Start hot key load
    threads = []
    for key in hot_keys:
        thread = threading.Thread(target=hit_hot_key, args=(key, 20))
        threads.append(thread)
        thread.start()
    
    # Generate normal load
    def normal_load():
        for i in range(100):
            try:
                key = f'normal_key_{random.randint(1, 50)}'
                requests.get(f'{base_url}/cache/{key}', timeout=1)
                time.sleep(0.1)
            except:
                pass
    
    normal_thread = threading.Thread(target=normal_load)
    normal_thread.start()
    
    # Wait for completion
    for thread in threads:
        thread.join()
    normal_thread.join()

generate_hot_key_load()
"
	@sleep 5
	@echo ""
	@echo "4️⃣ Checking hot-key detection results..."
	@curl -s http://localhost:8081/admin/hot-keys | jq .
	@echo ""
	@echo "5️⃣ Circuit breaker status:"
	@curl -s http://localhost:8081/admin/circuit-breakers | jq .
	@echo ""
	@echo "✅ Hot-key demonstration completed!"

consistent-hash-demo:
	@echo "🔄 Consistent Hashing Demonstration"
	@echo "=================================="
	@echo ""
	@echo "This demo shows consistent hashing behavior and key distribution."
	@echo ""
	@echo "1️⃣ Initial cluster state:"
	@curl -s http://localhost:8081/cluster/nodes | jq .
	@echo ""
	@echo "2️⃣ Hash ring information:"
	@curl -s http://localhost:8081/admin/hash-ring | jq .
	@echo ""
	@echo "3️⃣ Storing keys across the cluster..."
	@python3 -c "
import requests
import hashlib

base_url = 'http://localhost:8080'
keys = [f'hash_demo_key_{i}' for i in range(20)]

print('Storing keys and checking distribution...')
key_locations = {}

for key in keys:
    # Store the key
    value = {'key': key, 'hash': hashlib.md5(key.encode()).hexdigest()[:8]}
    response = requests.put(f'{base_url}/cache/{key}',
                          json={'value': value, 'ttl': 3600})
    
    if response.status_code == 200:
        # Check which nodes have the key
        for port in [8081, 8082, 8083]:
            try:
                check_response = requests.get(f'http://localhost:{port}/cache/{key}')
                if check_response.status_code == 200:
                    node = f'node-{port-8080}'
                    if node not in key_locations:
                        key_locations[node] = []
                    key_locations[node].append(key)
                    break
            except:
                pass

print('Key distribution:')
for node, keys in key_locations.items():
    print(f'  {node}: {len(keys)} keys')
    for key in keys[:3]:  # Show first 3 keys
        print(f'    - {key}')
    if len(keys) > 3:
        print(f'    ... and {len(keys)-3} more')
"
	@echo ""
	@echo "4️⃣ Cluster statistics:"
	@curl -s http://localhost:8081/admin/stats | jq .
	@echo ""
	@echo "✅ Consistent hashing demonstration completed!"

replication-demo:
	@echo "🔄 Data Replication and Consistency Demonstration"
	@echo "==============================================="
	@echo ""
	@echo "This demo shows data replication and consistency behavior."
	@echo ""
	@echo "1️⃣ Setting up replicated data..."
	@for i in $$(seq 1 10); do \
		curl -X PUT http://localhost:8080/cache/replicated_key_$$i \
			-H "Content-Type: application/json" \
			-d "{\"value\": {\"data\": \"replicated_data_$$i\", \"timestamp\": \"$$(date)\"}, \"ttl\": 3600}" >/dev/null; \
	done
	@echo "Created 10 replicated keys"
	@echo ""
	@echo "2️⃣ Checking replication status:"
	@curl -s http://localhost:8081/admin/replication | jq .
	@echo ""
	@echo "3️⃣ Verifying data consistency across nodes..."
	@python3 -c "
import requests

keys = [f'replicated_key_{i}' for i in range(1, 6)]  # Check first 5 keys
nodes = [8081, 8082, 8083]

print('Consistency check:')
for key in keys:
    values = {}
    for port in nodes:
        try:
            response = requests.get(f'http://localhost:{port}/cache/{key}')
            if response.status_code == 200:
                data = response.json()
                values[f'node-{port-8080}'] = data.get('value', {}).get('data', 'N/A')
        except:
            values[f'node-{port-8080}'] = 'ERROR'
    
    print(f'  {key}:')
    consistent = len(set(v for v in values.values() if v != 'ERROR')) <= 1
    for node, value in values.items():
        status = '✅' if value != 'ERROR' else '❌'
        print(f'    {node}: {status} {value}')
    
    consistency_status = '✅ CONSISTENT' if consistent else '❌ INCONSISTENT'
    print(f'    Status: {consistency_status}')
    print()
"
	@echo ""
	@echo "4️⃣ Replication coordinator status:"
	@curl -s http://localhost:8092/health | jq .
	@echo ""
	@echo "✅ Replication demonstration completed!"

performance-demo:
	@echo "🚀 Performance and Load Testing Demonstration"
	@echo "============================================"
	@echo ""
	@echo "This demo shows cache performance under various load conditions."
	@echo ""
	@echo "1️⃣ Baseline performance test..."
	@python3 -c "
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor

base_url = 'http://localhost:8080'

def performance_test(test_name, num_operations, concurrent_threads=1):
    print(f'Running {test_name}...')
    
    def worker(thread_id, ops_per_thread):
        success_count = 0
        error_count = 0
        
        for i in range(ops_per_thread):
            key = f'perf_test_{thread_id}_{i}'
            value = {'thread': thread_id, 'op': i, 'timestamp': time.time()}
            
            try:
                # SET operation
                response = requests.put(f'{base_url}/cache/{key}',
                                      json={'value': value, 'ttl': 300}, timeout=2)
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
                
                # GET operation
                response = requests.get(f'{base_url}/cache/{key}', timeout=2)
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 2
        
        return success_count, error_count
    
    start_time = time.time()
    
    ops_per_thread = num_operations // concurrent_threads
    with ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
        futures = [executor.submit(worker, i, ops_per_thread) 
                  for i in range(concurrent_threads)]
        
        total_success = 0
        total_errors = 0
        
        for future in futures:
            success, errors = future.result()
            total_success += success
            total_errors += errors
    
    duration = time.time() - start_time
    total_ops = total_success + total_errors
    
    print(f'  Duration: {duration:.2f} seconds')
    print(f'  Total operations: {total_ops}')
    print(f'  Successful: {total_success}')
    print(f'  Errors: {total_errors}')
    print(f'  Success rate: {(total_success/total_ops)*100:.1f}%')
    print(f'  Throughput: {total_ops/duration:.2f} ops/sec')
    print()

# Run performance tests
performance_test('Sequential Operations', 500, 1)
performance_test('Concurrent Operations (5 threads)', 500, 5)
performance_test('High Concurrency (10 threads)', 1000, 10)
"
	@echo ""
	@echo "2️⃣ Cache statistics after load test:"
	@for i in 1 2 3; do \
		echo "Node $$i:"; \
		curl -s http://localhost:808$$i/admin/stats | jq -r '"  Hit ratio: " + (.hit_ratio // 0 | tostring)'; \
		curl -s http://localhost:808$$i/admin/stats | jq -r '"  Memory used: " + (.memory_used_mb // 0 | tostring) + " MB"'; \
		echo ""; \
	done
	@echo "✅ Performance demonstration completed!"

# Operations targets
monitoring:
	@echo "📊 Opening monitoring dashboards..."
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/cache_admin_2024)"
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
	@echo "🚀 Distributed Cache Quick Start"
	@echo "==============================="
	@echo ""
	@$(MAKE) build
	@$(MAKE) docker-build
	@$(MAKE) start-cluster
	@echo ""
	@echo "🎯 Running demonstrations..."
	@$(MAKE) hot-key-demo
	@echo ""
	@$(MAKE) consistent-hash-demo
	@echo ""
	@echo "🧪 Running tests..."
	@$(MAKE) test-unit
	@echo ""
	@echo "🎉 Quick start completed successfully!"
	@echo ""
	@echo "🌐 Your distributed cache is ready!"
	@echo "   Load Balancer: http://localhost:8080"
	@echo "   Monitoring:    http://localhost:3000"
	@echo ""
	@echo "Try these commands:"
	@echo "  make hot-key-demo         - Hot-key detection demo"
	@echo "  make replication-demo     - Data replication demo"
	@echo "  make test-chaos           - Chaos engineering tests"
	@echo "  make benchmark            - Performance benchmarks"
	@echo "  make monitoring           - Open dashboards"
