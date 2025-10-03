# Custody & Key Management System Makefile
# Provides build, test, and deployment automation for secure custody operations

.PHONY: help build build-all clean test test-unit test-integration test-mpc test-hsm \
        start start-all stop stop-all restart logs docker-build docker-push \
        init-hsm generate-keys load-test-data \
        lint fmt vet security-scan deps-update \
        test-wallet-operations test-approval-workflow test-performance \
        compliance-scan security-audit vulnerability-scan \
        docs serve-docs

# Variables
PROJECT_NAME := custody-key-management-system
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
LDFLAGS := -X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)

# Docker settings
DOCKER_REGISTRY := localhost:5000
DOCKER_TAG := $(VERSION)

# Service definitions
SERVICES := wallet-manager mpc-service approval-service

# Go settings
GO_VERSION := 1.21
GOOS := $(shell go env GOOS)
GOARCH := $(shell go env GOARCH)

# Default target
help: ## Show this help message
	@echo "Custody & Key Management System - Available commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

# Build targets
build: ## Build all services
	@echo "Building all custody services..."
	@mkdir -p bin/
	@for service in $(SERVICES); do \
		echo "Building $$service..."; \
		cd services/$$service && go build -ldflags "$(LDFLAGS)" -o ../../bin/$$service ./main.go; \
		cd ../..; \
	done
	@echo "Build completed successfully!"

build-service: ## Build specific service (usage: make build-service SERVICE=wallet-manager)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make build-service SERVICE=wallet-manager"; \
		exit 1; \
	fi
	@echo "Building $(SERVICE)..."
	@cd services/$(SERVICE) && go build -ldflags "$(LDFLAGS)" -o ../../bin/$(SERVICE) ./main.go
	@echo "$(SERVICE) built successfully!"

build-all: deps init-hsm generate-keys build ## Install dependencies, initialize HSM, generate keys, and build all services

clean: ## Clean build artifacts and keys
	@echo "Cleaning build artifacts..."
	@rm -rf bin/
	@rm -rf logs/
	@rm -rf tmp/
	@rm -rf keys/test_*
	@docker system prune -f
	@echo "Clean completed!"

# Dependency management
deps: ## Install and update dependencies
	@echo "Installing dependencies..."
	@go mod download
	@go mod tidy
	@echo "Dependencies updated!"

deps-update: ## Update all dependencies
	@echo "Updating dependencies..."
	@go get -u ./...
	@go mod tidy
	@echo "Dependencies updated!"

# Key management
generate-keys: ## Generate test keys for development
	@echo "Generating test keys..."
	@./scripts/generate-test-keys.sh
	@echo "Test keys generated successfully!"

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

test-mpc: ## Run multi-party computation tests
	@echo "Running MPC tests..."
	@./scripts/wait-for-services.sh
	@cd tests/mpc && python3 -m pytest -v mpc_test.py
	@echo "MPC tests completed!"

test-hsm: ## Run HSM integration tests
	@echo "Running HSM tests..."
	@./scripts/wait-for-services.sh
	@cd tests/hsm && python3 -m pytest -v hsm_test.py
	@echo "HSM tests completed!"

test-performance: ## Run performance tests
	@echo "Running performance tests..."
	@./scripts/wait-for-services.sh
	@cd tests/performance && go test -v -bench=. -benchmem ./...
	@echo "Performance tests completed!"

# Comprehensive test suite
test-comprehensive: validate-test-env start-services wait-for-services test-unit-python test-unit test-integration test-mpc test-hsm test-performance
	@echo "Comprehensive custody system testing completed successfully!"

test-unit-python: ## Run Python unit tests
	@echo "Running Python unit tests..."
	@cd tests/wallets && python3 test_wallet_operations.py
	@echo "Python unit tests completed!"

# Health check
health-check: ## Check service health
	@echo "Checking custody system health..."
	@curl -f http://localhost:8511/health || exit 1
	@curl -f http://localhost:8512/health || exit 1
	@curl -f http://localhost:8513/health || exit 1
	@echo "Custody system services are healthy"

# Wait for services to be ready
wait-for-services: ## Wait for services to be ready
	@echo "Waiting for custody services to be ready..."
	@./scripts/wait-for-services.sh

