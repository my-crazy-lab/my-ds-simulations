# Payments Acquiring Gateway Makefile
# Provides build, test, and deployment automation for PCI DSS compliant payment processing

.PHONY: help build build-all clean test test-unit test-integration test-fraud test-compliance test-3ds \
        start start-all stop stop-all restart logs docker-build docker-push \
        generate-certs init-hsm load-test-data \
        lint fmt vet security-scan deps-update \
        test-psp-failover test-circuit-breaker test-performance \
        compliance-scan pci-audit vulnerability-scan \
        docs serve-docs

# Variables
PROJECT_NAME := payments-acquiring-gateway
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
LDFLAGS := -X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)

# Docker settings
DOCKER_REGISTRY := localhost:5000
DOCKER_TAG := $(VERSION)

# Service directories
SERVICES := authorization-service tokenization-service fraud-detection-service three-d-secure-service settlement-service retry-engine hsm-simulator

# Default target
help: ## Show this help message
	@echo "Payments Acquiring Gateway - Available Commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  %-25s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# Build targets
build: ## Build all services
	@echo "Building all payment services..."
	@for service in $(SERVICES); do \
		echo "Building $$service..."; \
		cd services/$$service && go build -ldflags "$(LDFLAGS)" -o ../../bin/$$service ./main.go; \
		cd ../..; \
	done
	@echo "Build completed successfully!"

build-service: ## Build specific service (usage: make build-service SERVICE=authorization-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make build-service SERVICE=authorization-service"; \
		exit 1; \
	fi
	@echo "Building $(SERVICE)..."
	@cd services/$(SERVICE) && go build -ldflags "$(LDFLAGS)" -o ../../bin/$(SERVICE) ./main.go
	@echo "$(SERVICE) built successfully!"

build-all: deps generate-certs build ## Install dependencies, generate certificates, and build all services

