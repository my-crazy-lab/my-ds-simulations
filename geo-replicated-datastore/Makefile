# Geo-replicated Datastore Makefile
# Production-grade CRDT-based distributed datastore with conflict resolution

.PHONY: help build docker-build start-cluster stop-cluster restart-cluster health-check
.PHONY: test-unit test-chaos test-comprehensive benchmark
.PHONY: crdt-demo partition-demo convergence-demo conflict-demo
.PHONY: monitoring logs clean quick-start

# Default target
help:
	@echo "Geo-replicated Datastore - Available targets:"
	@echo ""
	@echo "🏗️  Build & Setup:"
	@echo "  build              - Build all services"
	@echo "  docker-build       - Build Docker images"
	@echo "  start-cluster      - Start 9-node geo-replicated cluster"
	@echo "  stop-cluster       - Stop the cluster"
	@echo "  restart-cluster    - Restart the cluster"
	@echo "  health-check       - Check cluster health"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test-unit          - Run unit tests for CRDT operations"
	@echo "  test-chaos         - Run chaos engineering tests"
	@echo "  test-comprehensive - Run all tests"
	@echo "  benchmark          - Run performance benchmarks"
	@echo ""
	@echo "🎯 Demonstrations:"
	@echo "  crdt-demo          - Interactive CRDT operations demo"
	@echo "  partition-demo     - Network partition simulation"
	@echo "  convergence-demo   - Eventual consistency demonstration"
	@echo "  conflict-demo      - Conflict resolution demonstration"
	@echo ""
	@echo "📊 Operations:"
	@echo "  monitoring         - Open monitoring dashboards"
	@echo "  logs               - Show cluster logs"
	@echo "  clean              - Clean up resources"
	@echo "  quick-start        - Complete setup and demo"

# Build targets
build:
	@echo "🏗️ Building geo-replicated datastore services..."
	cd services/geodatastore-node && go mod tidy && go build -o ../../bin/geodatastore-node .
	cd services/anti-entropy-coordinator && go mod tidy && go build -o ../../bin/anti-entropy-coordinator .
	cd services/conflict-resolver && go mod tidy && go build -o ../../bin/conflict-resolver .
	@echo "✅ Build completed"

docker-build:
	@echo "🐳 Building Docker images..."
	docker-compose build --parallel
	@echo "✅ Docker images built"

# Cluster management
start-cluster:
	@echo "🚀 Starting geo-replicated datastore cluster..."
	@echo "   - 3 nodes in US region (ports 8081-8083)"
	@echo "   - 3 nodes in EU region (ports 8084-8086)"
	@echo "   - 3 nodes in APAC region (ports 8087-8089)"
	@echo "   - Load balancer on port 8080"
	@echo "   - Monitoring stack (Prometheus: 9090, Grafana: 3000)"
	docker-compose up -d
	@echo "⏳ Waiting for cluster to be ready..."
	sleep 30
	@$(MAKE) health-check
	@echo "✅ Geo-replicated cluster is ready!"
	@echo ""
	@echo "🌐 Access points:"
	@echo "  Load Balancer:    http://localhost:8080"
	@echo "  US Region:        http://localhost:8081-8083"
	@echo "  EU Region:        http://localhost:8084-8086"
	@echo "  APAC Region:      http://localhost:8087-8089"
	@echo "  Prometheus:       http://localhost:9090"
	@echo "  Grafana:          http://localhost:3000 (admin/geodatastore_admin)"
	@echo "  Jaeger:           http://localhost:16686"

stop-cluster:
	@echo "🛑 Stopping geo-replicated datastore cluster..."
	docker-compose down
	@echo "✅ Cluster stopped"

restart-cluster:
	@echo "🔄 Restarting geo-replicated datastore cluster..."
	docker-compose restart
	sleep 20
	@$(MAKE) health-check
	@echo "✅ Cluster restarted"

health-check:
	@echo "🏥 Checking cluster health..."
	@echo "US Region:"
	@curl -s http://localhost:8081/health | jq -r '.status // "unhealthy"' | sed 's/^/  us-1: /' || echo "  us-1: unreachable"
	@curl -s http://localhost:8082/health | jq -r '.status // "unhealthy"' | sed 's/^/  us-2: /' || echo "  us-2: unreachable"
	@curl -s http://localhost:8083/health | jq -r '.status // "unhealthy"' | sed 's/^/  us-3: /' || echo "  us-3: unreachable"
	@echo "EU Region:"
	@curl -s http://localhost:8084/health | jq -r '.status // "unhealthy"' | sed 's/^/  eu-1: /' || echo "  eu-1: unreachable"
	@curl -s http://localhost:8085/health | jq -r '.status // "unhealthy"' | sed 's/^/  eu-2: /' || echo "  eu-2: unreachable"
	@curl -s http://localhost:8086/health | jq -r '.status // "unhealthy"' | sed 's/^/  eu-3: /' || echo "  eu-3: unreachable"
	@echo "APAC Region:"
	@curl -s http://localhost:8087/health | jq -r '.status // "unhealthy"' | sed 's/^/  apac-1: /' || echo "  apac-1: unreachable"
	@curl -s http://localhost:8088/health | jq -r '.status // "unhealthy"' | sed 's/^/  apac-2: /' || echo "  apac-2: unreachable"
	@curl -s http://localhost:8089/health | jq -r '.status // "unhealthy"' | sed 's/^/  apac-3: /' || echo "  apac-3: unreachable"

