.PHONY: help build test deploy-docker deploy-k8s chaos-test clean examples

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Quick Start Options:'
	@echo '  examples       - Show minimal examples guide (recommended first step)'
	@echo '  basic-saga     - Start basic saga demo'
	@echo '  sharding       - Start database sharding demo'
	@echo '  sync           - Start CRDT sync demo'
	@echo '  analytics      - Start analytics pipeline demo'
	@echo '  eventsourcing  - Start event sourcing demo'
	@echo ''
	@echo 'Full System:'
	@echo '  deploy-docker  - Deploy complete system with Docker Compose'
	@echo '  deploy-k8s     - Deploy to Kubernetes'
	@echo '  distributed    - Deploy distributed database architecture'
	@echo ''
	@echo 'Development:'
	@echo '  build          - Build all services'
	@echo '  test           - Run tests'
	@echo '  chaos-test     - Run chaos tests'
	@echo '  clean          - Clean up containers'
	@echo '  status         - Check service health'

examples: ## Show minimal examples guide
	@echo "=== MINIMAL EXAMPLES ==="
	@echo "See docs/MINIMAL_EXAMPLES.md for step-by-step guides"
	@echo ""
	@echo "Quick example - Basic Saga Pattern:"
	@echo "1. docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15"
	@echo "2. cd services/saga-orchestrator && go run main.go"
	@echo "3. curl -X POST http://localhost:8080/api/v1/sagas -d '{\"type\":\"order_processing\"}'"
	@echo ""
	@echo "For more examples: cat docs/MINIMAL_EXAMPLES.md"

basic-saga: ## Start basic saga demo
	@echo "Starting basic saga demo..."
	@if [ ! -f docs/docker-compose-basic.yml ]; then \
		echo "Creating basic Docker Compose file..."; \
		cat > docs/docker-compose-basic.yml << 'EOF'; \
version: '3.8'; \
services:; \
  postgres:; \
    image: postgres:15-alpine; \
    ports:; \
      - "5432:5432"; \
    environment:; \
      POSTGRES_PASSWORD: postgres; \
      POSTGRES_DB: microservices; \
  redis:; \
    image: redis:7-alpine; \
    ports:; \
      - "6379:6379"; \
EOF; \
	fi
	@docker-compose -f docs/docker-compose-basic.yml up -d
	@echo "Basic infrastructure started. Now run:"
	@echo "cd services/saga-orchestrator && go run main.go"

sharding: ## Start database sharding demo
	@echo "Starting database sharding demo..."
	@docker run -d --name pg-primary -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
	@docker run -d --name pg-shard1 -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:15
	@docker run -d --name pg-shard2 -p 5434:5432 -e POSTGRES_PASSWORD=postgres postgres:15
	@echo "PostgreSQL instances started. Now run:"
	@echo "cd services/sharding-proxy && go run main.go"

sync: ## Start CRDT sync demo
	@echo "Starting CRDT sync demo..."
	@docker run -d --name mongo -p 27017:27017 mongo:7
	@docker run -d --name redis -p 6379:6379 redis:7-alpine
	@echo "MongoDB and Redis started. Now run:"
	@echo "cd services/sync-service && go run main.go"

analytics: ## Start analytics pipeline demo
	@echo "Starting analytics pipeline demo..."
	@docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
	@docker run -d --name clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:latest
	@echo "Databases started. Now run:"
	@echo "cd services/analytics-etl && go run main.go"

eventsourcing: ## Start event sourcing demo
	@echo "Starting event sourcing demo..."
	@docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
	@docker run -d --name mongo -p 27017:27017 mongo:7
	@docker run -d --name clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:latest
	@echo "Databases started. Now run:"
	@echo "cd services/cqrs-event-store && go run main.go"

build: ## Build all services
	@echo "Building services..."
	@for service in saga-orchestrator inventory-service payment-service notification-service sharding-proxy sync-service analytics-etl disaster-recovery schema-migration consistency-testing cqrs-event-store; do \
		if [ -d "services/$$service" ]; then \
			echo "Building $$service..."; \
			cd services/$$service && go mod tidy && go build -o main . && cd ../..; \
		fi; \
	done
	@echo "Build complete!"

test: ## Run all tests (unit + integration + load)
	@echo "Running complete test suite..."
	@./scripts/run-tests.sh all

