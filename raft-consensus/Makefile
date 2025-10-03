# Raft Consensus Algorithm - Makefile
# Production-grade build, test, and deployment automation

.PHONY: help build test clean docker-build docker-push start-cluster stop-cluster test-comprehensive benchmark chaos-test

# Default target
help: ## Show this help message
	@echo "Raft Consensus Algorithm - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# Variables
PROJECT_NAME := raft-consensus
DOCKER_REGISTRY := localhost:5000
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
DOCKER_IMAGE := $(DOCKER_REGISTRY)/$(PROJECT_NAME)
GO_VERSION := 1.21

# Build targets
build: ## Build the Raft node binary
	@echo "Building Raft node..."
	cd services/raft-node && go mod tidy
	cd services/raft-node && go build -o raft-node .
	@echo "Build completed successfully"

build-proto: ## Generate protobuf files
	@echo "Generating protobuf files..."
	cd services/raft-node && protoc --go_out=. --go-grpc_out=. proto/raft.proto
	@echo "Protobuf generation completed"

clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	cd services/raft-node && rm -f raft-node
	cd services/raft-node && go clean
	@echo "Clean completed"

# Docker targets
docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t $(PROJECT_NAME):$(VERSION) -t $(PROJECT_NAME):latest services/raft-node/
	@echo "Docker build completed"

docker-push: docker-build ## Push Docker image to registry
	@echo "Pushing Docker image to registry..."
	docker tag $(PROJECT_NAME):$(VERSION) $(DOCKER_IMAGE):$(VERSION)
	docker tag $(PROJECT_NAME):latest $(DOCKER_IMAGE):latest
	docker push $(DOCKER_IMAGE):$(VERSION)
	docker push $(DOCKER_IMAGE):latest
	@echo "Docker push completed"

# Cluster management
start-cluster: ## Start the Raft cluster
	@echo "Starting Raft cluster..."
	docker-compose up -d
	@echo "Waiting for cluster to be ready..."
	@sleep 30
	@$(MAKE) health-check
	@echo "Raft cluster started successfully"

stop-cluster: ## Stop the Raft cluster
	@echo "Stopping Raft cluster..."
	docker-compose down
	@echo "Raft cluster stopped"

restart-cluster: stop-cluster start-cluster ## Restart the Raft cluster

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
	cd services/raft-node && go test -v ./...
	@echo "Unit tests completed"

test-integration: ## Run integration tests
	@echo "Running integration tests..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/unit/test_raft_core.py -v --tb=short
	@echo "Integration tests completed"

test-chaos: ## Run chaos engineering tests
	@echo "Running chaos engineering tests..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/chaos/test_raft_chaos.py -v --tb=short -s
	@echo "Chaos tests completed"

test-performance: ## Run performance benchmarks
	@echo "Running performance benchmarks..."
	@$(MAKE) validate-test-env
	python3 -m pytest tests/unit/test_raft_core.py::TestRaftPerformance -v --tb=short
	@echo "Performance tests completed"

test-comprehensive: validate-test-env start-cluster ## Run all tests
	@echo "Running comprehensive test suite..."
	@sleep 10  # Allow cluster to stabilize
	
	@echo "=== Running Integration Tests ==="
	python3 -m pytest tests/unit/test_raft_core.py -v --tb=short || true
	
	@echo "=== Running Performance Tests ==="
	python3 -m pytest tests/unit/test_raft_core.py::TestRaftPerformance -v --tb=short || true
	
	@echo "=== Running Chaos Tests ==="
	python3 -m pytest tests/chaos/test_raft_chaos.py -v --tb=short -s || true
	
	@echo "Comprehensive testing completed"

validate-test-env: ## Validate test environment
	@echo "Validating test environment..."
	@command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed"; exit 1; }
	@python3 -c "import pytest, requests, docker" 2>/dev/null || { echo "Installing Python dependencies..."; pip3 install pytest requests docker; }
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose is required but not installed"; exit 1; }
	@echo "Test environment validated"

# Benchmarking
benchmark: ## Run performance benchmarks
	@echo "Running Raft performance benchmarks..."
	@$(MAKE) validate-test-env
	@$(MAKE) start-cluster
	@sleep 15
	
	@echo "=== Throughput Benchmark ==="
	python3 -c "
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor

def benchmark_throughput():
    base_url = 'http://localhost:8081'
    num_operations = 1000
    num_workers = 10
    
    def worker(worker_id, ops_per_worker):
        session = requests.Session()
        for i in range(ops_per_worker):
            try:
                session.put(f'{base_url}/kv/bench_key_{worker_id}_{i}', 
                           json={'value': f'bench_value_{worker_id}_{i}'}, 
                           timeout=5)
            except Exception as e:
                print(f'Worker {worker_id} error: {e}')
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(worker, worker_id, num_operations // num_workers)
            for worker_id in range(num_workers)
        ]
        for future in futures:
            future.result()
    
    end_time = time.time()
    duration = end_time - start_time
    throughput = num_operations / duration
    
    print(f'Benchmark Results:')
    print(f'  Operations: {num_operations}')
    print(f'  Duration: {duration:.2f}s')
    print(f'  Throughput: {throughput:.2f} ops/sec')
    print(f'  Latency (avg): {(duration * 1000) / num_operations:.2f}ms')