# Run specific test suites
test-wallet-operations: ## Run wallet operations tests
	@cd tests/wallets && python3 test_wallet_operations.py

test-approval-workflow: ## Run approval workflow tests
	@cd tests/approval && python3 test_approval_workflow.py

# Validate test environment
validate-test-env: ## Validate test environment
	@echo "Validating test environment..."
	@command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed"; exit 1; }
	@command -v go >/dev/null 2>&1 || { echo "Go is required but not installed"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "curl is required but not installed"; exit 1; }
	@pip3 list | grep -q requests || pip3 install requests
	@pip3 list | grep -q pytest || pip3 install pytest
	@pip3 list | grep -q cryptography || pip3 install cryptography
	@echo "Custody system test environment validated"

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
	@go fmt ./...
	@echo "Code formatting completed!"

vet: ## Run go vet
	@echo "Running go vet..."
	@go vet ./...
	@echo "Go vet completed!"

security-scan: ## Run security scan
	@echo "Running security scan..."
	@gosec ./...
	@echo "Security scan completed!"

# Docker targets
docker-build: ## Build Docker images
	@echo "Building Docker images..."
	@for service in $(SERVICES); do \
		echo "Building Docker image for $$service..."; \
		docker build -t $(PROJECT_NAME)-$$service:latest -f services/$$service/Dockerfile services/$$service/; \
	done
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
	@echo "Starting all custody services..."
	@docker-compose up -d
	@echo "Waiting for services to be ready..."
	@./scripts/wait-for-services.sh
	@echo "All custody services started successfully!"

start-all: start ## Alias for start

stop: ## Stop all services
	@echo "Stopping all custody services..."
	@docker-compose down
	@echo "All custody services stopped!"

stop-all: stop ## Alias for stop

restart: stop start ## Restart all services

logs: ## Show logs for all services
	@docker-compose logs -f

logs-service: ## Show logs for specific service (usage: make logs-service SERVICE=wallet-manager)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE parameter is required. Usage: make logs-service SERVICE=wallet-manager"; \
		exit 1; \
	fi
	@docker-compose logs -f $(SERVICE)

# Data management
load-test-data: ## Load test data (wallets, keys, etc.)
	@echo "Loading test data..."
	@./scripts/load-test-data.sh
	@echo "Test data loaded successfully!"

# Security and compliance
compliance-scan: ## Run comprehensive compliance scan
	@echo "Running compliance scan..."
	@./scripts/compliance-scan.sh
	@echo "Compliance scan completed!"

security-audit: ## Run security audit
	@echo "Running security audit..."
	@./scripts/security-audit.sh
	@echo "Security audit completed!"

vulnerability-scan: ## Run vulnerability scan
	@echo "Running vulnerability scan..."
	@./scripts/vulnerability-scan.sh
	@echo "Vulnerability scan completed!"

# Performance testing
load-test-signing: ## Run load test for signing operations
	@echo "Running signing load test..."
	@./tests/performance/load-test-signing.sh
	@echo "Signing load test completed!"

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

# Development helpers
dev-setup: ## Setup development environment
	@echo "Setting up development environment..."
	@make deps
	@make generate-keys
	@make init-hsm
	@make build
	@echo "Development environment setup completed!"

dev-reset: ## Reset development environment
	@echo "Resetting development environment..."
	@make stop
	@make clean
	@make dev-setup
	@make start
	@make load-test-data
	@echo "Development environment reset!"

# CI/CD helpers
ci-test: deps lint vet security-scan test ## Run all CI tests

ci-build: ci-test build docker-build ## Run CI build pipeline

# Quick commands
quick-start: start generate-keys init-hsm build start load-test-data ## Quick start for development

quick-test: ## Quick test run
	@make test-unit SERVICE=wallet-manager

# Environment info
info: ## Show environment information
	@echo "Custody & Key Management System Information:"
	@echo "  Version: $(VERSION)"
	@echo "  Build Time: $(BUILD_TIME)"
	@echo "  Git Commit: $(GIT_COMMIT)"
	@echo "  Go Version: $(shell go version)"
	@echo "  Docker Version: $(shell docker --version)"
	@echo "  Docker Compose Version: $(shell docker-compose --version)"
