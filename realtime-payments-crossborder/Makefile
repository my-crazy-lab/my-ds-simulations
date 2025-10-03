# Real-time Payments & Cross-border System Makefile
# Provides build, test, and deployment automation for instant payment processing

.PHONY: help build build-all clean test test-unit test-integration test-latency test-crossborder \
        start start-all stop stop-all restart logs docker-build docker-push \
        setup-networks load-participants setup-liquidity \
        lint fmt vet security-scan deps-update \
        test-performance test-ha test-consistency \
        load-test-10k stress-test benchmark \
        docs serve-docs

# Variables
PROJECT_NAME := realtime-payments-crossborder
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
LDFLAGS := -X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)

# Docker settings
DOCKER_REGISTRY := localhost:5000
DOCKER_TAG := $(VERSION)

# Service directories (Rust and Go services)
RUST_SERVICES := payment-router fx-engine settlement-engine
GO_SERVICES := message-validator correspondent-gateway liquidity-manager
PYTHON_SERVICES := sanctions-screening

# Default target
help: ## Show this help message
	@echo "Real-time Payments & Cross-border System - Available Commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  %-25s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# Build targets
build: build-rust build-go ## Build all services

build-rust: ## Build Rust services
	@echo "Building Rust services..."
	@for service in $(RUST_SERVICES); do \
		echo "Building $$service..."; \
		cd services/$$service && cargo build --release; \
		cp target/release/$$service ../../bin/; \
		cd ../..; \
	done
	@echo "Rust services built successfully!"

build-go: ## Build Go services
	@echo "Building Go services..."
	@for service in $(GO_SERVICES); do \
		echo "Building $$service..."; \
		cd services/$$service && go build -ldflags "$(LDFLAGS)" -o ../../bin/$$service ./main.go; \
		cd ../..; \
	done
	@echo "Go services built successfully!"

build-service: ## Build specific service (usage: make build-service SERVICE=payment-router)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make build-service SERVICE=payment-router"; \
		exit 1; \
	fi
	@echo "Building $(SERVICE)..."
	@if echo "$(RUST_SERVICES)" | grep -q "$(SERVICE)"; then \
		cd services/$(SERVICE) && cargo build --release && cp target/release/$(SERVICE) ../../bin/; \
	elif echo "$(GO_SERVICES)" | grep -q "$(SERVICE)"; then \
		cd services/$(SERVICE) && go build -ldflags "$(LDFLAGS)" -o ../../bin/$(SERVICE) ./main.go; \
	else \
		echo "Unknown service: $(SERVICE)"; \
		exit 1; \
	fi
	@echo "$(SERVICE) built successfully!"

build-all: deps setup-networks build ## Install dependencies, setup networks, and build all services

clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	@rm -rf bin/
	@rm -rf logs/
	@rm -rf tmp/
	@for service in $(RUST_SERVICES); do \
		cd services/$$service && cargo clean; \
		cd ../..; \
	done
	@docker system prune -f
	@echo "Clean completed!"

# Dependency management
deps: deps-rust deps-go deps-python ## Install all dependencies

deps-rust: ## Install Rust dependencies
	@echo "Installing Rust dependencies..."
	@for service in $(RUST_SERVICES); do \
		echo "Installing dependencies for $$service..."; \
		cd services/$$service && cargo fetch; \
		cd ../..; \
	done
	@echo "Rust dependencies installed!"

deps-go: ## Install Go dependencies
	@echo "Installing Go dependencies..."
	@for service in $(GO_SERVICES); do \
		echo "Installing dependencies for $$service..."; \
		cd services/$$service && go mod tidy && go mod download; \
		cd ../..; \
	done
	@echo "Go dependencies installed!"

deps-python: ## Install Python dependencies
	@echo "Installing Python dependencies..."
	@for service in $(PYTHON_SERVICES); do \
		echo "Installing dependencies for $$service..."; \
		cd services/$$service && pip install -r requirements.txt; \
		cd ../..; \
	done
	@echo "Python dependencies installed!"

deps-update: ## Update all dependencies
	@echo "Updating dependencies..."
	@for service in $(RUST_SERVICES); do \
		cd services/$$service && cargo update; \
		cd ../..; \
	done
	@for service in $(GO_SERVICES); do \
		cd services/$$service && go get -u ./... && go mod tidy; \
		cd ../..; \
	done
	@echo "Dependencies updated!"

# Network and data setup
setup-networks: ## Setup payment networks and correspondent banks
	@echo "Setting up payment networks..."
	@./scripts/setup-payment-networks.sh
	@echo "Payment networks configured!"

