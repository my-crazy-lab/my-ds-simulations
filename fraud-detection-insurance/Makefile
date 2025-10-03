# Fraud Detection Insurance Makefile
# ML-powered fraud detection for insurance claims

.PHONY: help build test clean deploy docker-build docker-up docker-down \
        run-tests run-ml-tests run-database-tests run-graph-tests \
        setup-dev install-deps format lint security-scan \
        start-services stop-services restart-services \
        backup-data restore-data migrate-schema \
        train-models deploy-models validate-models \
        deploy-staging deploy-production \
        monitor-health check-performance generate-reports

# Default target
help: ## Show this help message
	@echo "Fraud Detection Insurance - Available Commands:"
	@echo "=============================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Build targets
build: ## Build all fraud detection services
	@echo "🔨 Building fraud detection services..."
	cd services/fraud-detection-engine && go build -o ../../bin/fraud-detection-engine .
	@echo "✅ Build completed"

build-docker: ## Build Docker images
	@echo "🐳 Building Docker images..."
	docker-compose build
	@echo "✅ Docker images built"

# Test targets
test: ## Run all tests
	@echo "🧪 Running all tests..."
	$(MAKE) run-database-tests
	$(MAKE) run-ml-tests
	$(MAKE) run-graph-tests
	@echo "✅ All tests completed"

run-database-tests: ## Run database-specific tests
	@echo "🗄️ Running database tests..."
	cd tests/database && python -m pytest test_graph_ml_features.py -v
	@echo "✅ Database tests completed"

run-ml-tests: ## Run ML model tests
	@echo "🤖 Running ML tests..."
	cd tests/ml && python -m pytest -v
	@echo "✅ ML tests completed"

run-graph-tests: ## Run graph analytics tests
	@echo "📊 Running graph tests..."
	cd tests/graph && python -m pytest -v
	@echo "✅ Graph tests completed"

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

# Service management
start-services: ## Start all services
	@echo "🚀 Starting fraud detection services..."
	$(MAKE) docker-up
	@echo "✅ Services started"

stop-services: ## Stop all services
	@echo "🛑 Stopping fraud detection services..."
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
	docker-compose up -d postgres neo4j
	sleep 10
	$(MAKE) migrate-schema
	@echo "✅ Database setup completed"

migrate-schema: ## Run database migrations
	@echo "📊 Running database migrations..."
	cd services/fraud-detection-engine && go run migrations/*.go
	@echo "✅ Migrations completed"

backup-data: ## Backup database
	@echo "💾 Backing up database..."
	docker-compose exec postgres pg_dump -U fraud_user fraud_db > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup completed"

restore-data: ## Restore database from backup
	@echo "🔄 Restoring database..."
	@read -p "Enter backup file path: " backup_file; \
	docker-compose exec -T postgres psql -U fraud_user fraud_db < $$backup_file
	@echo "✅ Restore completed"

# ML model management
train-models: ## Train ML models
	@echo "🤖 Training ML models..."
	cd scripts && python train_fraud_models.py
	@echo "✅ Model training completed"

deploy-models: ## Deploy trained models
	@echo "🚀 Deploying ML models..."
	cd scripts && python deploy_models.py
	@echo "✅ Model deployment completed"

validate-models: ## Validate model performance
	@echo "✅ Validating model performance..."
	cd scripts && python validate_models.py
	@echo "✅ Model validation completed"

# Monitoring and performance
monitor-health: ## Check service health
	@echo "🏥 Checking service health..."
	curl -f http://localhost:8080/health || echo "❌ Fraud Detection Engine unhealthy"
	@echo "✅ Health check completed"

check-performance: ## Check performance metrics
	@echo "📊 Checking performance metrics..."
	curl -s http://localhost:8081/metrics | grep -E "(fraud_score|detection_rate|false_positive)"
	@echo "✅ Performance check completed"

generate-reports: ## Generate fraud detection reports
	@echo "📊 Generating reports..."
	cd scripts && python generate_fraud_report.py
	@echo "✅ Reports generated"

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
	rm -rf models/
	docker system prune -f
	@echo "✅ Cleanup completed"

# Development utilities
dev-shell: ## Open development shell
	docker-compose exec fraud-detection-engine /bin/bash

logs: ## View service logs
	docker-compose logs -f fraud-detection-engine

# Quick commands
quick-test: ## Quick test run
	cd tests/database && python -m pytest test_graph_ml_features.py::TestGraphMLFeatures::test_graph_based_fraud_detection -v

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
	@echo "Fraud Detection Insurance v1.0.0"
	@echo "Go version: $(shell go version)"
	@echo "Docker version: $(shell docker --version)"
	@echo "Python version: $(shell python --version)"

# Default development workflow
dev: ## Start development workflow
	$(MAKE) setup-dev
	$(MAKE) quick-start
	$(MAKE) quick-test
