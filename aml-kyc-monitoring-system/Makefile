# AML/KYC Monitoring System Makefile
# Comprehensive build, test, and deployment automation

.PHONY: help build test clean deploy docker-build docker-up docker-down \
        run-tests run-integration-tests run-database-tests run-monitoring-tests \
        setup-dev install-deps format lint security-scan \
        start-services stop-services restart-services \
        backup-data restore-data migrate-schema \
        load-test stress-test benchmark \
        deploy-staging deploy-production \
        monitor-health check-compliance generate-reports

# Default target
help: ## Show this help message
	@echo "AML/KYC Monitoring System - Available Commands:"
	@echo "================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Build targets
build: ## Build all services
	@echo "🔨 Building AML/KYC monitoring services..."
	cd services/aml-engine && go build -o ../../bin/aml-engine .
	@echo "✅ Build completed"

build-docker: ## Build Docker images
	@echo "🐳 Building Docker images..."
	docker-compose build
	@echo "✅ Docker images built"

# Test targets
test: ## Run all tests
	@echo "🧪 Running all tests..."
	$(MAKE) run-database-tests
	$(MAKE) run-monitoring-tests
	$(MAKE) run-integration-tests
	@echo "✅ All tests completed"

run-database-tests: ## Run database-specific tests
	@echo "🗄️ Running database tests..."
	cd tests/database && python -m pytest test_graph_analytics_streaming.py -v
	@echo "✅ Database tests completed"

run-monitoring-tests: ## Run monitoring tests
	@echo "📊 Running monitoring tests..."
	cd tests/monitoring && python -m pytest -v
	@echo "✅ Monitoring tests completed"

run-integration-tests: ## Run integration tests
	@echo "🔗 Running integration tests..."
	cd tests && python -m pytest integration/ -v
	@echo "✅ Integration tests completed"

run-load-tests: ## Run load tests
	@echo "⚡ Running load tests..."
	k6 run tests/k6/aml-load-test.js
	@echo "✅ Load tests completed"

# Development targets
setup-dev: ## Setup development environment
	@echo "🛠️ Setting up development environment..."
	$(MAKE) install-deps
	$(MAKE) setup-database
	@echo "✅ Development environment ready"

install-deps: ## Install dependencies
	@echo "📦 Installing dependencies..."
	go mod tidy
	pip install -r requirements-test.txt
	@echo "✅ Dependencies installed"

format: ## Format code
	@echo "🎨 Formatting code..."
	go fmt ./...
	black tests/
	@echo "✅ Code formatted"

lint: ## Run linters
	@echo "🔍 Running linters..."
	golangci-lint run ./...
	flake8 tests/
	@echo "✅ Linting completed"

security-scan: ## Run security scans
	@echo "🔒 Running security scans..."
	gosec ./...
	safety check -r requirements-test.txt
	@echo "✅ Security scan completed"

# Docker targets
docker-up: ## Start Docker services
	@echo "🚀 Starting Docker services..."
	docker-compose up -d
	@echo "✅ Services started"

docker-down: ## Stop Docker services
	@echo "🛑 Stopping Docker services..."
	docker-compose down
	@echo "✅ Services stopped"

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-ps: ## Show running containers
	docker-compose ps

# Service management
start-services: ## Start all services
	@echo "🚀 Starting AML/KYC services..."
	$(MAKE) docker-up
	@echo "✅ Services started"

stop-services: ## Stop all services
	@echo "🛑 Stopping AML/KYC services..."
	$(MAKE) docker-down
	@echo "✅ Services stopped"

restart-services: ## Restart all services
	@echo "🔄 Restarting services..."
	$(MAKE) stop-services
	$(MAKE) start-services
	@echo "✅ Services restarted"

# Database management
setup-database: ## Setup database
	@echo "🗄️ Setting up database..."
	docker-compose up -d postgres redis neo4j
	sleep 10
	$(MAKE) migrate-schema
	@echo "✅ Database setup completed"

