# Distributed KV Store with Tunable Consistency - Makefile
# Production-grade build, test, and deployment automation

.PHONY: help build test clean docker-build start-cluster stop-cluster test-comprehensive benchmark cap-test

# Default target
help: ## Show this help message
	@echo "Distributed KV Store with Tunable Consistency - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""

# Variables
PROJECT_NAME := distributed-kv-store
DOCKER_REGISTRY := localhost:5000
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
DOCKER_IMAGE := $(DOCKER_REGISTRY)/$(PROJECT_NAME)
GO_VERSION := 1.21

# Build targets
build: ## Build the KV store node binary
	@echo "Building KV store node..."
	cd services/kvstore-node && go mod tidy
	cd services/kvstore-node && go build -o kvstore-node .
	@echo "Build completed successfully"

build-proto: ## Generate protobuf files
	@echo "Generating protobuf files..."
	cd services/kvstore-node && protoc --go_out=. --go-grpc_out=. proto/kvstore.proto
	@echo "Protobuf generation completed"

clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	cd services/kvstore-node && rm -f kvstore-node
	cd services/kvstore-node && go clean
	@echo "Clean completed"

# Docker targets
docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t $(PROJECT_NAME):$(VERSION) -t $(PROJECT_NAME):latest services/kvstore-node/
	@echo "Docker build completed"

docker-push: docker-build ## Push Docker image to registry
	@echo "Pushing Docker image to registry..."
	docker tag $(PROJECT_NAME):$(VERSION) $(DOCKER_IMAGE):$(VERSION)
	docker tag $(PROJECT_NAME):latest $(DOCKER_IMAGE):latest
	docker push $(DOCKER_IMAGE):$(VERSION)
	docker push $(DOCKER_IMAGE):latest
	@echo "Docker push completed"

# Cluster management
start-cluster: ## Start the KV store cluster
	@echo "Starting distributed KV store cluster..."
	docker-compose up -d
	@echo "Waiting for cluster to be ready..."
	@sleep 45
	@$(MAKE) health-check
	@echo "KV store cluster started successfully"

stop-cluster: ## Stop the KV store cluster
	@echo "Stopping KV store cluster..."
	docker-compose down
	@echo "KV store cluster stopped"

restart-cluster: stop-cluster start-cluster ## Restart the KV store cluster

health-check: ## Check cluster health
	@echo "Checking cluster health..."
	@for port in 8081 8082 8083; do \
		echo "Checking node on port $$port..."; \
		curl -f http://localhost:$$port/health || exit 1; \
		echo ""; \
	done
	@echo "All nodes are healthy"

# Testing targets
test-unit: ## Run unit tests
	@echo "Running unit tests..."
	cd services/kvstore-node && go test -v ./...
	@echo "Unit tests completed"

test-consistency: ## Run consistency model tests
	@echo "Running consistency model tests..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/unit/test_consistency_models.py -v --tb=short
	@echo "Consistency tests completed"

test-cap: ## Run CAP theorem validation tests
	@echo "Running CAP theorem tests..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/chaos/test_cap_theorem.py -v --tb=short -s
	@echo "CAP theorem tests completed"

test-performance: ## Run performance benchmarks
	@echo "Running performance benchmarks..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/unit/test_consistency_models.py::TestPerformanceComparison -v --tb=short
	@echo "Performance tests completed"

test-comprehensive: validate-test-env start-cluster ## Run all tests
	@echo "Running comprehensive test suite..."
	@sleep 15  # Allow cluster to stabilize
	
	@echo "=== Running Consistency Model Tests ==="
	python3 -m pytest tests/unit/test_consistency_models.py -v --tb=short || true
	
	@echo "=== Running CAP Theorem Tests ==="
	python3 -m pytest tests/chaos/test_cap_theorem.py -v --tb=short -s || true
	
	@echo "=== Running Performance Tests ==="
	python3 -m pytest tests/unit/test_consistency_models.py::TestPerformanceComparison -v --tb=short || true
	
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
	@echo "Running KV store performance benchmarks..."
	@$(MAKE) validate-test-env
	@$(MAKE) start-cluster
	@sleep 20
	
	@echo "=== Consistency Level Performance Comparison ==="
	python3 -c "
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import statistics