# Testing targets
test-unit:
	@echo "🧪 Running CRDT unit tests..."
	python3 -m pytest tests/unit/test_crdt_operations.py -v --tb=short
	@echo "✅ Unit tests completed"

test-chaos:
	@echo "🌪️ Running chaos engineering tests..."
	python3 -m pytest tests/chaos/test_geo_replication.py -v --tb=short -s
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
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

def benchmark_counter_operations():
    print('🔢 Benchmarking counter operations...')
    
    # Create counter
    key = f'benchmark_counter_{int(time.time())}'
    response = requests.post('http://localhost:8080/crdt/counters/' + key, 
                           json={'type': 'pn_counter', 'initial_value': 0})
    
    if response.status_code != 201:
        print(f'Failed to create counter: {response.status_code}')
        return
    
    # Benchmark increments
    latencies = []
    operations = 1000
    
    def increment_operation():
        start = time.time()
        try:
            response = requests.post(f'http://localhost:8080/crdt/counters/{key}/increment',
                                   json={'value': 1}, timeout=5)
            end = time.time()
            if response.status_code == 200:
                return (end - start) * 1000  # Convert to milliseconds
        except:
            pass
        return None
    
    print(f'Performing {operations} increment operations...')
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(increment_operation) for _ in range(operations)]
        for future in as_completed(futures):
            latency = future.result()
            if latency is not None:
                latencies.append(latency)
    
    end_time = time.time()
    duration = end_time - start_time
    
    if latencies:
        print(f'✅ Counter Operations Benchmark Results:')
        print(f'   Total operations: {len(latencies)}/{operations}')
        print(f'   Duration: {duration:.2f} seconds')
        print(f'   Throughput: {len(latencies)/duration:.2f} ops/sec')
        print(f'   Average latency: {statistics.mean(latencies):.2f} ms')
        print(f'   Median latency: {statistics.median(latencies):.2f} ms')
        print(f'   95th percentile: {sorted(latencies)[int(len(latencies)*0.95)]:.2f} ms')
    else:
        print('❌ No successful operations')

def benchmark_cross_region_latency():
    print('🌍 Benchmarking cross-region latency...')
    
    regions = {
        'us': 'http://localhost:8081',
        'eu': 'http://localhost:8084', 
        'apac': 'http://localhost:8087'
    }
    
    key = f'cross_region_test_{int(time.time())}'
    
    # Create counter in US
    response = requests.post(f'{regions[\"us\"]}/crdt/counters/{key}',
                           json={'type': 'pn_counter', 'initial_value': 0})
    
    if response.status_code != 201:
        print(f'Failed to create counter: {response.status_code}')
        return
    
    time.sleep(3)  # Wait for propagation
    
    # Test cross-region read latency
    for region, url in regions.items():
        latencies = []
        for _ in range(10):
            start = time.time()
            try:
                response = requests.get(f'{url}/crdt/counters/{key}', timeout=5)
                end = time.time()
                if response.status_code == 200:
                    latencies.append((end - start) * 1000)
            except:
                pass
        
        if latencies:
            avg_latency = statistics.mean(latencies)
            print(f'   {region.upper()} region: {avg_latency:.2f} ms average read latency')

benchmark_counter_operations()
benchmark_cross_region_latency()
"
	@echo "✅ Benchmarks completed"

