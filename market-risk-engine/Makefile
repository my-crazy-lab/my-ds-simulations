# Market Risk Engine Makefile
# Comprehensive build, test, and deployment automation

.PHONY: help build test deploy clean setup-gpu

# Default target
help:
	@echo "Market Risk Engine - Available Commands:"
	@echo ""
	@echo "🏗️  BUILD COMMANDS"
	@echo "  build-all              Build all services and containers"
	@echo "  build-pnl              Build P&L calculator service"
	@echo "  build-var              Build VaR engine service"
	@echo "  build-greeks           Build Greeks calculator service"
	@echo "  build-position         Build position manager service"
	@echo "  build-risk-monitor     Build risk monitor service"
	@echo "  build-margin           Build margin calculator service"
	@echo "  build-stress           Build stress tester service"
	@echo "  build-reporting        Build reporting service"
	@echo ""
	@echo "🚀 DEPLOYMENT COMMANDS"
	@echo "  start-all              Start all services"
	@echo "  stop-all               Stop all services"
	@echo "  restart-all            Restart all services"
	@echo "  start-infrastructure   Start infrastructure services only"
	@echo "  start-services         Start application services only"
	@echo "  logs                   View all service logs"
	@echo "  logs-follow            Follow all service logs"
	@echo ""
	@echo "🧪 TESTING COMMANDS"
	@echo "  test-all               Run all tests"
	@echo "  test-pnl               Run P&L calculation tests"
	@echo "  test-var               Run VaR model tests"
	@echo "  test-greeks            Run Greeks calculation tests"
	@echo "  test-gpu               Run GPU performance tests"
	@echo "  test-limits            Run risk limits tests"
	@echo "  test-integration       Run integration tests"
	@echo "  test-performance       Run performance tests"
	@echo "  test-accuracy          Run accuracy validation tests"
	@echo ""
	@echo "⚙️  SETUP COMMANDS"
	@echo "  setup-gpu              Setup GPU environment"
	@echo "  setup-models           Setup risk models"
	@echo "  setup-data             Load test data"
	@echo "  setup-monitoring       Setup monitoring dashboards"
	@echo "  health-check           Check system health"
	@echo ""
	@echo "📊 MONITORING COMMANDS"
	@echo "  view-dashboard         Open risk dashboard"
	@echo "  view-metrics           Open performance metrics"
	@echo "  view-analytics         Open risk analytics"
	@echo "  generate-report        Generate risk report"
	@echo ""
	@echo "🔧 UTILITY COMMANDS"
	@echo "  clean                  Clean build artifacts"
	@echo "  reset-data             Reset all data"
	@echo "  backup-data            Backup risk data"
	@echo "  restore-data           Restore risk data"

# Build Commands
build-all: build-pnl build-var build-greeks build-position build-risk-monitor build-margin build-stress build-reporting
	@echo "✅ All services built successfully"

build-pnl:
	@echo "🏗️ Building P&L Calculator service..."
	cd services/pnl-calculator && docker build -f Dockerfile.cuda -t market-risk/pnl-calculator:latest .

build-var:
	@echo "🏗️ Building VaR Engine service..."
	cd services/var-engine && docker build -f Dockerfile.cuda -t market-risk/var-engine:latest .

build-greeks:
	@echo "🏗️ Building Greeks Calculator service..."
	cd services/greeks-calculator && docker build -f Dockerfile.cuda -t market-risk/greeks-calculator:latest .

build-position:
	@echo "🏗️ Building Position Manager service..."
	cd services/position-manager && docker build -t market-risk/position-manager:latest .

build-risk-monitor:
	@echo "🏗️ Building Risk Monitor service..."
	cd services/risk-monitor && docker build -t market-risk/risk-monitor:latest .

build-margin:
	@echo "🏗️ Building Margin Calculator service..."
	cd services/margin-calculator && docker build -t market-risk/margin-calculator:latest .

build-stress:
	@echo "🏗️ Building Stress Tester service..."
	cd services/stress-tester && docker build -t market-risk/stress-tester:latest .

build-reporting:
	@echo "🏗️ Building Reporting Service..."
	cd services/reporting-service && docker build -t market-risk/reporting-service:latest .

# Deployment Commands
start-all: start-infrastructure start-services
	@echo "🚀 All services started successfully"

