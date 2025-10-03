# Core Banking Ledger System Makefile
# Provides build, test, and deployment automation

.PHONY: help build build-all clean test test-unit test-integration test-chaos test-performance \
        start start-all stop stop-all restart logs docker-build docker-push \
        migrate-up migrate-down migrate-reset load-sample-data \
        lint fmt vet security-scan deps-update \
        chaos-network chaos-partition chaos-crash \
        benchmark load-test stress-test \
        docs serve-docs

# Variables
PROJECT_NAME := core-banking-ledger
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
LDFLAGS := -X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)

# Docker settings
DOCKER_REGISTRY := localhost:5000
DOCKER_TAG := $(VERSION)

# Service directories
SERVICES := ledger-service account-service transaction-service reconciliation-service audit-service

# Default target
help: ## Show this help message
	@echo "Core Banking Ledger System - Available Commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# Build targets
build: ## Build all services
	@echo "Building all services..."
	@for service in $(SERVICES); do \
		echo "Building $$service..."; \
		cd services/$$service && go build -ldflags "$(LDFLAGS)" -o ../../bin/$$service ./main.go; \
		cd ../..; \
	done
	@echo "Build completed successfully!"

build-service: ## Build specific service (usage: make build-service SERVICE=ledger-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make build-service SERVICE=ledger-service"; \
		exit 1; \
	fi
	@echo "Building $(SERVICE)..."
	@cd services/$(SERVICE) && go build -ldflags "$(LDFLAGS)" -o ../../bin/$(SERVICE) ./main.go
	@echo "$(SERVICE) built successfully!"

build-all: deps build ## Install dependencies and build all services

clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	@rm -rf bin/
	@rm -rf logs/
	@rm -rf tmp/
	@docker system prune -f
	@echo "Clean completed!"

# Dependency management
deps: ## Install and update dependencies
	@echo "Installing dependencies..."
	@for service in $(SERVICES); do \
		echo "Installing dependencies for $$service..."; \
		cd services/$$service && go mod tidy && go mod download; \
		cd ../..; \
	done
	@echo "Dependencies installed!"

deps-update: ## Update all dependencies
	@echo "Updating dependencies..."
	@for service in $(SERVICES); do \
		echo "Updating dependencies for $$service..."; \
		cd services/$$service && go get -u ./... && go mod tidy; \
		cd ../..; \
	done
	@echo "Dependencies updated!"

# Testing targets
test: test-unit test-integration ## Run all tests

test-unit: ## Run unit tests
	@echo "Running unit tests..."
	@for service in $(SERVICES); do \
		echo "Testing $$service..."; \
		cd services/$$service && go test -v -race -coverprofile=coverage.out ./...; \
		cd ../..; \
	done
	@echo "Unit tests completed!"

test-integration: ## Run integration tests
	@echo "Running integration tests..."
	@./scripts/wait-for-services.sh
	@cd tests/integration && go test -v -tags=integration ./...
	@echo "Integration tests completed!"

test-chaos: ## Run chaos engineering tests
	@echo "Running chaos engineering tests..."
	@./scripts/wait-for-services.sh
	@cd tests/chaos && python3 -m pytest -v
	@echo "Chaos tests completed!"

test-performance: ## Run performance tests
	@echo "Running performance tests..."
	@./scripts/wait-for-services.sh
	@cd tests/performance && python3 test_ledger_performance.py
	@cd tests/performance && go test -v -bench=. -benchmem ./...
	@echo "Performance tests completed!"

# Comprehensive test suite
test-comprehensive: validate-test-env start-services wait-for-services test-unit-python test-unit test-integration test-performance test-chaos
	@echo "Comprehensive testing completed successfully!"

test-unit-python: ## Run Python unit tests
	@echo "Running Python unit tests..."
	@cd tests/unit && python3 test_ledger_operations.py
	@echo "Python unit tests completed!"

# Health check
health-check: ## Check service health
	@echo "Checking service health..."
	@curl -f http://localhost:8501/health || exit 1
	@echo "Core Banking Ledger service is healthy"