# Demonstration targets
crdt-demo:
	@echo "🎯 CRDT Operations Demonstration"
	@echo "================================"
	@echo ""
	@echo "1️⃣ Creating G-Counter (grow-only)..."
	@curl -X POST http://localhost:8080/crdt/counters/demo_g_counter \
		-H "Content-Type: application/json" \
		-d '{"type": "g_counter", "initial_value": 0}' | jq .
	@echo ""
	@echo "2️⃣ Incrementing from different regions..."
	@curl -X POST http://localhost:8081/crdt/counters/demo_g_counter/increment \
		-H "Content-Type: application/json" -d '{"value": 5}' | jq .
	@curl -X POST http://localhost:8084/crdt/counters/demo_g_counter/increment \
		-H "Content-Type: application/json" -d '{"value": 3}' | jq .
	@curl -X POST http://localhost:8087/crdt/counters/demo_g_counter/increment \
		-H "Content-Type: application/json" -d '{"value": 7}' | jq .
	@echo ""
	@echo "3️⃣ Waiting for convergence..."
	@sleep 3
	@echo ""
	@echo "4️⃣ Reading from all regions (should be 15):"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/counters/demo_g_counter | jq -r '.value')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/counters/demo_g_counter | jq -r '.value')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/counters/demo_g_counter | jq -r '.value')"
	@echo ""
	@echo "5️⃣ Creating OR-Set (observed-remove set)..."
	@curl -X POST http://localhost:8080/crdt/sets/demo_or_set \
		-H "Content-Type: application/json" \
		-d '{"type": "or_set"}' | jq .
	@echo ""
	@echo "6️⃣ Adding elements from different regions..."
	@curl -X POST http://localhost:8081/crdt/sets/demo_or_set/add \
		-H "Content-Type: application/json" -d '{"element": "distributed"}' | jq .
	@curl -X POST http://localhost:8084/crdt/sets/demo_or_set/add \
		-H "Content-Type: application/json" -d '{"element": "systems"}' | jq .
	@curl -X POST http://localhost:8087/crdt/sets/demo_or_set/add \
		-H "Content-Type: application/json" -d '{"element": "crdts"}' | jq .
	@echo ""
	@echo "7️⃣ Reading set from different regions:"
	@sleep 2
	@echo "US:   $$(curl -s http://localhost:8081/crdt/sets/demo_or_set | jq -r '.elements | join(\", \")')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/sets/demo_or_set | jq -r '.elements | join(\", \")')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/sets/demo_or_set | jq -r '.elements | join(\", \")')"
	@echo ""
	@echo "✅ CRDT demonstration completed!"

partition-demo:
	@echo "🌪️ Network Partition Demonstration"
	@echo "=================================="
	@echo ""
	@echo "This demo simulates network partitions and shows how CRDTs handle them."
	@echo "⚠️  This will temporarily pause some containers!"
	@echo ""
	@read -p "Press Enter to continue or Ctrl+C to cancel..."
	@echo ""
	@echo "1️⃣ Creating counter for partition test..."
	@curl -X POST http://localhost:8080/crdt/counters/partition_test \
		-H "Content-Type: application/json" \
		-d '{"type": "pn_counter", "initial_value": 0}' | jq .
	@sleep 3
	@echo ""
	@echo "2️⃣ Initial operations from all regions..."
	@curl -X POST http://localhost:8081/crdt/counters/partition_test/increment \
		-H "Content-Type: application/json" -d '{"value": 10}' | jq .
	@curl -X POST http://localhost:8084/crdt/counters/partition_test/increment \
		-H "Content-Type: application/json" -d '{"value": 20}' | jq .
	@curl -X POST http://localhost:8087/crdt/counters/partition_test/increment \
		-H "Content-Type: application/json" -d '{"value": 30}' | jq .
	@sleep 3
	@echo ""
	@echo "3️⃣ Current values (should all be 60):"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/counters/partition_test | jq -r '.value')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/counters/partition_test | jq -r '.value')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/counters/partition_test | jq -r '.value')"
	@echo ""
	@echo "4️⃣ Simulating network partition (pausing EU region)..."
	@docker pause geodatastore-eu-1 geodatastore-eu-2 geodatastore-eu-3
	@sleep 2
	@echo ""
	@echo "5️⃣ Operations during partition (US and APAC only)..."
	@curl -X POST http://localhost:8081/crdt/counters/partition_test/increment \
		-H "Content-Type: application/json" -d '{"value": 5}' | jq .
	@curl -X POST http://localhost:8087/crdt/counters/partition_test/increment \
		-H "Content-Type: application/json" -d '{"value": 7}' | jq .
	@sleep 3
	@echo ""
	@echo "6️⃣ Values during partition:"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/counters/partition_test | jq -r '.value')"
	@echo "EU:   unreachable (partitioned)"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/counters/partition_test | jq -r '.value')"
	@echo ""
	@echo "7️⃣ Healing partition (unpausing EU region)..."
	@docker unpause geodatastore-eu-1 geodatastore-eu-2 geodatastore-eu-3
	@sleep 10
	@echo ""
	@echo "8️⃣ Values after partition healing (should all be 72):"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/counters/partition_test | jq -r '.value')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/counters/partition_test | jq -r '.value')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/counters/partition_test | jq -r '.value')"
	@echo ""
	@echo "✅ Partition demonstration completed!"