test-unit: ## Run unit tests only
	@echo "Running unit tests..."
	@./scripts/run-tests.sh unit

test-load: ## Run K6 load tests only
	@echo "Running load tests..."
	@./scripts/run-tests.sh load

test-integration: ## Run integration tests only
	@echo "Running integration tests..."
	@./scripts/run-tests.sh integration

test-coverage: ## Generate test coverage reports
	@echo "Generating coverage reports..."
	@mkdir -p coverage
	@for service in saga-orchestrator inventory-service payment-service notification-service sync-service; do \
		if [ -d "services/$$service" ]; then \
			echo "Generating coverage for $$service..."; \
			cd services/$$service && \
			go test -coverprofile=../../coverage/$$service.out ./... && \
			go tool cover -html=../../coverage/$$service.out -o ../../coverage/$$service.html && \
			cd ../..; \
		fi; \
	done
	@echo "Coverage reports generated in coverage/ directory"

deploy-docker: ## Deploy complete system with Docker Compose
	@echo "Deploying complete system with Docker Compose..."
	@docker-compose -f infrastructure/docker-compose.yml up -d
	@echo "Waiting for services to start..."
	@sleep 30
	@echo "Services started! Check http://localhost:3000 for Grafana"

distributed: ## Deploy distributed database architecture
	@echo "Deploying distributed database architecture..."
	@chmod +x scripts/deploy-distributed.sh
	@./scripts/deploy-distributed.sh deploy

deploy-k8s: ## Deploy to Kubernetes
	@echo "Deploying to Kubernetes..."
	@kubectl apply -f infrastructure/k8s/
	@echo "Kubernetes deployment complete!"

chaos-test: ## Run chaos tests
	@echo "Running chaos tests..."
	@cd chaos && python3 chaos_runner.py
	@echo "Chaos tests complete!"

clean: ## Clean up Docker containers and images
	@echo "Cleaning up..."
	@docker stop $$(docker ps -aq) 2>/dev/null || true
	@docker rm $$(docker ps -aq) 2>/dev/null || true
	@docker-compose -f infrastructure/docker-compose.yml down -v 2>/dev/null || true
	@docker-compose -f infrastructure/docker-compose-distributed.yml down -v 2>/dev/null || true
	@docker system prune -f
	@echo "Cleanup complete!"

status: ## Show status of all services
	@echo "=== SERVICE STATUS ==="
	@echo "Checking health endpoints..."
	@for port in 8080 8081 8082 8083 8090 8091 8092 8093 8094 8095; do \
		echo -n "Port $$port: "; \
		curl -s -f http://localhost:$$port/health > /dev/null && echo "✅ Healthy" || echo "❌ Not responding"; \
	done

logs: ## Show logs for running containers
	@echo "=== CONTAINER LOGS ==="
	@docker ps --format "table {{.Names}}\t{{.Status}}"
	@echo ""
	@echo "To view logs for a specific container:"
	@echo "docker logs -f <container_name>"

install: ## Install all dependencies (Go, Docker, K6, etc.)
	@echo "Installing development dependencies..."
	@./scripts/install-dependencies.sh

setup: ## Setup development environment
	@echo "Setting up development environment..."
	@./scripts/install-dependencies.sh
	@echo "Environment setup complete!"

docs: ## Open documentation
	@echo "=== DOCUMENTATION ==="
	@echo "Available documentation:"
	@echo "- Getting Started: docs/GETTING_STARTED.md"
	@echo "- Minimal Examples: docs/MINIMAL_EXAMPLES.md"
	@echo "- Service Breakdown: docs/SERVICE_BREAKDOWN.md"
	@echo "- Simplified Docker: docs/DOCKER_SIMPLIFIED.md"
	@echo ""
	@echo "Quick start: make examples"

k6-saga: ## Run K6 load test for saga orchestrator
	@echo "Running K6 load test for saga orchestrator..."
	@k6 run tests/k6/saga-orchestrator-load-test.js

k6-inventory: ## Run K6 load test for inventory service
	@echo "Running K6 load test for inventory service..."
	@k6 run tests/k6/inventory-service-load-test.js

k6-sync: ## Run K6 load test for sync service
	@echo "Running K6 load test for sync service..."
	@k6 run tests/k6/sync-service-load-test.js

k6-all: ## Run all K6 load tests
	@echo "Running all K6 load tests..."
	@make k6-saga
	@make k6-inventory
	@make k6-sync