# Wait for services to be ready
wait-for-services: ## Wait for services to be ready
	@echo "Waiting for services to be ready..."
	@./scripts/wait-for-services.sh

# Run specific test suites
test-ledger-operations: ## Run ledger operations tests
	@cd tests/unit && python3 test_ledger_operations.py

test-ledger-performance: ## Run ledger performance tests
	@cd tests/performance && python3 test_ledger_performance.py

# Validate test environment
validate-test-env: ## Validate test environment
	@echo "Validating test environment..."
	@command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed"; exit 1; }
	@command -v go >/dev/null 2>&1 || { echo "Go is required but not installed"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "curl is required but not installed"; exit 1; }
	@pip3 list | grep -q requests || pip3 install requests
	@pip3 list | grep -q psycopg2 || pip3 install psycopg2-binary
	@pip3 list | grep -q pytest || pip3 install pytest
	@echo "Test environment validated"

# Code quality
lint: ## Run linter
	@echo "Running linter..."
	@for service in $(SERVICES); do \
		echo "Linting $$service..."; \
		cd services/$$service && golangci-lint run ./...; \
		cd ../..; \
	done
	@echo "Linting completed!"

fmt: ## Format code
	@echo "Formatting code..."
	@for service in $(SERVICES); do \
		echo "Formatting $$service..."; \
		cd services/$$service && go fmt ./...; \
		cd ../..; \
	done
	@echo "Code formatting completed!"

vet: ## Run go vet
	@echo "Running go vet..."
	@for service in $(SERVICES); do \
		echo "Vetting $$service..."; \
		cd services/$$service && go vet ./...; \
		cd ../..; \
	done
	@echo "Go vet completed!"

security-scan: ## Run security scan
	@echo "Running security scan..."
	@for service in $(SERVICES); do \
		echo "Scanning $$service..."; \
		cd services/$$service && gosec ./...; \
		cd ../..; \
	done
	@echo "Security scan completed!"

# Docker targets
docker-build: ## Build Docker images
	@echo "Building Docker images..."
	@docker-compose build
	@echo "Docker images built successfully!"

docker-push: ## Push Docker images to registry
	@echo "Pushing Docker images to $(DOCKER_REGISTRY)..."
	@for service in $(SERVICES); do \
		docker tag $(PROJECT_NAME)-$$service:latest $(DOCKER_REGISTRY)/$(PROJECT_NAME)-$$service:$(DOCKER_TAG); \
		docker push $(DOCKER_REGISTRY)/$(PROJECT_NAME)-$$service:$(DOCKER_TAG); \
	done
	@echo "Docker images pushed successfully!"

# Service management
start: ## Start all services with Docker Compose
	@echo "Starting all services..."
	@docker-compose up -d
	@echo "Waiting for services to be ready..."
	@./scripts/wait-for-services.sh
	@echo "All services started successfully!"

start-infra: ## Start only infrastructure services
	@echo "Starting infrastructure services..."
	@docker-compose up -d postgres-primary postgres-replica redis kafka zookeeper schema-registry prometheus grafana jaeger
	@echo "Infrastructure services started!"

start-service: ## Start specific service (usage: make start-service SERVICE=ledger-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make start-service SERVICE=ledger-service"; \
		exit 1; \
	fi
	@echo "Starting $(SERVICE)..."
	@docker-compose up -d $(SERVICE)
	@echo "$(SERVICE) started successfully!"

stop: ## Stop all services
	@echo "Stopping all services..."
	@docker-compose down
	@echo "All services stopped!"

stop-service: ## Stop specific service (usage: make stop-service SERVICE=ledger-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make stop-service SERVICE=ledger-service"; \
		exit 1; \
	fi
	@echo "Stopping $(SERVICE)..."
	@docker-compose stop $(SERVICE)
	@echo "$(SERVICE) stopped!"

restart: stop start ## Restart all services