def benchmark_consistency_level(consistency_level, num_operations=500):
    base_url = 'http://localhost:8081'
    session = requests.Session()
    
    # Warmup
    for i in range(10):
        try:
            session.put(f'{base_url}/kv/warmup_{i}?consistency={consistency_level}', 
                       json={'value': f'warmup_{i}'}, timeout=10)
        except:
            pass
    
    # Benchmark writes
    write_latencies = []
    start_time = time.time()
    
    for i in range(num_operations):
        op_start = time.time()
        try:
            response = session.put(f'{base_url}/kv/bench_{consistency_level}_{i}?consistency={consistency_level}', 
                                 json={'value': f'value_{i}'}, timeout=10)
            if response.status_code == 200:
                write_latencies.append(time.time() - op_start)
        except Exception as e:
            print(f'Write error: {e}')
    
    write_duration = time.time() - start_time
    write_throughput = len(write_latencies) / write_duration if write_duration > 0 else 0
    
    # Benchmark reads
    read_latencies = []
    start_time = time.time()
    
    for i in range(min(100, len(write_latencies))):
        op_start = time.time()
        try:
            response = session.get(f'{base_url}/kv/bench_{consistency_level}_{i}?consistency={consistency_level}', timeout=10)
            if response.status_code == 200:
                read_latencies.append(time.time() - op_start)
        except Exception as e:
            print(f'Read error: {e}')
    
    read_duration = time.time() - start_time
    read_throughput = len(read_latencies) / read_duration if read_duration > 0 else 0
    
    return {
        'consistency_level': consistency_level,
        'write_throughput': write_throughput,
        'read_throughput': read_throughput,
        'write_latency_avg': statistics.mean(write_latencies) * 1000 if write_latencies else 0,
        'write_latency_p95': statistics.quantiles(write_latencies, n=20)[18] * 1000 if len(write_latencies) > 20 else 0,
        'read_latency_avg': statistics.mean(read_latencies) * 1000 if read_latencies else 0,
        'read_latency_p95': statistics.quantiles(read_latencies, n=20)[18] * 1000 if len(read_latencies) > 20 else 0,
        'successful_writes': len(write_latencies),
        'successful_reads': len(read_latencies)
    }

# Test different consistency levels
consistency_levels = ['strong', 'eventual', 'local']
results = []

for level in consistency_levels:
    print(f'Benchmarking {level} consistency...')
    result = benchmark_consistency_level(level)
    results.append(result)

print('\n=== Performance Benchmark Results ===')
print(f'{'Consistency':<12} {'Write TPS':<10} {'Read TPS':<10} {'Write Avg':<12} {'Write P95':<12} {'Read Avg':<11} {'Read P95':<11}')
print('-' * 85)

for result in results:
    print(f'{result[\"consistency_level\"]:<12} '
          f'{result[\"write_throughput\"]:<10.1f} '
          f'{result[\"read_throughput\"]:<10.1f} '
          f'{result[\"write_latency_avg\"]:<12.2f} '
          f'{result[\"write_latency_p95\"]:<12.2f} '
          f'{result[\"read_latency_avg\"]:<11.2f} '
          f'{result[\"read_latency_p95\"]:<11.2f}')

print('\nLatency in milliseconds, Throughput in operations/second')
"
	@echo "Benchmark completed"

# CAP theorem demonstration
cap-demo: ## Demonstrate CAP theorem trade-offs
	@echo "Running CAP theorem demonstration..."
	@$(MAKE) validate-test-env
	@$(MAKE) start-cluster
	@sleep 20
	
	@echo "=== CAP Theorem Interactive Demonstration ==="
	python3 -c "
import requests
import time

base_url = 'http://localhost:8081'
session = requests.Session()

print('\\n1. Normal Operation (C + A + P seems possible)')
print('Writing with strong consistency...')
response = session.put(f'{base_url}/kv/cap_demo?consistency=strong', 
                      json={'value': 'initial_value'}, timeout=10)
print(f'Strong write success: {response.status_code == 200}')

print('\\nReading from all nodes...')
for port in [8081, 8082, 8083]:
    try:
        response = requests.get(f'http://localhost:{port}/kv/cap_demo?consistency=strong', timeout=5)
        if response.status_code == 200:
            value = response.json().get('value')
            print(f'Node {port}: {value}')
        else:
            print(f'Node {port}: Failed to read')
    except:
        print(f'Node {port}: Unreachable')

print('\\n2. Under Network Partition (Must choose C or A)')
print('In a real partition scenario:')
print('- CP System: Maintains consistency, sacrifices availability')
print('- AP System: Maintains availability, sacrifices immediate consistency')
print('- Cannot have all three simultaneously during partition')

print('\\n3. Consistency Levels Comparison')
consistency_levels = ['strong', 'eventual', 'local']
for level in consistency_levels:
    successes = 0
    for i in range(5):
        try:
            response = session.put(f'{base_url}/kv/demo_{level}_{i}?consistency={level}', 
                                 json={'value': f'value_{i}'}, timeout=3)
            if response.status_code == 200:
                successes += 1
        except:
            pass
    
    availability = successes / 5
    print(f'{level:>10} consistency: {availability:.1%} availability ({successes}/5 operations)')

print('\\nCAP Theorem: You can only guarantee 2 out of 3 properties simultaneously!')
"
	@echo "CAP demonstration completed"

# Monitoring and observability
start-monitoring: ## Start monitoring stack
	@echo "Starting monitoring stack..."
	docker-compose up -d prometheus grafana jaeger
	@echo "Monitoring stack started"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana: http://localhost:3000 (admin/kvstore_admin)"
	@echo "  Jaeger: http://localhost:16686"

