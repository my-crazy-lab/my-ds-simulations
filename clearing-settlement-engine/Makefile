# Clearing & Settlement Engine Makefile
# Comprehensive build, test, and deployment automation

.PHONY: help build test deploy clean

# Default target
help:
	@echo "Clearing & Settlement Engine - Available Commands:"
	@echo ""
	@echo "🏗️  BUILD COMMANDS"
	@echo "  build-all              Build all services"
	@echo "  build-go               Build Go services (transaction-collector, settlement-processor, reporting)"
	@echo "  build-java             Build Java services (netting-engine, risk-manager, reconciliation)"
	@echo "  build-python           Build Python services (collateral-manager)"
	@echo ""
	@echo "🚀 DEPLOYMENT COMMANDS"
	@echo "  quick-start            Start all services with infrastructure"
	@echo "  start-infra            Start infrastructure services only"
	@echo "  start-services         Start application services only"
	@echo "  stop-all               Stop all services"
	@echo "  restart-all            Restart all services"
	@echo ""
	@echo "🔧 SETUP COMMANDS"
	@echo "  setup-participants     Initialize clearing participants"
	@echo "  setup-collateral       Setup collateral pools"
	@echo "  load-test-data         Load test transactions"
	@echo "  setup-networks         Configure settlement networks"
	@echo ""
	@echo "🧪 TESTING COMMANDS"
	@echo "  test-all               Run all tests"
	@echo "  test-settlement        Test settlement cycle"
	@echo "  test-netting           Test netting algorithms"
	@echo "  test-risk              Test risk management"
	@echo "  test-atomic            Test atomic settlement"
	@echo "  test-performance       Run performance tests"
	@echo "  test-ha                Test high availability"
	@echo ""
	@echo "📊 OPERATIONS COMMANDS"
	@echo "  run-settlement-cycle   Execute T+1 settlement cycle"
	@echo "  run-bilateral-netting  Execute bilateral netting"
	@echo "  run-multilateral-netting Execute multilateral netting"
	@echo "  check-risk-exposure    Check participant risk exposure"
	@echo "  generate-reports       Generate regulatory reports"
	@echo ""
	@echo "🔍 MONITORING COMMANDS"
	@echo "  health-check           Check service health"
	@echo "  logs                   View service logs"
	@echo "  metrics                View system metrics"
	@echo "  traces                 View distributed traces"
	@echo ""
	@echo "🧹 MAINTENANCE COMMANDS"
	@echo "  clean                  Clean build artifacts"
	@echo "  reset-db               Reset database"
	@echo "  backup-db              Backup database"
	@echo "  lint                   Run code linting"
	@echo "  security-scan          Run security scans"

# Build Commands
build-all: build-go build-java build-python
	@echo "✅ All services built successfully"

build-go:
	@echo "🔨 Building Go services..."
	cd services/transaction-collector && go mod tidy && go build -o bin/transaction-collector ./cmd/main.go
	cd services/settlement-processor && go mod tidy && go build -o bin/settlement-processor ./cmd/main.go
	cd services/reporting-service && go mod tidy && go build -o bin/reporting-service ./cmd/main.go
	@echo "✅ Go services built"

build-java:
	@echo "🔨 Building Java services..."
	cd services/netting-engine && ./mvnw clean package -DskipTests
	cd services/risk-manager && ./mvnw clean package -DskipTests
	cd services/reconciliation-service && ./mvnw clean package -DskipTests
	@echo "✅ Java services built"

build-python:
	@echo "🔨 Building Python services..."
	cd services/collateral-manager && pip install -r requirements.txt
	@echo "✅ Python services built"

# Deployment Commands
quick-start: start-infra wait-for-infra setup-participants start-services health-check
	@echo "🚀 Clearing & Settlement Engine started successfully!"
	@echo "📊 Grafana Dashboard: http://localhost:3004 (admin/settlement_admin)"
	@echo "📈 Prometheus Metrics: http://localhost:9094"
	@echo "🔍 Jaeger Tracing: http://localhost:16690"

start-infra:
	@echo "🏗️ Starting infrastructure services..."
	docker-compose up -d postgres redis zookeeper kafka schema-registry prometheus grafana jaeger

wait-for-infra:
	@echo "⏳ Waiting for infrastructure services..."
	./scripts/wait-for-services.sh

start-services:
	@echo "🚀 Starting application services..."
	docker-compose up -d transaction-collector netting-engine settlement-processor risk-manager collateral-manager reporting-service reconciliation-service

stop-all:
	@echo "🛑 Stopping all services..."
	docker-compose down

restart-all: stop-all quick-start

# Setup Commands
setup-participants:
	@echo "👥 Setting up clearing participants..."
	./scripts/setup-participants.sh

setup-collateral:
	@echo "💰 Setting up collateral pools..."
	./scripts/setup-collateral.sh

load-test-data:
	@echo "📊 Loading test transactions..."
	./scripts/load-test-transactions.sh

setup-networks:
	@echo "🌐 Configuring settlement networks..."
	./scripts/setup-networks.sh

