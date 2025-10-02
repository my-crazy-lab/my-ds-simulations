#!/bin/bash

set -e

# Microservices Saga Deployment Script
# Supports Docker Compose and Kubernetes deployments

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_TYPE="${1:-docker-compose}"
ENVIRONMENT="${2:-development}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        command -v docker >/dev/null 2>&1 || error "Docker is required but not installed"
        command -v docker-compose >/dev/null 2>&1 || error "Docker Compose is required but not installed"
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        command -v kubectl >/dev/null 2>&1 || error "kubectl is required but not installed"
        command -v helm >/dev/null 2>&1 || error "Helm is required but not installed"
    fi
    
    command -v go >/dev/null 2>&1 || error "Go is required but not installed"
    
    log "Prerequisites check passed"
}

# Build services
build_services() {
    log "Building services..."
    
    cd "$PROJECT_ROOT"
    
    # Build saga orchestrator
    info "Building saga orchestrator..."
    cd services/saga-orchestrator
    CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o saga-orchestrator ./main.go
    docker build -t microservices-saga/saga-orchestrator:latest .
    cd "$PROJECT_ROOT"
    
    # Build inventory service
    info "Building inventory service..."
    cd services/inventory-service
    CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o inventory-service ./main.go
    docker build -t microservices-saga/inventory-service:latest .
    cd "$PROJECT_ROOT"
    
    # Build payment service
    info "Building payment service..."
    cd services/payment-service
    CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o payment-service ./main.go
    docker build -t microservices-saga/payment-service:latest .
    cd "$PROJECT_ROOT"
    
    # Build notification service
    info "Building notification service..."
    cd services/notification-service
    CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o notification-service ./main.go
    docker build -t microservices-saga/notification-service:latest .
    cd "$PROJECT_ROOT"
    
    log "Services built successfully"
}

# Deploy with Docker Compose
deploy_docker_compose() {
    log "Deploying with Docker Compose..."
    
    cd "$PROJECT_ROOT"
    
    # Stop existing containers
    info "Stopping existing containers..."
    docker-compose -f infrastructure/docker-compose.yml down --remove-orphans
    
    # Start infrastructure services first
    info "Starting infrastructure services..."
    docker-compose -f infrastructure/docker-compose.yml up -d postgres redis kafka zookeeper schema-registry
    
    # Wait for services to be ready
    info "Waiting for infrastructure services to be ready..."
    sleep 30
    
    # Register Avro schemas
    info "Registering Avro schemas..."
    bash scripts/register_schemas.sh
    
    # Start application services
    info "Starting application services..."
    docker-compose -f infrastructure/docker-compose.yml up -d
    
    # Wait for services to be healthy
    info "Waiting for services to be healthy..."
    sleep 60
    
    # Run health checks
    check_service_health
    
    log "Docker Compose deployment completed"
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log "Deploying to Kubernetes..."
    
    cd "$PROJECT_ROOT"
    
    # Create namespace
    info "Creating namespace..."
    kubectl apply -f infrastructure/k8s/namespace.yaml
    
    # Deploy infrastructure
    info "Deploying infrastructure..."
    kubectl apply -f infrastructure/k8s/postgres.yaml
    kubectl apply -f infrastructure/k8s/redis.yaml
    kubectl apply -f infrastructure/k8s/kafka.yaml
    
    # Wait for infrastructure
    info "Waiting for infrastructure to be ready..."
    kubectl wait --for=condition=ready pod -l app=postgres -n microservices --timeout=300s
    kubectl wait --for=condition=ready pod -l app=redis -n microservices --timeout=300s
    kubectl wait --for=condition=ready pod -l app=kafka -n microservices --timeout=300s
    
    # Deploy application services
    info "Deploying application services..."
    kubectl apply -f infrastructure/k8s/saga-orchestrator.yaml
    kubectl apply -f infrastructure/k8s/inventory-service.yaml
    kubectl apply -f infrastructure/k8s/payment-service.yaml
    kubectl apply -f infrastructure/k8s/notification-service.yaml
    
    # Deploy monitoring
    info "Deploying monitoring..."
    kubectl apply -f infrastructure/k8s/prometheus.yaml
    kubectl apply -f infrastructure/k8s/grafana.yaml
    kubectl apply -f infrastructure/k8s/jaeger.yaml
    
    # Wait for services
    info "Waiting for services to be ready..."
    kubectl wait --for=condition=ready pod -l app=saga-orchestrator -n microservices --timeout=300s
    kubectl wait --for=condition=ready pod -l app=inventory-service -n microservices --timeout=300s
    kubectl wait --for=condition=ready pod -l app=payment-service -n microservices --timeout=300s
    kubectl wait --for=condition=ready pod -l app=notification-service -n microservices --timeout=300s
    
    # Setup ingress
    info "Setting up ingress..."
    kubectl apply -f infrastructure/k8s/ingress.yaml
    
    log "Kubernetes deployment completed"
}

