# Cross-System Integration Platform - Quick Start Guide

## 🚀 Getting Started in 15 Minutes

This guide will help you get the Cross-System Integration Platform up and running quickly on your local machine.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Docker & Docker Compose** (v20.10+)
- **Python 3.9+** with pip
- **Go 1.19+** (for building Go services)
- **Node.js 18+** with npm (for load testing)
- **Git** for cloning the repository

## Step 1: Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd cross-system-integration

# Make scripts executable
chmod +x scripts/setup/*.sh
chmod +x scripts/deployment/*.sh
chmod +x scripts/testing/*.sh

# Install all dependencies
./scripts/setup/install-dependencies.sh
```

This script will:
- Install Docker, Go, Python, and Node.js (if not already installed)
- Set up Python virtual environment
- Install all required packages
- Create necessary directories
- Set up environment configuration

## Step 2: Start Infrastructure Services

```bash
# Start infrastructure services (Redis, Kafka, Prometheus, Grafana)
docker-compose up -d redis kafka zookeeper prometheus grafana jaeger mlflow

# Wait for services to be ready (this may take 2-3 minutes)
./scripts/setup/wait-for-services.sh
```

Verify infrastructure is running:
```bash
# Check service status
docker-compose ps

# Test connectivity
curl http://localhost:9090  # Prometheus
curl http://localhost:3000  # Grafana
redis-cli ping              # Redis
```

## Step 3: Deploy Core Services

Choose one of the deployment methods:

### Option A: Local Development (Recommended for testing)
```bash
# Deploy all services locally
./scripts/deployment/deploy-all-services.sh local
```

### Option B: Docker Deployment (Recommended for production-like testing)
```bash
# Deploy with Docker Compose
./scripts/deployment/deploy-all-services.sh docker
```

The deployment script will:
- Build all services
- Start services in the correct order
- Perform health checks
- Display access information

## Step 4: Verify Installation

### Health Checks
```bash
# Check all service health
curl http://localhost:8090/health  # Event Bus
curl http://localhost:8091/health  # Intelligent Orchestrator
curl http://localhost:8092/health  # ChatOps Engine
```

### Quick Functionality Test
```bash
# Test ChatOps interface
curl -X POST http://localhost:8092/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "quickstart",
    "user_id": "demo",
    "message": "what is the system status?"
  }'
```

Expected response:
```json
{
  "intent": "system_status",
  "response": "🔍 **System Status Report**\n\nOverall Health: 3/3 services healthy...",
  "processing_time": 0.234
}
```

## Step 5: Explore Key Features

### 1. Intelligent Saga Orchestration

Start a saga with ML-powered optimization:
```bash
curl -X POST http://localhost:8091/api/v1/sagas/start \
  -H "Content-Type: application/json" \
  -d '{
    "saga_id": "payment_saga",
    "correlation_id": "demo_payment_001",
    "context": {
      "user_id": "demo_user",
      "amount": 150.0,
      "system_load": 0.3
    }
  }'
```

Response includes ML prediction:
```json
{
  "execution_id": "exec_1234567890_demo_payment_001",
  "saga_id": "payment_saga",
  "status": "pending",
  "ml_prediction": {
    "failure_probability": 0.15,
    "risk_level": "low",
    "confidence": 0.87,
    "recommendations": ["Monitor system load", "Implement health checks"]
  }
}
```

### 2. Natural Language Operations

Try different ChatOps commands:

```bash
# System status
curl -X POST http://localhost:8092/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","user_id":"user","message":"system status"}'

# Saga management
curl -X POST http://localhost:8092/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","user_id":"user","message":"show saga status"}'

# Troubleshooting
curl -X POST http://localhost:8092/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","user_id":"user","message":"help troubleshoot saga failures"}'

# Start operations
curl -X POST http://localhost:8092/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","user_id":"user","message":"start saga payment_saga"}'
```

### 3. Event Bus Operations

Publish and query events:

```bash
# Publish an event
curl -X POST http://localhost:8090/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "type": "saga.started",
    "source": "microservices",
    "data": {
      "saga_id": "payment_saga",
      "user_id": "demo_user",
      "amount": 100.0
    },
    "metadata": {
      "priority": "normal",
      "tags": ["demo", "payment"]
    }
  }'

# Query recent events
curl "http://localhost:8090/api/v1/events?limit=10"
```

## Step 6: Access Monitoring Dashboards

### Prometheus (Metrics)
- URL: http://localhost:9090
- Query examples:
  - `event_bus_events_received_total` - Event processing metrics
  - `intelligent_orchestrator_saga_executions_total` - Saga metrics
  - `chatops_engine_queries_total` - ChatOps usage metrics

### Grafana (Visualization)
- URL: http://localhost:3000
- Username: `admin`
- Password: `admin123`
- Pre-configured dashboards for all services

### Jaeger (Tracing)
- URL: http://localhost:16686
- View distributed traces across services

### MLflow (ML Experiments)
- URL: http://localhost:5000
- View ML model experiments and metrics

## Step 7: Run Tests

### Unit Tests
```bash
# Run all unit tests
./scripts/testing/run-all-tests.sh --unit-only

# Run specific service tests
cd services/intelligent-orchestrator
python -m pytest tests/ -v
```

### Integration Tests
```bash
# Run integration tests
./scripts/testing/run-all-tests.sh --integration-only

# Or run directly
python -m pytest tests/integration/ -v -s
```

### Load Tests
```bash
# Run load tests with k6
./scripts/testing/run-all-tests.sh --load-only

# Or run directly
k6 run tests/load/cross-system-load-test.js
```

## Common Use Cases

### Use Case 1: Automated Payment Processing

1. **Start Payment Saga via ChatOps**:
   ```
   Message: "start saga payment_saga for user123 amount 250"
   ```

2. **Monitor Progress**:
   ```
   Message: "show saga status"
   ```

3. **Troubleshoot Issues**:
   ```
   Message: "why did payment saga fail?"
   ```

### Use Case 2: System Health Monitoring

1. **Check Overall Health**:
   ```
   Message: "what is the system status?"
   ```

2. **Get Performance Metrics**:
   ```
   Message: "show metrics for last 1 hour"
   ```

3. **Investigate Issues**:
   ```
   Message: "troubleshoot high error rates"
   ```

### Use Case 3: Predictive Operations

1. **View ML Predictions**:
   - Start a saga and observe the ML prediction in the response
   - Check how the system automatically adjusts timeouts and retries

2. **Monitor Model Performance**:
   - Visit MLflow dashboard to see model accuracy
   - View feature importance and prediction confidence

## Troubleshooting

### Common Issues

1. **Services not starting**:
   ```bash
   # Check logs
   docker-compose logs <service-name>
   
   # For local deployment
   tail -f logs/<service-name>.log
   ```

2. **Port conflicts**:
   ```bash
   # Check what's using the ports
   lsof -i :8090  # Event Bus
   lsof -i :8091  # Orchestrator
   lsof -i :8092  # ChatOps
   ```

3. **Python dependencies**:
   ```bash
   # Recreate virtual environment
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r services/intelligent-orchestrator/requirements.txt
   pip install -r services/chatops-engine/requirements.txt
   ```

4. **Go build issues**:
   ```bash
   cd services/event-bus
   go mod tidy
   go mod download
   go build -o ../../bin/event-bus ./main.go
   ```

### Getting Help

1. **Check service logs**:
   ```bash
   # Docker deployment
   docker-compose logs -f <service-name>
   
   # Local deployment
   tail -f logs/<service-name>.log
   ```

2. **Health check endpoints**:
   ```bash
   curl http://localhost:8090/health
   curl http://localhost:8091/health
   curl http://localhost:8092/health
   ```

3. **Verify infrastructure**:
   ```bash
   redis-cli ping
   docker-compose ps
   ```

## Next Steps

1. **Explore Advanced Features**:
   - Read the [Architecture Guide](../architecture/SYSTEM_DESIGN.md)
   - Try the [ChatOps Tutorial](CHATOPS_TUTORIAL.md)
   - Review [Integration Examples](INTEGRATION_EXAMPLES.md)

2. **Customize for Your Use Case**:
   - Modify saga definitions in the orchestrator
   - Add custom routing rules to the event bus
   - Extend the ChatOps knowledge base

3. **Deploy to Production**:
   - Review the [Deployment Guide](../deployment/DEPLOYMENT_GUIDE.md)
   - Set up monitoring and alerting
   - Configure security and authentication

## Support

- **Documentation**: Check the `docs/` directory for detailed guides
- **Issues**: Report bugs and feature requests in the project repository
- **Community**: Join our community discussions

---

🎉 **Congratulations!** You now have a fully functional Cross-System Integration Platform running locally. The system demonstrates intelligent saga orchestration, natural language operations, and comprehensive monitoring capabilities.