start-infrastructure:
	@echo "🚀 Starting infrastructure services..."
	docker-compose up -d postgres redis influxdb zookeeper kafka schema-registry prometheus grafana jaeger
	@echo "⏳ Waiting for infrastructure to be ready..."
	./scripts/wait-for-services.sh

start-services:
	@echo "🚀 Starting application services..."
	docker-compose up -d pnl-calculator var-engine greeks-calculator position-manager risk-monitor margin-calculator stress-tester reporting-service

stop-all:
	@echo "🛑 Stopping all services..."
	docker-compose down

restart-all: stop-all start-all

logs:
	docker-compose logs --tail=100

logs-follow:
	docker-compose logs -f

# Testing Commands
test-all: test-pnl test-var test-greeks test-gpu test-limits test-integration
	@echo "✅ All tests completed"

test-pnl:
	@echo "🧪 Running P&L calculation tests..."
	python -m pytest tests/pnl/ -v --tb=short
	python tests/pnl/test_pnl_accuracy.py

test-var:
	@echo "🧪 Running VaR model tests..."
	python -m pytest tests/var/ -v --tb=short
	python tests/var/test_var_models.py

test-greeks:
	@echo "🧪 Running Greeks calculation tests..."
	python -m pytest tests/greeks/ -v --tb=short
	python tests/greeks/test_greeks_accuracy.py

test-gpu:
	@echo "🧪 Running GPU performance tests..."
	python -m pytest tests/gpu/ -v --tb=short
	python tests/gpu/test_gpu_performance.py

test-limits:
	@echo "🧪 Running risk limits tests..."
	python -m pytest tests/limits/ -v --tb=short
	python tests/limits/test_limit_monitoring.py

test-integration:
	@echo "🧪 Running integration tests..."
	python -m pytest tests/integration/ -v --tb=short

test-performance:
	@echo "🧪 Running performance tests..."
	python tests/performance/test_system_performance.py

test-accuracy:
	@echo "🧪 Running accuracy validation tests..."
	python tests/accuracy/test_model_accuracy.py

# Setup Commands
setup-gpu:
	@echo "⚙️ Setting up GPU environment..."
	./scripts/setup-gpu-environment.sh

setup-models:
	@echo "⚙️ Setting up risk models..."
	./scripts/setup-risk-models.sh

setup-data:
	@echo "⚙️ Loading test data..."
	./scripts/load-test-data.sh

setup-monitoring:
	@echo "⚙️ Setting up monitoring dashboards..."
	./scripts/setup-monitoring.sh

health-check:
	@echo "🏥 Checking system health..."
	./scripts/health-check.sh

# Monitoring Commands
view-dashboard:
	@echo "📊 Opening risk dashboard..."
	open http://localhost:3007

view-metrics:
	@echo "📊 Opening performance metrics..."
	open http://localhost:9096

view-analytics:
	@echo "📊 Opening risk analytics..."
	open http://localhost:8498

generate-report:
	@echo "📊 Generating risk report..."
	curl -X POST http://localhost:8498/api/v1/reports/generate \
		-H "Content-Type: application/json" \
		-d '{"report_type": "daily_risk", "portfolio_ids": ["ALL"]}'

# Risk Operations Commands
run-pnl-calculation:
	@echo "💰 Running P&L calculation..."
	curl -X POST http://localhost:8491/api/v1/pnl/$(PORTFOLIO_ID) \
		-H "Content-Type: application/json"

run-var-calculation:
	@echo "📈 Running VaR calculation..."
	curl -X POST http://localhost:8492/api/v1/var/calculate \
		-H "Content-Type: application/json" \
		-d '{"portfolio_id": "$(PORTFOLIO_ID)", "confidence_level": 0.95, "method": "MONTE_CARLO"}'

run-stress-test:
	@echo "⚡ Running stress test..."
	curl -X POST http://localhost:8497/api/v1/stress-test \
		-H "Content-Type: application/json" \
		-d '{"portfolio_id": "$(PORTFOLIO_ID)", "scenario": "MARKET_CRASH_2008"}'

check-risk-limits:
	@echo "🚨 Checking risk limits..."
	curl http://localhost:8495/api/v1/limits/$(PORTFOLIO_ID)/status