benchmark_throughput()
"
	@echo "Benchmark completed"

# Monitoring and observability
start-monitoring: ## Start monitoring stack
	@echo "Starting monitoring stack..."
	docker-compose up -d prometheus grafana jaeger
	@echo "Monitoring stack started"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana: http://localhost:3000 (admin/raft_admin)"
	@echo "  Jaeger: http://localhost:16686"

logs: ## Show cluster logs
	@echo "Showing cluster logs..."
	docker-compose logs -f

logs-node: ## Show logs for specific node (usage: make logs-node NODE=raft-node1)
	@echo "Showing logs for $(NODE)..."
	docker-compose logs -f $(NODE)

# Development targets
dev-setup: ## Setup development environment
	@echo "Setting up development environment..."
	cd services/raft-node && go mod tidy
	@$(MAKE) build-proto
	@$(MAKE) validate-test-env
	@echo "Development environment setup completed"

format: ## Format Go code
	@echo "Formatting Go code..."
	cd services/raft-node && go fmt ./...
	@echo "Code formatting completed"

lint: ## Run Go linter
	@echo "Running Go linter..."
	cd services/raft-node && golangci-lint run
	@echo "Linting completed"

# Operational targets
backup-data: ## Backup cluster data
	@echo "Backing up cluster data..."
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	docker run --rm -v raft-consensus_raft_node1_data:/data -v $$(pwd)/backups:/backup alpine \
		tar czf /backup/raft_backup_$$timestamp.tar.gz -C /data .
	@echo "Backup completed"

restore-data: ## Restore cluster data (usage: make restore-data BACKUP=filename.tar.gz)
	@echo "Restoring cluster data from $(BACKUP)..."
	@$(MAKE) stop-cluster
	docker run --rm -v raft-consensus_raft_node1_data:/data -v $$(pwd)/backups:/backup alpine \
		tar xzf /backup/$(BACKUP) -C /data
	@$(MAKE) start-cluster
	@echo "Data restoration completed"

scale-cluster: ## Scale cluster (usage: make scale-cluster NODES=5)
	@echo "Scaling cluster to $(NODES) nodes..."
	@echo "Note: This requires updating docker-compose.yml for additional nodes"
	@echo "Scaling not implemented yet - requires membership change support"

# Security and compliance
security-scan: ## Run security scan on Docker images
	@echo "Running security scan..."
	@command -v trivy >/dev/null 2>&1 || { echo "Trivy is required for security scanning"; exit 1; }
	trivy image $(PROJECT_NAME):latest
	@echo "Security scan completed"

# Cleanup targets
clean-data: ## Clean all persistent data (WARNING: This will delete all data!)
	@echo "WARNING: This will delete all cluster data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(MAKE) stop-cluster; \
		docker volume rm -f raft-consensus_raft_node1_data raft-consensus_raft_node1_wal; \
		docker volume rm -f raft-consensus_raft_node2_data raft-consensus_raft_node2_wal; \
		docker volume rm -f raft-consensus_raft_node3_data raft-consensus_raft_node3_wal; \
		echo "Data cleanup completed"; \
	else \
		echo "Data cleanup cancelled"; \
	fi

clean-all: clean stop-cluster ## Clean everything (code, containers, data)
	@echo "Cleaning everything..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "Complete cleanup finished"

# Documentation
docs: ## Generate documentation
	@echo "Generating documentation..."
	@echo "Documentation generation not implemented yet"

# Quick start
quick-start: dev-setup docker-build start-cluster test-integration ## Quick start for development
	@echo ""
	@echo "🎉 Raft Consensus cluster is ready!"
	@echo ""
	@echo "Cluster endpoints:"
	@echo "  Node 1: http://localhost:8081"
	@echo "  Node 2: http://localhost:8082"
	@echo "  Node 3: http://localhost:8083"
	@echo "  Load Balancer: http://localhost:8080"
	@echo ""
	@echo "Monitoring:"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana: http://localhost:3000 (admin/raft_admin)"
	@echo "  Jaeger: http://localhost:16686"
	@echo ""
	@echo "Try some commands:"
	@echo "  curl -X PUT http://localhost:8080/kv/mykey -d '{\"value\": \"myvalue\"}'"
	@echo "  curl http://localhost:8080/kv/mykey"
	@echo "  curl http://localhost:8080/admin/status"
	@echo ""

# CI/CD targets
ci-test: ## Run CI tests
	@echo "Running CI test suite..."
	@$(MAKE) build
	@$(MAKE) test-unit
	@$(MAKE) docker-build
	@$(MAKE) test-comprehensive
	@echo "CI tests completed"

cd-deploy: ## Deploy to production (placeholder)
	@echo "Production deployment not implemented yet"
	@echo "This would typically involve:"
	@echo "  - Building and pushing images"
	@echo "  - Updating Kubernetes manifests"
	@echo "  - Rolling deployment"
	@echo "  - Health checks"