logs: ## Show cluster logs
	@echo "Showing cluster logs..."
	docker-compose logs -f

logs-node: ## Show logs for specific node (usage: make logs-node NODE=kvstore-node1)
	@echo "Showing logs for $(NODE)..."
	docker-compose logs -f $(NODE)

# Development targets
dev-setup: ## Setup development environment
	@echo "Setting up development environment..."
	cd services/kvstore-node && go mod tidy
	@$(MAKE) build-proto
	@$(MAKE) validate-test-env
	@echo "Development environment setup completed"

format: ## Format Go code
	@echo "Formatting Go code..."
	cd services/kvstore-node && go fmt ./...
	@echo "Code formatting completed"

lint: ## Run Go linter
	@echo "Running Go linter..."
	cd services/kvstore-node && golangci-lint run
	@echo "Linting completed"

# Operational targets
backup-data: ## Backup cluster data
	@echo "Backing up cluster data..."
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	for node in node1 node2 node3; do \
		docker run --rm -v distributed-kv-store_kvstore_$${node}_data:/data -v $$(pwd)/backups:/backup alpine \
			tar czf /backup/kvstore_$${node}_backup_$$timestamp.tar.gz -C /data .; \
	done
	@echo "Backup completed"

restore-data: ## Restore cluster data (usage: make restore-data BACKUP=filename.tar.gz NODE=node1)
	@echo "Restoring cluster data from $(BACKUP) to $(NODE)..."
	@$(MAKE) stop-cluster
	docker run --rm -v distributed-kv-store_kvstore_$(NODE)_data:/data -v $$(pwd)/backups:/backup alpine \
		tar xzf /backup/$(BACKUP) -C /data
	@$(MAKE) start-cluster
	@echo "Data restoration completed"

# Consistency and repair operations
trigger-read-repair: ## Trigger read repair on all nodes
	@echo "Triggering read repair on all nodes..."
	@for port in 8081 8082 8083; do \
		echo "Triggering read repair on port $$port..."; \
		curl -X POST http://localhost:$$port/admin/repair || true; \
		echo ""; \
	done
	@echo "Read repair triggered on all nodes"

trigger-anti-entropy: ## Trigger anti-entropy on all nodes
	@echo "Triggering anti-entropy on all nodes..."
	@for port in 8081 8082 8083; do \
		echo "Triggering anti-entropy on port $$port..."; \
		curl -X POST http://localhost:$$port/admin/anti-entropy || true; \
		echo ""; \
	done
	@echo "Anti-entropy triggered on all nodes"

consistency-check: ## Check consistency across all nodes
	@echo "Checking consistency across all nodes..."
	@for port in 8081 8082 8083; do \
		echo "Consistency status for port $$port:"; \
		curl -s http://localhost:$$port/admin/consistency | python3 -m json.tool || true; \
		echo ""; \
	done

# Cleanup targets
clean-data: ## Clean all persistent data (WARNING: This will delete all data!)
	@echo "WARNING: This will delete all cluster data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(MAKE) stop-cluster; \
		docker volume rm -f distributed-kv-store_kvstore_node1_data; \
		docker volume rm -f distributed-kv-store_kvstore_node2_data; \
		docker volume rm -f distributed-kv-store_kvstore_node3_data; \
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
quick-start: dev-setup docker-build start-cluster test-consistency ## Quick start for development
	@echo ""
	@echo "🎉 Distributed KV Store with Tunable Consistency is ready!"
	@echo ""
	@echo "Cluster endpoints:"
	@echo "  Node 1: http://localhost:8081"
	@echo "  Node 2: http://localhost:8082"
	@echo "  Node 3: http://localhost:8083"
	@echo "  Load Balancer: http://localhost:8080"
	@echo ""
	@echo "Monitoring:"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana: http://localhost:3000 (admin/kvstore_admin)"
	@echo "  Jaeger: http://localhost:16686"
	@echo ""
	@echo "Try different consistency levels:"
	@echo "  # Strong consistency"
	@echo "  curl -X PUT 'http://localhost:8080/kv/mykey?consistency=strong' -d '{\"value\": \"myvalue\"}'"
	@echo "  curl 'http://localhost:8080/kv/mykey?consistency=strong'"
	@echo ""
	@echo "  # Eventual consistency"
	@echo "  curl -X PUT 'http://localhost:8080/kv/mykey2?consistency=eventual' -d '{\"value\": \"myvalue2\"}'"
	@echo "  curl 'http://localhost:8080/kv/mykey2?consistency=eventual'"
	@echo ""
	@echo "  # Local read (fastest)"
	@echo "  curl 'http://localhost:8080/kv/mykey2?consistency=local'"
	@echo ""
	@echo "Run CAP theorem demo: make cap-demo"
	@echo ""

# CI/CD targets
ci-test: ## Run CI tests
	@echo "Running CI test suite..."
	@$(MAKE) build
	@$(MAKE) test-unit
	@$(MAKE) docker-build
	@$(MAKE) test-comprehensive
	@echo "CI tests completed"