restart-service: ## Restart specific service (usage: make restart-service SERVICE=ledger-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make restart-service SERVICE=ledger-service"; \
		exit 1; \
	fi
	@make stop-service SERVICE=$(SERVICE)
	@make start-service SERVICE=$(SERVICE)

logs: ## Show logs for all services
	@docker-compose logs -f

logs-service: ## Show logs for specific service (usage: make logs-service SERVICE=ledger-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make logs-service SERVICE=ledger-service"; \
		exit 1; \
	fi
	@docker-compose logs -f $(SERVICE)

# Database management
migrate-up: ## Run database migrations
	@echo "Running database migrations..."
	@./scripts/migrate-db.sh up
	@echo "Database migrations completed!"

migrate-down: ## Rollback database migrations
	@echo "Rolling back database migrations..."
	@./scripts/migrate-db.sh down
	@echo "Database rollback completed!"

migrate-reset: ## Reset database (drop and recreate)
	@echo "Resetting database..."
	@./scripts/migrate-db.sh reset
	@echo "Database reset completed!"

load-sample-data: ## Load sample data into database
	@echo "Loading sample data..."
	@./scripts/load-sample-data.sh
	@echo "Sample data loaded successfully!"

# Chaos engineering
chaos-network: ## Simulate network partition
	@echo "Simulating network partition..."
	@./tests/chaos/network-partition.sh
	@echo "Network partition test completed!"

chaos-partition: ## Simulate database partition
	@echo "Simulating database partition..."
	@./tests/chaos/database-partition.sh
	@echo "Database partition test completed!"

chaos-crash: ## Simulate service crash
	@echo "Simulating service crash..."
	@./tests/chaos/service-crash.sh
	@echo "Service crash test completed!"

# Performance testing
benchmark: ## Run benchmark tests
	@echo "Running benchmark tests..."
	@./tests/performance/benchmark.sh
	@echo "Benchmark tests completed!"

load-test: ## Run load tests
	@echo "Running load tests..."
	@./tests/performance/load-test.sh
	@echo "Load tests completed!"

stress-test: ## Run stress tests
	@echo "Running stress tests..."
	@./tests/performance/stress-test.sh
	@echo "Stress tests completed!"

# Documentation
docs: ## Generate documentation
	@echo "Generating documentation..."
	@./scripts/generate-docs.sh
	@echo "Documentation generated!"

serve-docs: ## Serve documentation locally
	@echo "Serving documentation at http://localhost:8000"
	@cd docs && python3 -m http.server 8000

# Monitoring and observability
metrics: ## Show current metrics
	@echo "Current system metrics:"
	@curl -s http://localhost:9091/metrics | grep -E "(transaction_|account_|ledger_)" | head -20

health-check: ## Check health of all services
	@echo "Checking service health..."
	@./scripts/health-check.sh
	@echo "Health check completed!"

# Development helpers
dev-setup: ## Setup development environment
	@echo "Setting up development environment..."
	@./scripts/dev-setup.sh
	@echo "Development environment ready!"

dev-reset: ## Reset development environment
	@echo "Resetting development environment..."
	@make stop
	@make clean
	@make migrate-reset
	@make start
	@make load-sample-data
	@echo "Development environment reset!"

# CI/CD helpers
ci-test: deps lint vet security-scan test ## Run all CI tests

ci-build: ci-test build docker-build ## Run CI build pipeline

# Quick commands
quick-start: start-infra migrate-up load-sample-data build start ## Quick start for development

quick-test: ## Quick test run
	@make test-unit SERVICE=ledger-service

# Environment info
info: ## Show environment information
	@echo "Core Banking Ledger System Information:"
	@echo "  Version: $(VERSION)"
	@echo "  Build Time: $(BUILD_TIME)"
	@echo "  Git Commit: $(GIT_COMMIT)"
	@echo "  Go Version: $(shell go version)"
	@echo "  Docker Version: $(shell docker --version)"
	@echo "  Docker Compose Version: $(shell docker-compose --version)"
	@echo ""
	@echo "Services:"
	@for service in $(SERVICES); do \
		echo "  - $$service"; \
	done