# Testing Commands
test-all: test-settlement test-netting test-risk test-atomic test-performance
	@echo "✅ All tests completed"

test-settlement:
	@echo "🧪 Testing settlement cycle..."
	cd tests/settlement && python settlement_cycle_test.py
	cd tests/settlement && python -m pytest settlement_cycle_test.py -v

test-netting:
	@echo "🧪 Testing netting algorithms..."
	cd tests/netting && python bilateral_netting_test.py
	cd tests/netting && python multilateral_netting_test.py
	cd tests/netting && python netting_optimization_test.py

test-risk:
	@echo "🧪 Testing risk management..."
	cd tests/risk && python exposure_monitoring_test.py
	cd tests/risk && python collateral_management_test.py
	cd tests/risk && python margin_call_test.py

test-atomic:
	@echo "🧪 Testing atomic settlement..."
	cd tests/settlement && python atomic_settlement_test.py

test-performance:
	@echo "🧪 Running performance tests..."
	cd tests/performance && python settlement_performance_test.py
	cd tests/performance && python netting_performance_test.py

test-ha:
	@echo "🧪 Testing high availability..."
	cd tests/ha && python settlement_failover_test.py
	cd tests/ha && python data_consistency_test.py

# Operations Commands
run-settlement-cycle:
	@echo "💼 Running T+1 settlement cycle..."
	curl -X POST http://localhost:8463/api/v1/settlement/cycle \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer settlement_token" \
		-d '{"settlement_date": "'$(shell date -d '+1 day' '+%Y-%m-%d')'", "currency": "USD"}'

run-bilateral-netting:
	@echo "💼 Running bilateral netting..."
	curl -X POST http://localhost:8462/api/v1/netting/bilateral \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer settlement_token" \
		-d '{"participants": ["BANK001", "BANK002"], "currency": "USD", "cutoff_time": "'$(shell date -u +%Y-%m-%dT%H:%M:%SZ)'"}'

run-multilateral-netting:
	@echo "💼 Running multilateral netting..."
	curl -X POST http://localhost:8462/api/v1/netting/multilateral \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer settlement_token" \
		-d '{"participants": ["BANK001", "BANK002", "BANK003", "BANK004"], "currency": "USD", "cutoff_time": "'$(shell date -u +%Y-%m-%dT%H:%M:%SZ)'"}'

check-risk-exposure:
	@echo "💼 Checking risk exposure..."
	curl -X GET http://localhost:8464/api/v1/risk/exposure \
		-H "Authorization: Bearer settlement_token"

generate-reports:
	@echo "💼 Generating regulatory reports..."
	curl -X POST http://localhost:8466/api/v1/reports/generate \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer settlement_token" \
		-d '{"report_type": "SETTLEMENT_SUMMARY", "date": "'$(shell date '+%Y-%m-%d')'"}'

# Monitoring Commands
health-check:
	@echo "🔍 Checking service health..."
	@echo "Transaction Collector:"
	@curl -s http://localhost:8461/health | jq '.status' || echo "❌ Service unavailable"
	@echo "Netting Engine:"
	@curl -s http://localhost:8462/health | jq '.status' || echo "❌ Service unavailable"
	@echo "Settlement Processor:"
	@curl -s http://localhost:8463/health | jq '.status' || echo "❌ Service unavailable"
	@echo "Risk Manager:"
	@curl -s http://localhost:8464/health | jq '.status' || echo "❌ Service unavailable"
	@echo "Collateral Manager:"
	@curl -s http://localhost:8465/health | jq '.status' || echo "❌ Service unavailable"
	@echo "Reporting Service:"
	@curl -s http://localhost:8466/health | jq '.status' || echo "❌ Service unavailable"
	@echo "Reconciliation Service:"
	@curl -s http://localhost:8467/health | jq '.status' || echo "❌ Service unavailable"

logs:
	@echo "📋 Viewing service logs..."
	docker-compose logs -f --tail=100

metrics:
	@echo "📊 Opening Prometheus metrics..."
	open http://localhost:9094

traces:
	@echo "🔍 Opening Jaeger traces..."
	open http://localhost:16690

# Maintenance Commands
clean:
	@echo "🧹 Cleaning build artifacts..."
	find . -name "target" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "bin" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	docker system prune -f

reset-db:
	@echo "🗄️ Resetting database..."
	docker-compose stop postgres
	docker volume rm clearing-settlement-engine_postgres_data 2>/dev/null || true
	docker-compose up -d postgres
	sleep 10
	make setup-participants

backup-db:
	@echo "💾 Backing up database..."
	mkdir -p backups
	docker exec settlement-postgres pg_dump -U settlement_user settlement_engine > backups/settlement_backup_$(shell date +%Y%m%d_%H%M%S).sql