migrate-schema: ## Run database migrations
	@echo "📊 Running database migrations..."
	cd services/aml-engine && go run migrations/*.go
	@echo "✅ Migrations completed"

backup-data: ## Backup database
	@echo "💾 Backing up database..."
	docker-compose exec postgres pg_dump -U aml_user aml_db > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup completed"

restore-data: ## Restore database from backup
	@echo "🔄 Restoring database..."
	@read -p "Enter backup file path: " backup_file; \
	docker-compose exec -T postgres psql -U aml_user aml_db < $$backup_file
	@echo "✅ Restore completed"

# Monitoring and health checks
monitor-health: ## Check service health
	@echo "🏥 Checking service health..."
	curl -f http://localhost:8080/health || echo "❌ AML Engine unhealthy"
	curl -f http://localhost:9090/api/v1/query?query=up || echo "❌ Prometheus unhealthy"
	@echo "✅ Health check completed"

check-compliance: ## Run compliance checks
	@echo "📋 Running compliance checks..."
	cd tests && python -m pytest compliance/ -v
	@echo "✅ Compliance checks completed"

generate-reports: ## Generate monitoring reports
	@echo "📊 Generating reports..."
	cd scripts && python generate_aml_report.py
	@echo "✅ Reports generated"

# Performance testing
load-test: ## Run load tests
	@echo "⚡ Running load tests..."
	k6 run --vus 50 --duration 5m tests/k6/aml-load-test.js
	@echo "✅ Load test completed"

stress-test: ## Run stress tests
	@echo "💪 Running stress tests..."
	k6 run --vus 100 --duration 10m tests/k6/aml-stress-test.js
	@echo "✅ Stress test completed"

benchmark: ## Run benchmarks
	@echo "🏃 Running benchmarks..."
	cd services/aml-engine && go test -bench=. -benchmem
	@echo "✅ Benchmarks completed"

# Deployment targets
deploy-staging: ## Deploy to staging
	@echo "🚀 Deploying to staging..."
	docker-compose -f docker-compose.staging.yml up -d
	@echo "✅ Staging deployment completed"

deploy-production: ## Deploy to production
	@echo "🚀 Deploying to production..."
	@echo "⚠️  Production deployment requires manual approval"
	@read -p "Are you sure you want to deploy to production? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker-compose -f docker-compose.prod.yml up -d; \
		echo "✅ Production deployment completed"; \
	else \
		echo "❌ Production deployment cancelled"; \
	fi

# Cleanup targets
clean: ## Clean build artifacts
	@echo "🧹 Cleaning build artifacts..."
	rm -rf bin/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	docker system prune -f
	@echo "✅ Cleanup completed"

clean-data: ## Clean all data (WARNING: destructive)
	@echo "⚠️  WARNING: This will delete all data!"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker-compose down -v; \
		docker volume prune -f; \
		echo "✅ Data cleanup completed"; \
	else \
		echo "❌ Data cleanup cancelled"; \
	fi

# Development utilities
dev-shell: ## Open development shell
	docker-compose exec aml-engine /bin/bash

logs: ## View service logs
	docker-compose logs -f aml-engine

tail-logs: ## Tail service logs
	docker-compose logs -f --tail=100

# Documentation
docs: ## Generate documentation
	@echo "📚 Generating documentation..."
	cd docs && make html
	@echo "✅ Documentation generated"

# Quick commands
quick-test: ## Quick test run
	cd tests/database && python -m pytest test_graph_analytics_streaming.py::TestGraphAnalyticsStreaming::test_streaming_enrichment_accuracy -v

quick-start: ## Quick start for development
	$(MAKE) docker-up
	sleep 15
	$(MAKE) monitor-health

# CI/CD helpers
ci-test: ## Run tests in CI environment
	@echo "🤖 Running CI tests..."
	$(MAKE) lint
	$(MAKE) security-scan
	$(MAKE) test
	@echo "✅ CI tests completed"

ci-build: ## Build in CI environment
	@echo "🤖 Running CI build..."
	$(MAKE) build
	$(MAKE) build-docker
	@echo "✅ CI build completed"

# Version management
version: ## Show version information
	@echo "AML/KYC Monitoring System v1.0.0"
	@echo "Go version: $(shell go version)"
	@echo "Docker version: $(shell docker --version)"
	@echo "Python version: $(shell python --version)"

# Default development workflow
dev: ## Start development workflow
	$(MAKE) setup-dev
	$(MAKE) quick-start
	$(MAKE) quick-test