clean: ## Clean build artifacts and certificates
	@echo "Cleaning build artifacts..."
	@rm -rf bin/
	@rm -rf logs/
	@rm -rf tmp/
	@rm -rf infrastructure/tls/*.crt
	@rm -rf infrastructure/tls/*.key
	@rm -rf infrastructure/tls/*.csr
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

# Certificate management
generate-certs: ## Generate TLS certificates for secure communication
	@echo "Generating TLS certificates..."
	@./scripts/generate-certificates.sh
	@echo "Certificates generated successfully!"

init-hsm: ## Initialize HSM simulator with test keys
	@echo "Initializing HSM simulator..."
	@./scripts/init-hsm.sh
	@echo "HSM simulator initialized!"

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

test-fraud: ## Run fraud detection tests
	@echo "Running fraud detection tests..."
	@./scripts/wait-for-services.sh
	@cd tests/fraud && python3 -m pytest -v fraud_detection_test.py
	@echo "Fraud detection tests completed!"

test-3ds: ## Run 3D Secure tests
	@echo "Running 3D Secure tests..."
	@./scripts/wait-for-services.sh
	@cd tests/3ds && python3 -m pytest -v three_d_secure_test.py
	@echo "3D Secure tests completed!"

test-compliance: ## Run PCI compliance tests
	@echo "Running PCI compliance tests..."
	@./scripts/wait-for-services.sh
	@cd tests/compliance && python3 -m pytest -v pci_compliance_test.py
	@echo "Compliance tests completed!"

test-performance: ## Run performance tests
	@echo "Running performance tests..."
	@./scripts/wait-for-services.sh
	@cd tests/performance && go test -v -bench=. -benchmem ./...
	@echo "Performance tests completed!"

# Comprehensive test suite
test-comprehensive: validate-test-env start-services wait-for-services test-unit-python test-unit test-integration test-fraud test-3ds test-compliance test-performance
	@echo "Comprehensive payment gateway testing completed successfully!"

test-unit-python: ## Run Python unit tests
	@echo "Running Python unit tests..."
	@cd tests/unit && python3 test_payment_processing.py
	@echo "Python unit tests completed!"

# Health check
health-check: ## Check service health
	@echo "Checking payment gateway health..."
	@curl -f http://localhost:8502/health || exit 1
	@echo "Payment gateway service is healthy"

# Wait for services to be ready
wait-for-services: ## Wait for services to be ready
	@echo "Waiting for payment services to be ready..."
	@./scripts/wait-for-services.sh

# Run specific test suites
test-payment-processing: ## Run payment processing tests
	@cd tests/unit && python3 test_payment_processing.py

test-fraud-detection: ## Run fraud detection tests
	@cd tests/fraud && python3 fraud_detection_test.py

# Validate test environment
validate-test-env: ## Validate test environment
	@echo "Validating test environment..."
	@command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed"; exit 1; }
	@command -v go >/dev/null 2>&1 || { echo "Go is required but not installed"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "curl is required but not installed"; exit 1; }
	@pip3 list | grep -q requests || pip3 install requests
	@pip3 list | grep -q pytest || pip3 install pytest
	@echo "Payment gateway test environment validated"

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
	@echo "Starting all payment services..."
	@docker-compose up -d
	@echo "Waiting for services to be ready..."
	@./scripts/wait-for-services.sh
	@echo "All services started successfully!"

start-infra: ## Start only infrastructure services
	@echo "Starting infrastructure services..."
	@docker-compose up -d postgres redis vault kafka zookeeper schema-registry prometheus grafana jaeger
	@echo "Infrastructure services started!"

start-service: ## Start specific service (usage: make start-service SERVICE=authorization-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make start-service SERVICE=authorization-service"; \
		exit 1; \
	fi
	@echo "Starting $(SERVICE)..."
	@docker-compose up -d $(SERVICE)
	@echo "$(SERVICE) started successfully!"

stop: ## Stop all services
	@echo "Stopping all services..."
	@docker-compose down
	@echo "All services stopped!"

stop-service: ## Stop specific service (usage: make stop-service SERVICE=authorization-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make stop-service SERVICE=authorization-service"; \
		exit 1; \
	fi
	@echo "Stopping $(SERVICE)..."
	@docker-compose stop $(SERVICE)
	@echo "$(SERVICE) stopped!"

restart: stop start ## Restart all services

restart-service: ## Restart specific service (usage: make restart-service SERVICE=authorization-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make restart-service SERVICE=authorization-service"; \
		exit 1; \
	fi
	@make stop-service SERVICE=$(SERVICE)
	@make start-service SERVICE=$(SERVICE)

logs: ## Show logs for all services
	@docker-compose logs -f

logs-service: ## Show logs for specific service (usage: make logs-service SERVICE=authorization-service)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make logs-service SERVICE=authorization-service"; \
		exit 1; \
	fi
	@docker-compose logs -f $(SERVICE)

# Data management
load-test-data: ## Load test data (merchants, test cards, etc.)
	@echo "Loading test data..."
	@./scripts/load-test-data.sh
	@echo "Test data loaded successfully!"

# High availability testing
test-psp-failover: ## Test PSP failover scenarios
	@echo "Testing PSP failover..."
	@./tests/ha/test-psp-failover.sh
	@echo "PSP failover test completed!"

test-circuit-breaker: ## Test circuit breaker functionality
	@echo "Testing circuit breaker..."
	@./tests/ha/test-circuit-breaker.sh
	@echo "Circuit breaker test completed!"

# Compliance and security
compliance-scan: ## Run comprehensive compliance scan
	@echo "Running compliance scan..."
	@./scripts/compliance-scan.sh
	@echo "Compliance scan completed!"

pci-audit: ## Run PCI DSS audit
	@echo "Running PCI DSS audit..."
	@./scripts/pci-audit.sh
	@echo "PCI audit completed!"

vulnerability-scan: ## Run vulnerability scan
	@echo "Running vulnerability scan..."
	@./scripts/vulnerability-scan.sh
	@echo "Vulnerability scan completed!"

# Performance testing
load-test-1000tps: ## Run load test at 1000 TPS
	@echo "Running load test at 1000 TPS..."
	@./tests/performance/load-test-1000tps.sh
	@echo "Load test completed!"

stress-test: ## Run stress test
	@echo "Running stress test..."
	@./tests/performance/stress-test.sh
	@echo "Stress test completed!"

# Documentation
docs: ## Generate documentation
	@echo "Generating documentation..."
	@./scripts/generate-docs.sh
	@echo "Documentation generated!"

serve-docs: ## Serve documentation locally
	@echo "Serving documentation at https://localhost:8000"
	@cd docs && python3 -m http.server 8000

# Monitoring and observability
metrics: ## Show current metrics
	@echo "Current payment metrics:"
	@curl -s http://localhost:9092/metrics | grep -E "(payment_|fraud_|authorization_)" | head -20

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
	@make generate-certs
	@make init-hsm
	@make build-all
	@make start
	@make load-test-data
	@echo "Development environment reset!"

# CI/CD helpers
ci-test: deps lint vet security-scan test ## Run all CI tests

ci-build: ci-test build docker-build ## Run CI build pipeline

# Quick commands
quick-start: start-infra generate-certs init-hsm build start load-test-data ## Quick start for development

quick-test: ## Quick test run
	@make test-unit SERVICE=authorization-service

# Environment info
info: ## Show environment information
	@echo "Payments Acquiring Gateway Information:"
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
	@echo ""
	@echo "Endpoints:"
	@echo "  - Authorization API: https://localhost:8446"
	@echo "  - Tokenization API: https://localhost:8445"
	@echo "  - Fraud Detection: http://localhost:8447"
	@echo "  - 3D Secure: http://localhost:8448"
	@echo "  - Settlement: http://localhost:8449"
	@echo "  - HSM Simulator: https://localhost:8444"
	@echo "  - Grafana: http://localhost:3002 (admin/payments_admin)"
	@echo "  - Prometheus: http://localhost:9092"
	@echo "  - Jaeger: http://localhost:16688"