convergence-demo:
	@echo "🔄 Eventual Consistency Demonstration"
	@echo "===================================="
	@echo ""
	@echo "This demo shows how CRDTs achieve eventual consistency."
	@echo ""
	@echo "1️⃣ Creating test counter..."
	@curl -X POST http://localhost:8080/crdt/counters/convergence_test \
		-H "Content-Type: application/json" \
		-d '{"type": "pn_counter", "initial_value": 0}' | jq .
	@sleep 2
	@echo ""
	@echo "2️⃣ Rapid concurrent operations from all regions..."
	@for i in $$(seq 1 5); do \
		curl -X POST http://localhost:8081/crdt/counters/convergence_test/increment \
			-H "Content-Type: application/json" -d "{\"value\": $$i}" & \
		curl -X POST http://localhost:8084/crdt/counters/convergence_test/increment \
			-H "Content-Type: application/json" -d "{\"value\": $$((i+10))}" & \
		curl -X POST http://localhost:8087/crdt/counters/convergence_test/increment \
			-H "Content-Type: application/json" -d "{\"value\": $$((i+20))}" & \
	done
	@wait
	@echo ""
	@echo "3️⃣ Immediate values (may be inconsistent):"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/counters/convergence_test | jq -r '.value')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/counters/convergence_test | jq -r '.value')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/counters/convergence_test | jq -r '.value')"
	@echo ""
	@echo "4️⃣ Waiting for convergence..."
	@sleep 5
	@echo ""
	@echo "5️⃣ Final values (should all be 195):"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/counters/convergence_test | jq -r '.value')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/counters/convergence_test | jq -r '.value')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/counters/convergence_test | jq -r '.value')"
	@echo ""
	@echo "✅ Convergence demonstration completed!"

conflict-demo:
	@echo "⚔️ Conflict Resolution Demonstration"
	@echo "==================================="
	@echo ""
	@echo "This demo shows how CRDTs automatically resolve conflicts."
	@echo ""
	@echo "1️⃣ Creating LWW-Register for conflict test..."
	@curl -X POST http://localhost:8080/crdt/registers/conflict_test \
		-H "Content-Type: application/json" \
		-d '{"type": "lww_register", "initial_value": "initial"}' | jq .
	@sleep 2
	@echo ""
	@echo "2️⃣ Concurrent conflicting updates..."
	@curl -X PUT http://localhost:8081/crdt/registers/conflict_test \
		-H "Content-Type: application/json" -d '{"value": "us_update"}' & \
	@curl -X PUT http://localhost:8084/crdt/registers/conflict_test \
		-H "Content-Type: application/json" -d '{"value": "eu_update"}' & \
	@curl -X PUT http://localhost:8087/crdt/registers/conflict_test \
		-H "Content-Type: application/json" -d '{"value": "apac_update"}' &
	@wait
	@echo ""
	@echo "3️⃣ Waiting for conflict resolution..."
	@sleep 5
	@echo ""
	@echo "4️⃣ Resolved values (LWW should pick one):"
	@echo "US:   $$(curl -s http://localhost:8081/crdt/registers/conflict_test | jq -r '.value')"
	@echo "EU:   $$(curl -s http://localhost:8084/crdt/registers/conflict_test | jq -r '.value')"
	@echo "APAC: $$(curl -s http://localhost:8087/crdt/registers/conflict_test | jq -r '.value')"
	@echo ""
	@echo "5️⃣ Checking for detected conflicts..."
	@curl -s http://localhost:8081/admin/conflicts | jq .
	@echo ""
	@echo "✅ Conflict resolution demonstration completed!"

# Operations targets
monitoring:
	@echo "📊 Opening monitoring dashboards..."
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/geodatastore_admin)"
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
	@echo "🚀 Geo-replicated Datastore Quick Start"
	@echo "======================================="
	@echo ""
	@$(MAKE) build
	@$(MAKE) docker-build
	@$(MAKE) start-cluster
	@echo ""
	@echo "🎯 Running demonstrations..."
	@$(MAKE) crdt-demo
	@echo ""
	@$(MAKE) convergence-demo
	@echo ""
	@echo "🧪 Running tests..."
	@$(MAKE) test-unit
	@echo ""
	@echo "🎉 Quick start completed successfully!"
	@echo ""
	@echo "🌐 Your geo-replicated datastore is ready!"
	@echo "   Load Balancer: http://localhost:8080"
	@echo "   Monitoring:    http://localhost:3000"
	@echo ""
	@echo "Try these commands:"
	@echo "  make crdt-demo        - Interactive CRDT demo"
	@echo "  make partition-demo   - Network partition simulation"
	@echo "  make test-chaos       - Chaos engineering tests"
	@echo "  make monitoring       - Open dashboards"