# Check service health
check_service_health() {
    log "Checking service health..."
    
    services=(
        "http://localhost:8080/health:saga-orchestrator"
        "http://localhost:8081/health:inventory-service"
        "http://localhost:8082/health:payment-service"
        "http://localhost:8083/health:notification-service"
    )
    
    for service in "${services[@]}"; do
        IFS=':' read -r url name <<< "$service"
        info "Checking $name..."
        
        for i in {1..30}; do
            if curl -f -s "$url" > /dev/null; then
                log "$name is healthy"
                break
            fi
            
            if [ $i -eq 30 ]; then
                error "$name failed health check"
            fi
            
            sleep 2
        done
    done
}

# Setup monitoring
setup_monitoring() {
    log "Setting up monitoring..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        info "Grafana available at: http://localhost:3000 (admin/admin)"
        info "Prometheus available at: http://localhost:9090"
        info "Jaeger available at: http://localhost:16686"
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        info "Setting up port forwards for monitoring..."
        kubectl port-forward -n microservices svc/grafana 3000:3000 &
        kubectl port-forward -n microservices svc/prometheus 9090:9090 &
        kubectl port-forward -n microservices svc/jaeger 16686:16686 &
        
        info "Grafana available at: http://localhost:3000"
        info "Prometheus available at: http://localhost:9090"
        info "Jaeger available at: http://localhost:16686"
    fi
}

# Seed test data
seed_test_data() {
    log "Seeding test data..."
    bash "$SCRIPT_DIR/seed_data.sh"
}

# Run smoke tests
run_smoke_tests() {
    log "Running smoke tests..."
    
    # Test saga creation
    info "Testing saga creation..."
    response=$(curl -s -X POST http://localhost:8080/api/v1/sagas \
        -H "Content-Type: application/json" \
        -d '{
            "saga_type": "order-processing",
            "saga_data": {
                "order_id": "test-order-001",
                "user_id": "test-user",
                "items": [{"sku": "LAPTOP-001", "quantity": 1, "price": 1299.99}],
                "total_amount": 1299.99
            }
        }')
    
    saga_id=$(echo "$response" | jq -r '.id')
    
    if [[ "$saga_id" != "null" && "$saga_id" != "" ]]; then
        log "Smoke test passed - Saga created: $saga_id"
    else
        error "Smoke test failed - Could not create saga"
    fi
    
    # Wait and check saga status
    sleep 10
    status_response=$(curl -s "http://localhost:8080/api/v1/sagas/$saga_id")
    saga_status=$(echo "$status_response" | jq -r '.status')
    
    info "Saga status: $saga_status"
}

# Cleanup
cleanup() {
    log "Cleaning up..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        docker-compose -f infrastructure/docker-compose.yml down --remove-orphans
        docker system prune -f
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl delete namespace microservices --ignore-not-found=true
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [deployment-type] [environment]"
    echo ""
    echo "Deployment types:"
    echo "  docker-compose  Deploy using Docker Compose (default)"
    echo "  kubernetes      Deploy to Kubernetes cluster"
    echo "  cleanup         Clean up deployment"
    echo ""
    echo "Environments:"
    echo "  development     Development environment (default)"
    echo "  staging         Staging environment"
    echo "  production      Production environment"
    echo ""
    echo "Examples:"
    echo "  $0                           # Deploy with Docker Compose in development"
    echo "  $0 kubernetes production     # Deploy to Kubernetes in production"
    echo "  $0 cleanup                   # Clean up deployment"
}

# Main execution
main() {
    case "$DEPLOYMENT_TYPE" in
        "docker-compose")
            check_prerequisites
            build_services
            deploy_docker_compose
            setup_monitoring
            seed_test_data
            run_smoke_tests
            ;;
        "kubernetes")
            check_prerequisites
            build_services
            deploy_kubernetes
            setup_monitoring
            seed_test_data
            run_smoke_tests
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        *)
            error "Unknown deployment type: $DEPLOYMENT_TYPE"
            show_usage
            ;;
    esac
}

# Trap cleanup on exit
trap cleanup EXIT

main "$@"
