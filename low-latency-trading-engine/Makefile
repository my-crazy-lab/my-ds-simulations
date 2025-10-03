# Low-Latency Trading Engine Makefile
# Ultra-high performance trading system build and deployment automation

.PHONY: help build test clean deploy docker-build docker-up docker-down \
        run-tests run-latency-tests run-database-tests run-performance-tests \
        setup-dev install-deps format lint security-scan \
        start-services stop-services restart-services \
        backup-data restore-data migrate-schema \
        load-test stress-test benchmark-latency \
        deploy-staging deploy-production \
        monitor-health check-performance generate-reports

# Default target
help: ## Show this help message
	@echo "Low-Latency Trading Engine - Available Commands:"
	@echo "==============================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Build targets
build: ## Build all trading services
	@echo "🔨 Building trading engine services..."
	cd services/matching-engine && go build -o ../../bin/matching-engine .
	cd services/market-data-feed && go build -o ../../bin/market-data-feed .
	cd services/risk-manager && go build -o ../../bin/risk-manager .
	@echo "✅ Build completed"

build-optimized: ## Build with performance optimizations
	@echo "🚀 Building optimized trading engine..."
	cd services/matching-engine && go build -ldflags="-s -w" -gcflags="-B" -o ../../bin/matching-engine .
	cd services/market-data-feed && go build -ldflags="-s -w" -gcflags="-B" -o ../../bin/market-data-feed .
	cd services/risk-manager && go build -ldflags="-s -w" -gcflags="-B" -o ../../bin/risk-manager .
	@echo "✅ Optimized build completed"

build-docker: ## Build Docker images
	@echo "🐳 Building Docker images..."
	docker-compose build
	@echo "✅ Docker images built"

# Test targets
test: ## Run all tests
	@echo "🧪 Running all tests..."
	$(MAKE) run-database-tests
	$(MAKE) run-latency-tests
	$(MAKE) run-performance-tests
	@echo "✅ All tests completed"

run-database-tests: ## Run database-specific tests
	@echo "🗄️ Running database tests..."
	cd tests/database && python -m pytest test_deterministic_matching_persistence.py -v
	@echo "✅ Database tests completed"

run-latency-tests: ## Run latency tests
	@echo "⚡ Running latency tests..."
	cd tests/latency && python -m pytest -v
	@echo "✅ Latency tests completed"

run-performance-tests: ## Run performance tests
	@echo "🏃 Running performance tests..."
	cd tests/unit && go test -bench=. -benchmem
	@echo "✅ Performance tests completed"

run-integration-tests: ## Run integration tests
	@echo "🔗 Running integration tests..."
	cd tests && python -m pytest integration/ -v
	@echo "✅ Integration tests completed"

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
	goimports -w ./services/
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
	docker-compose logs -f matching-engine

docker-ps: ## Show running containers
	docker-compose ps

# Service management
start-services: ## Start all trading services
	@echo "🚀 Starting trading services..."
	$(MAKE) docker-up
	@echo "✅ Services started"

stop-services: ## Stop all trading services
	@echo "🛑 Stopping trading services..."
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
	docker-compose up -d postgres redis
	sleep 10
	$(MAKE) migrate-schema
	@echo "✅ Database setup completed"

migrate-schema: ## Run database migrations
	@echo "📊 Running database migrations..."
	cd services/matching-engine && go run migrations/*.go
	@echo "✅ Migrations completed"

backup-data: ## Backup database
	@echo "💾 Backing up database..."
	docker-compose exec postgres pg_dump -U trading_user trading_db > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup completed"

restore-data: ## Restore database from backup
	@echo "🔄 Restoring database..."
	@read -p "Enter backup file path: " backup_file; \
	docker-compose exec -T postgres psql -U trading_user trading_db < $$backup_file
	@echo "✅ Restore completed"

# Performance monitoring
monitor-health: ## Check service health
	@echo "🏥 Checking service health..."
	curl -f http://localhost:8080/health || echo "❌ Matching Engine unhealthy"
	curl -f http://localhost:8082/health || echo "❌ Market Data Feed unhealthy"
	curl -f http://localhost:8083/health || echo "❌ Risk Manager unhealthy"
	@echo "✅ Health check completed"

check-performance: ## Check performance metrics
	@echo "📊 Checking performance metrics..."
	curl -s http://localhost:8081/metrics | grep -E "(latency|throughput|orders_per_second)"
	@echo "✅ Performance check completed"

generate-reports: ## Generate performance reports
	@echo "📊 Generating reports..."
	cd scripts && python generate_trading_report.py
	@echo "✅ Reports generated"

# Performance testing
load-test: ## Run load tests
	@echo "⚡ Running load tests..."
	k6 run --vus 100 --duration 5m tests/k6/trading-load-test.js
	@echo "✅ Load test completed"

stress-test: ## Run stress tests
	@echo "💪 Running stress tests..."
	k6 run --vus 500 --duration 10m tests/k6/trading-stress-test.js
	@echo "✅ Stress test completed"

benchmark-latency: ## Run latency benchmarks
	@echo "🏃 Running latency benchmarks..."
	cd services/matching-engine && go test -bench=BenchmarkOrderProcessing -benchtime=10s
	@echo "✅ Latency benchmarks completed"

benchmark-throughput: ## Run throughput benchmarks
	@echo "🚀 Running throughput benchmarks..."
	cd services/matching-engine && go test -bench=BenchmarkThroughput -benchtime=30s
	@echo "✅ Throughput benchmarks completed"

# Market simulation
simulate-market: ## Simulate market conditions
	@echo "📈 Simulating market conditions..."
	docker-compose up -d market-data-feed
	@echo "✅ Market simulation started"

stop-simulation: ## Stop market simulation
	@echo "📉 Stopping market simulation..."
	docker-compose stop market-data-feed
	@echo "✅ Market simulation stopped"

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
	@echo "⚠️  WARNING: This will delete all trading data!"
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
	docker-compose exec matching-engine /bin/bash

logs: ## View service logs
	docker-compose logs -f matching-engine

tail-logs: ## Tail service logs
	docker-compose logs -f --tail=100

# Documentation
docs: ## Generate documentation
	@echo "📚 Generating documentation..."
	cd docs && make html
	@echo "✅ Documentation generated"

# Quick commands
quick-test: ## Quick test run
	cd tests/database && python -m pytest test_deterministic_matching_persistence.py::TestDeterministicMatching::test_ultra_low_latency_order_processing -v

quick-start: ## Quick start for development
	$(MAKE) docker-up
	sleep 20
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
	$(MAKE) build-optimized
	$(MAKE) build-docker
	@echo "✅ CI build completed"

# Performance tuning
tune-kernel: ## Tune kernel parameters for low latency
	@echo "⚙️ Tuning kernel parameters..."
	sudo sysctl -w net.core.rmem_max=134217728
	sudo sysctl -w net.core.wmem_max=134217728
	sudo sysctl -w net.ipv4.tcp_rmem="4096 87380 134217728"
	sudo sysctl -w net.ipv4.tcp_wmem="4096 65536 134217728"
	@echo "✅ Kernel tuning completed"

# Version management
version: ## Show version information
	@echo "Low-Latency Trading Engine v1.0.0"
	@echo "Go version: $(shell go version)"
	@echo "Docker version: $(shell docker --version)"
	@echo "Python version: $(shell python --version)"

# Default development workflow
dev: ## Start development workflow
	$(MAKE) setup-dev
	$(MAKE) quick-start
	$(MAKE) quick-test