load-participants: ## Load test participants and accounts
	@echo "Loading test participants..."
	@./scripts/load-participants.sh
	@echo "Test participants loaded!"

setup-liquidity: ## Initialize liquidity pools
	@echo "Setting up liquidity pools..."
	@./scripts/setup-liquidity.sh
	@echo "Liquidity pools initialized!"

# Testing targets
test: test-unit test-integration ## Run all tests

test-unit: ## Run unit tests
	@echo "Running unit tests..."
	@for service in $(RUST_SERVICES); do \
		echo "Testing $$service..."; \
		cd services/$$service && cargo test; \
		cd ../..; \
	done
	@for service in $(GO_SERVICES); do \
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

test-latency: ## Run latency tests
	@echo "Running latency tests..."
	@./scripts/wait-for-services.sh
	@cd tests/latency && python3 -m pytest -v latency_test.py
	@echo "Latency tests completed!"

test-crossborder: ## Run cross-border payment tests
	@echo "Running cross-border tests..."
	@./scripts/wait-for-services.sh
	@cd tests/crossborder && python3 -m pytest -v crossborder_test.py
	@echo "Cross-border tests completed!"

test-performance: ## Run performance tests
	@echo "Running performance tests..."
	@./scripts/wait-for-services.sh
	@cd tests/performance && go test -v -bench=. -benchmem ./...
	@echo "Performance tests completed!"

test-ha: ## Run high availability tests
	@echo "Running high availability tests..."
	@./scripts/wait-for-services.sh
	@cd tests/ha && python3 -m pytest -v ha_test.py
	@echo "High availability tests completed!"

test-consistency: ## Run data consistency tests
	@echo "Running data consistency tests..."
	@./scripts/wait-for-services.sh
	@cd tests/consistency && go test -v ./...
	@echo "Data consistency tests completed!"

# Code quality
lint: lint-rust lint-go ## Run linters

lint-rust: ## Run Rust linter
	@echo "Running Rust linter..."
	@for service in $(RUST_SERVICES); do \
		echo "Linting $$service..."; \
		cd services/$$service && cargo clippy -- -D warnings; \
		cd ../..; \
	done
	@echo "Rust linting completed!"

lint-go: ## Run Go linter
	@echo "Running Go linter..."
	@for service in $(GO_SERVICES); do \
		echo "Linting $$service..."; \
		cd services/$$service && golangci-lint run ./...; \
		cd ../..; \
	done
	@echo "Go linting completed!"

fmt: fmt-rust fmt-go ## Format code

fmt-rust: ## Format Rust code
	@echo "Formatting Rust code..."
	@for service in $(RUST_SERVICES); do \
		cd services/$$service && cargo fmt; \
		cd ../..; \
	done
	@echo "Rust code formatting completed!"

fmt-go: ## Format Go code
	@echo "Formatting Go code..."
	@for service in $(GO_SERVICES); do \
		cd services/$$service && go fmt ./...; \
		cd ../..; \
	done
	@echo "Go code formatting completed!"

vet: ## Run go vet
	@echo "Running go vet..."
	@for service in $(GO_SERVICES); do \
		echo "Vetting $$service..."; \
		cd services/$$service && go vet ./...; \
		cd ../..; \
	done
	@echo "Go vet completed!"

security-scan: ## Run security scan
	@echo "Running security scan..."
	@for service in $(RUST_SERVICES); do \
		echo "Scanning $$service..."; \
		cd services/$$service && cargo audit; \
		cd ../..; \
	done
	@for service in $(GO_SERVICES); do \
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
	@for service in $(RUST_SERVICES) $(GO_SERVICES) $(PYTHON_SERVICES); do \
		docker tag $(PROJECT_NAME)-$$service:latest $(DOCKER_REGISTRY)/$(PROJECT_NAME)-$$service:$(DOCKER_TAG); \
		docker push $(DOCKER_REGISTRY)/$(PROJECT_NAME)-$$service:$(DOCKER_TAG); \
	done
	@echo "Docker images pushed successfully!"

# Service management
start: ## Start all services with Docker Compose
	@echo "Starting all real-time payment services..."
	@docker-compose up -d
	@echo "Waiting for services to be ready..."
	@./scripts/wait-for-services.sh
	@echo "All services started successfully!"

start-infra: ## Start only infrastructure services
	@echo "Starting infrastructure services..."
	@docker-compose up -d postgres redis kafka zookeeper schema-registry influxdb prometheus grafana jaeger
	@echo "Infrastructure services started!"