calculate-margin:
	@echo "💳 Calculating margin requirements..."
	curl -X POST http://localhost:8496/api/v1/margin/calculate \
		-H "Content-Type: application/json" \
		-d '{"portfolio_id": "$(PORTFOLIO_ID)"}'

# Data Management Commands
load-market-data:
	@echo "📊 Loading market data..."
	python scripts/load_market_data.py --source $(DATA_SOURCE) --date $(DATE)

load-positions:
	@echo "📊 Loading positions..."
	python scripts/load_positions.py --file $(POSITIONS_FILE)

generate-test-positions:
	@echo "📊 Generating test positions..."
	python scripts/generate_test_positions.py --count $(COUNT) --portfolio $(PORTFOLIO_ID)

# Performance Optimization Commands
optimize-gpu-kernels:
	@echo "🚀 Optimizing GPU kernels..."
	cd gpu-kernels && make optimize

benchmark-performance:
	@echo "🏃 Running performance benchmarks..."
	python scripts/benchmark_performance.py

profile-memory:
	@echo "🧠 Profiling memory usage..."
	python scripts/profile_memory.py

# Utility Commands
clean:
	@echo "🧹 Cleaning build artifacts..."
	docker system prune -f
	docker volume prune -f
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete

reset-data:
	@echo "🔄 Resetting all data..."
	docker-compose down -v
	docker volume rm $(shell docker volume ls -q | grep market-risk) 2>/dev/null || true

backup-data:
	@echo "💾 Backing up risk data..."
	./scripts/backup-data.sh

restore-data:
	@echo "📥 Restoring risk data..."
	./scripts/restore-data.sh $(BACKUP_FILE)

# Development Commands
dev-setup:
	@echo "🛠️ Setting up development environment..."
	pip install -r requirements-dev.txt
	pre-commit install

dev-test:
	@echo "🧪 Running development tests..."
	python -m pytest tests/ -v --cov=services --cov-report=html

dev-lint:
	@echo "🔍 Running code linting..."
	flake8 services/ tests/
	black --check services/ tests/
	isort --check-only services/ tests/

dev-format:
	@echo "✨ Formatting code..."
	black services/ tests/
	isort services/ tests/

# Security Commands
security-scan:
	@echo "🔒 Running security scan..."
	bandit -r services/
	safety check

vulnerability-check:
	@echo "🛡️ Checking for vulnerabilities..."
	docker run --rm -v $(PWD):/app clair-scanner:latest

# Documentation Commands
generate-docs:
	@echo "📚 Generating documentation..."
	cd docs && make html

serve-docs:
	@echo "📚 Serving documentation..."
	cd docs/_build/html && python -m http.server 8000

# Kubernetes Commands (if using K8s)
k8s-deploy:
	@echo "☸️ Deploying to Kubernetes..."
	kubectl apply -f k8s/

k8s-delete:
	@echo "☸️ Deleting from Kubernetes..."
	kubectl delete -f k8s/

k8s-status:
	@echo "☸️ Checking Kubernetes status..."
	kubectl get pods -l app=market-risk-engine

# Environment-specific Commands
deploy-dev: build-all
	@echo "🚀 Deploying to development..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

deploy-staging: build-all
	@echo "🚀 Deploying to staging..."
	docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d

deploy-prod: build-all
	@echo "🚀 Deploying to production..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Quick Start Commands
quick-start: setup-gpu start-infrastructure setup-models setup-data start-services health-check
	@echo "🎉 Market Risk Engine is ready!"
	@echo "📊 Dashboard: http://localhost:3007"
	@echo "📈 Metrics: http://localhost:9096"
	@echo "🔍 Analytics: http://localhost:8498"

demo: quick-start generate-test-positions
	@echo "🎭 Running demo..."
	$(MAKE) run-pnl-calculation PORTFOLIO_ID=DEMO_PORTFOLIO
	$(MAKE) run-var-calculation PORTFOLIO_ID=DEMO_PORTFOLIO
	$(MAKE) run-stress-test PORTFOLIO_ID=DEMO_PORTFOLIO
	@echo "✅ Demo completed successfully!"

# Variables for parameterized commands
PORTFOLIO_ID ?= DEFAULT_PORTFOLIO
DATA_SOURCE ?= bloomberg
DATE ?= $(shell date +%Y-%m-%d)
POSITIONS_FILE ?= data/positions.csv
COUNT ?= 1000
BACKUP_FILE ?= backup.sql