lint:
	@echo "🔍 Running code linting..."
	cd services/transaction-collector && golangci-lint run
	cd services/settlement-processor && golangci-lint run
	cd services/reporting-service && golangci-lint run
	cd services/netting-engine && ./mvnw checkstyle:check
	cd services/risk-manager && ./mvnw checkstyle:check
	cd services/reconciliation-service && ./mvnw checkstyle:check
	cd services/collateral-manager && flake8 . && black --check .

security-scan:
	@echo "🔒 Running security scans..."
	cd services/transaction-collector && gosec ./...
	cd services/settlement-processor && gosec ./...
	cd services/reporting-service && gosec ./...
	cd services/netting-engine && ./mvnw org.owasp:dependency-check-maven:check
	cd services/risk-manager && ./mvnw org.owasp:dependency-check-maven:check
	cd services/reconciliation-service && ./mvnw org.owasp:dependency-check-maven:check
	cd services/collateral-manager && safety check

# Load Testing Commands
load-test-1k:
	@echo "🚀 Running 1K transaction load test..."
	cd tests/performance && python load_test.py --transactions=1000 --concurrent=10

load-test-10k:
	@echo "🚀 Running 10K transaction load test..."
	cd tests/performance && python load_test.py --transactions=10000 --concurrent=50

load-test-100k:
	@echo "🚀 Running 100K transaction load test..."
	cd tests/performance && python load_test.py --transactions=100000 --concurrent=100

stress-test:
	@echo "🚀 Running stress test..."
	cd tests/performance && python stress_test.py --duration=300 --max-tps=1000

benchmark:
	@echo "🚀 Running benchmark tests..."
	cd tests/performance && python benchmark.py

# Development Commands
dev-setup:
	@echo "🛠️ Setting up development environment..."
	make build-all
	make start-infra
	make wait-for-infra
	make setup-participants
	make setup-collateral
	make load-test-data

dev-reset: stop-all reset-db dev-setup

# Chaos Engineering Commands
chaos-test-network:
	@echo "🌪️ Testing network partition resilience..."
	cd tests/chaos && python network_partition_test.py

chaos-test-service:
	@echo "🌪️ Testing service failure resilience..."
	cd tests/chaos && python service_failure_test.py

chaos-test-db:
	@echo "🌪️ Testing database failure resilience..."
	cd tests/chaos && python database_failure_test.py

# Compliance Commands
compliance-check:
	@echo "📋 Running compliance checks..."
	cd tests/compliance && python basel_iii_test.py
	cd tests/compliance && python pfmi_test.py
	cd tests/compliance && python regulatory_reporting_test.py

audit-trail:
	@echo "📋 Generating audit trail..."
	curl -X GET http://localhost:8466/api/v1/audit/trail \
		-H "Authorization: Bearer settlement_token" \
		-G -d "start_date=$(shell date -d '-1 day' '+%Y-%m-%d')" \
		-d "end_date=$(shell date '+%Y-%m-%d')"

# Documentation Commands
docs:
	@echo "📚 Generating documentation..."
	cd docs && make html

api-docs:
	@echo "📚 Generating API documentation..."
	swagger-codegen generate -i api/openapi.yaml -l html2 -o docs/api

# Docker Commands
docker-build:
	@echo "🐳 Building Docker images..."
	docker-compose build

docker-push:
	@echo "🐳 Pushing Docker images..."
	docker-compose push

docker-pull:
	@echo "🐳 Pulling Docker images..."
	docker-compose pull

# Utility Commands
check-ports:
	@echo "🔍 Checking port availability..."
	@echo "PostgreSQL (5437):" && (nc -z localhost 5437 && echo "✅ Available" || echo "❌ Not available")
	@echo "Redis (6383):" && (nc -z localhost 6383 && echo "✅ Available" || echo "❌ Not available")
	@echo "Kafka (9096):" && (nc -z localhost 9096 && echo "✅ Available" || echo "❌ Not available")
	@echo "Transaction Collector (8461):" && (nc -z localhost 8461 && echo "✅ Available" || echo "❌ Not available")
	@echo "Netting Engine (8462):" && (nc -z localhost 8462 && echo "✅ Available" || echo "❌ Not available")
	@echo "Settlement Processor (8463):" && (nc -z localhost 8463 && echo "✅ Available" || echo "❌ Not available")

show-config:
	@echo "⚙️ Current configuration:"
	@echo "Database URL: postgres://settlement_user:***@localhost:5437/settlement_engine"
	@echo "Redis URL: redis://localhost:6383"
	@echo "Kafka Brokers: localhost:9096"
	@echo "Grafana: http://localhost:3004"
	@echo "Prometheus: http://localhost:9094"
	@echo "Jaeger: http://localhost:16690"

version:
	@echo "Clearing & Settlement Engine v1.0.0"
	@echo "Built with:"
	@echo "  Go: $(shell go version 2>/dev/null || echo 'Not installed')"
	@echo "  Java: $(shell java -version 2>&1 | head -n 1 || echo 'Not installed')"
	@echo "  Python: $(shell python3 --version 2>/dev/null || echo 'Not installed')"
	@echo "  Docker: $(shell docker --version 2>/dev/null || echo 'Not installed')"
