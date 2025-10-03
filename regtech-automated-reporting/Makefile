# RegTech Automated Reporting Makefile
# Regulatory compliance and audit trail automation

.PHONY: help build test clean deploy docker-build docker-up docker-down \
        run-tests run-compliance-tests run-database-tests run-audit-tests \
        setup-dev install-deps format lint security-scan \
        start-services stop-services restart-services \
        backup-data restore-data migrate-schema \
        generate-reports validate-reports submit-reports \
        deploy-staging deploy-production \
        monitor-health check-compliance audit-trail

# Default target
help: ## Show this help message
	@echo "RegTech Automated Reporting - Available Commands:"
	@echo "================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Build targets
build: ## Build all RegTech services
	@echo "🔨 Building RegTech services..."
	cd services/reporting-engine && go build -o ../../bin/reporting-engine .
	@echo "✅ Build completed"

build-docker: ## Build Docker images
	@echo "🐳 Building Docker images..."
	docker-compose build
	@echo "✅ Docker images built"

# Test targets
test: ## Run all tests
	@echo "🧪 Running all tests..."
	$(MAKE) run-database-tests
	$(MAKE) run-compliance-tests
	$(MAKE) run-audit-tests
	@echo "✅ All tests completed"

run-database-tests: ## Run database-specific tests
	@echo "🗄️ Running database tests..."
	cd tests/database && python -m pytest -v
	@echo "✅ Database tests completed"

run-compliance-tests: ## Run compliance tests
	@echo "📋 Running compliance tests..."
	cd tests/compliance && python -m pytest -v
	@echo "✅ Compliance tests completed"

run-audit-tests: ## Run audit tests
	@echo "🔍 Running audit tests..."
	cd tests/audit && python -m pytest -v
	@echo "✅ Audit tests completed"

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
	@echo "🚀 Starting RegTech services..."
	$(MAKE) docker-up
	@echo "✅ Services started"

stop-services: ## Stop all services
	@echo "🛑 Stopping RegTech services..."
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
	docker-compose up -d postgres
	sleep 10
	$(MAKE) migrate-schema
	@echo "✅ Database setup completed"

migrate-schema: ## Run database migrations
	@echo "📊 Running database migrations..."
	cd services/reporting-engine && go run migrations/*.go
	@echo "✅ Migrations completed"

backup-data: ## Backup database
	@echo "💾 Backing up database..."
	docker-compose exec postgres pg_dump -U regtech_user regtech_db > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup completed"

restore-data: ## Restore database from backup
	@echo "🔄 Restoring database..."
	@read -p "Enter backup file path: " backup_file; \
	docker-compose exec -T postgres psql -U regtech_user regtech_db < $$backup_file
	@echo "✅ Restore completed"

# Reporting functions
generate-reports: ## Generate regulatory reports
	@echo "📊 Generating regulatory reports..."
	cd scripts && python generate_regulatory_reports.py
	@echo "✅ Reports generated"

validate-reports: ## Validate report formats
	@echo "✅ Validating report formats..."
	cd scripts && python validate_reports.py
	@echo "✅ Report validation completed"

submit-reports: ## Submit reports to regulators
	@echo "📤 Submitting reports to regulators..."
	cd scripts && python submit_reports.py
	@echo "✅ Reports submitted"

# Monitoring and compliance
monitor-health: ## Check service health
	@echo "🏥 Checking service health..."
	curl -f http://localhost:8080/health || echo "❌ Reporting Engine unhealthy"
	@echo "✅ Health check completed"

check-compliance: ## Run compliance checks
	@echo "📋 Running compliance checks..."
	cd tests && python -m pytest compliance/ -v
	@echo "✅ Compliance checks completed"

audit-trail: ## Generate audit trail
	@echo "🔍 Generating audit trail..."
	cd scripts && python generate_audit_trail.py
	@echo "✅ Audit trail generated"

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

# Development utilities
dev-shell: ## Open development shell
	docker-compose exec reporting-engine /bin/bash

logs: ## View service logs
	docker-compose logs -f reporting-engine

# Quick commands
quick-test: ## Quick test run
	cd tests/database && python -m pytest -v

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
	@echo "RegTech Automated Reporting v1.0.0"
	@echo "Go version: $(shell go version)"
	@echo "Docker version: $(shell docker --version)"
	@echo "Python version: $(shell python --version)"

# Default development workflow
dev: ## Start development workflow
	$(MAKE) setup-dev
	$(MAKE) quick-start
	$(MAKE) quick-test