start-service: ## Start specific service (usage: make start-service SERVICE=payment-router)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make start-service SERVICE=payment-router"; \
		exit 1; \
	fi
	@echo "Starting $(SERVICE)..."
	@docker-compose up -d $(SERVICE)
	@echo "$(SERVICE) started successfully!"

stop: ## Stop all services
	@echo "Stopping all services..."
	@docker-compose down
	@echo "All services stopped!"

stop-service: ## Stop specific service (usage: make stop-service SERVICE=payment-router)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make stop-service SERVICE=payment-router"; \
		exit 1; \
	fi
	@echo "Stopping $(SERVICE)..."
	@docker-compose stop $(SERVICE)
	@echo "$(SERVICE) stopped!"

restart: stop start ## Restart all services

restart-service: ## Restart specific service (usage: make restart-service SERVICE=payment-router)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make restart-service SERVICE=payment-router"; \
		exit 1; \
	fi
	@make stop-service SERVICE=$(SERVICE)
	@make start-service SERVICE=$(SERVICE)

logs: ## Show logs for all services
	@docker-compose logs -f

logs-service: ## Show logs for specific service (usage: make logs-service SERVICE=payment-router)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make logs-service SERVICE=payment-router"; \
		exit 1; \
	fi
	@docker-compose logs -f $(SERVICE)

# Performance testing
load-test-10k: ## Run load test at 10,000 TPS
	@echo "Running load test at 10,000 TPS..."
	@./tests/performance/load-test-10k-tps.sh
	@echo "Load test completed!"

stress-test: ## Run stress test
	@echo "Running stress test..."
	@./tests/performance/stress-test.sh
	@echo "Stress test completed!"

benchmark: ## Run comprehensive benchmarks
	@echo "Running comprehensive benchmarks..."
	@./tests/performance/benchmark.sh
	@echo "Benchmarks completed!"

# Monitoring and observability
metrics: ## Show current metrics
	@echo "Current payment metrics:"
	@curl -s http://localhost:9093/metrics | grep -E "(payment_|latency_|throughput_)" | head -20

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
	@make start-infra
	@make setup-networks
	@make load-participants
	@make setup-liquidity
	@make build-all
	@make start
	@echo "Development environment reset!"

# CI/CD helpers
ci-test: deps lint vet security-scan test ## Run all CI tests

ci-build: ci-test build docker-build ## Run CI build pipeline

# Quick commands
quick-start: start-infra setup-networks load-participants setup-liquidity build start ## Quick start for development

quick-test: ## Quick test run
	@make test-unit
	@make test-latency

# Environment info
info: ## Show environment information
	@echo "Real-time Payments & Cross-border System Information:"
	@echo "  Version: $(VERSION)"
	@echo "  Build Time: $(BUILD_TIME)"
	@echo "  Git Commit: $(GIT_COMMIT)"
	@echo "  Rust Version: $(shell rustc --version 2>/dev/null || echo "Not installed")"
	@echo "  Go Version: $(shell go version 2>/dev/null || echo "Not installed")"
	@echo "  Docker Version: $(shell docker --version)"
	@echo "  Docker Compose Version: $(shell docker-compose --version)"
	@echo ""
	@echo "Services:"
	@echo "  Rust Services:"
	@for service in $(RUST_SERVICES); do \
		echo "    - $$service"; \
	done
	@echo "  Go Services:"
	@for service in $(GO_SERVICES); do \
		echo "    - $$service"; \
	done
	@echo "  Python Services:"
	@for service in $(PYTHON_SERVICES); do \
		echo "    - $$service"; \
	done
	@echo ""
	@echo "Endpoints:"
	@echo "  - Payment Router: http://localhost:8451"
	@echo "  - Message Validator: http://localhost:8452"
	@echo "  - FX Engine: http://localhost:8453"
	@echo "  - Correspondent Gateway: http://localhost:8454"
	@echo "  - Settlement Engine: http://localhost:8455"
	@echo "  - Sanctions Screening: http://localhost:8456"
	@echo "  - Liquidity Manager: http://localhost:8457"
	@echo "  - Grafana: http://localhost:3003 (admin/realtime_admin)"
	@echo "  - Prometheus: http://localhost:9093"
	@echo "  - Jaeger: http://localhost:16689"
	@echo "  - InfluxDB: http://localhost:8086"

# Documentation
docs: ## Generate documentation
	@echo "Generating documentation..."
	@./scripts/generate-docs.sh
	@echo "Documentation generated!"

serve-docs: ## Serve documentation locally
	@echo "Serving documentation at http://localhost:8001"
	@cd docs && python3 -m http.server 8001
