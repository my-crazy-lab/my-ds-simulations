#!/bin/bash

# Cross-System Integration - Service Deployment Script
# This script deploys all services in the correct order with health checks

set -e  # Exit on any error

echo "🚀 Cross-System Integration - Deploying All Services"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOYMENT_MODE="${1:-local}"  # local, docker, or kubernetes

# Service configuration
declare -A SERVICES=(
    ["event-bus"]="8090"
    ["intelligent-orchestrator"]="8091"
    ["chatops-engine"]="8092"
    ["predictive-scaler"]="8093"
    ["data-quality-engine"]="8094"
    ["maintenance-controller"]="8095"
)

# Infrastructure services
declare -A INFRASTRUCTURE=(
    ["redis"]="6379"
    ["kafka"]="9092"
    ["prometheus"]="9090"
    ["grafana"]="3000"
    ["mlflow"]="5000"
)

# Health check function
check_service_health() {
    local service_name=$1
    local port=$2
    local max_attempts=${3:-30}
    local attempt=1
    
    print_status "Checking health of $service_name on port $port..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
            print_status "✅ $service_name is healthy"
            return 0
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            print_error "❌ $service_name failed to become healthy after $max_attempts attempts"
            return 1
        fi
        
        echo -n "."
        sleep 2
        ((attempt++))
    done
}

# Wait for infrastructure services
wait_for_infrastructure() {
    print_header "Waiting for Infrastructure Services"
    
    for service in "${!INFRASTRUCTURE[@]}"; do
        port=${INFRASTRUCTURE[$service]}
        
        case $service in
            "redis")
                print_status "Checking Redis on port $port..."
                while ! redis-cli -p $port ping > /dev/null 2>&1; do
                    echo -n "."
                    sleep 2
                done
                print_status "✅ Redis is ready"
                ;;
            "kafka")
                print_status "Checking Kafka on port $port..."
                # Simple port check for Kafka
                while ! nc -z localhost $port > /dev/null 2>&1; do
                    echo -n "."
                    sleep 2
                done
                print_status "✅ Kafka is ready"
                ;;
            *)
                # Generic HTTP health check
                while ! curl -s -f "http://localhost:$port" > /dev/null 2>&1; do
                    echo -n "."
                    sleep 2
                done
                print_status "✅ $service is ready"
                ;;
        esac
    done
}

# Deploy infrastructure
deploy_infrastructure() {
    print_header "Deploying Infrastructure Services"
    
    cd "$PROJECT_ROOT"
    
    print_status "Starting infrastructure with Docker Compose..."
    docker-compose up -d redis kafka zookeeper prometheus grafana jaeger mlflow
    
    print_status "Waiting for infrastructure services to be ready..."
    wait_for_infrastructure
    
    print_status "✅ All infrastructure services are running"
}

# Build Go services
build_go_services() {
    print_header "Building Go Services"
    
    cd "$PROJECT_ROOT"
    
    # Build event-bus
    if [ -d "services/event-bus" ]; then
        print_status "Building event-bus..."
        cd services/event-bus
        go mod tidy
        go build -o ../../bin/event-bus ./main.go
        cd ../..
        print_status "✅ event-bus built successfully"
    fi
}

# Deploy services locally
deploy_local() {
    print_header "Deploying Services Locally"
    
    cd "$PROJECT_ROOT"
    
    # Create bin directory
    mkdir -p bin logs
    
    # Build Go services
    build_go_services
    
    # Activate Python virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
        print_status "Activated Python virtual environment"
    else
        print_warning "Python virtual environment not found. Creating one..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r services/intelligent-orchestrator/requirements.txt
        pip install -r services/chatops-engine/requirements.txt
    fi
    
    # Start services in background
    print_status "Starting services..."
    
    # Start event-bus
    if [ -f "bin/event-bus" ]; then
        print_status "Starting event-bus on port 8090..."
        nohup ./bin/event-bus > logs/event-bus.log 2>&1 &
        echo $! > logs/event-bus.pid
    fi
    
    # Start intelligent-orchestrator
    if [ -d "services/intelligent-orchestrator" ]; then
        print_status "Starting intelligent-orchestrator on port 8091..."
        cd services/intelligent-orchestrator
        nohup python main.py > ../../logs/intelligent-orchestrator.log 2>&1 &
        echo $! > ../../logs/intelligent-orchestrator.pid
        cd ../..
    fi
    
    # Start chatops-engine
    if [ -d "services/chatops-engine" ]; then
        print_status "Starting chatops-engine on port 8092..."
        cd services/chatops-engine
        nohup python main.py > ../../logs/chatops-engine.log 2>&1 &
        echo $! > ../../logs/chatops-engine.pid
        cd ../..
    fi
    
    # Wait for services to start
    sleep 10
    
    # Health check all services
    print_header "Performing Health Checks"
    
    for service in "${!SERVICES[@]}"; do
        port=${SERVICES[$service]}
        if ! check_service_health "$service" "$port" 15; then
            print_error "Service $service failed health check"
            return 1
        fi
    done
    
    print_status "✅ All services deployed and healthy"
}

# Deploy with Docker
deploy_docker() {
    print_header "Deploying Services with Docker"
    
    cd "$PROJECT_ROOT"
    
    print_status "Building and starting all services with Docker Compose..."
    docker-compose up -d --build
    
    print_status "Waiting for services to be ready..."
    sleep 30
    
    # Health check all services
    print_header "Performing Health Checks"
    
    for service in "${!SERVICES[@]}"; do
        port=${SERVICES[$service]}
        if ! check_service_health "$service" "$port" 20; then
            print_error "Service $service failed health check"
            # Show logs for debugging
            print_status "Showing logs for $service:"
            docker-compose logs --tail=50 "$service"
            return 1
        fi
    done
    
    print_status "✅ All services deployed and healthy"
}

# Deploy to Kubernetes
deploy_kubernetes() {
    print_header "Deploying Services to Kubernetes"
    
    # Check if kubectl is available
    if ! command -v kubectl > /dev/null 2>&1; then
        print_error "kubectl is not installed. Please install kubectl first."
        return 1
    fi
    
    # Check if cluster is accessible
    if ! kubectl cluster-info > /dev/null 2>&1; then
        print_error "Cannot access Kubernetes cluster. Please check your kubeconfig."
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    # Apply Kubernetes manifests
    if [ -d "infrastructure/kubernetes" ]; then
        print_status "Applying Kubernetes manifests..."
        kubectl apply -f infrastructure/kubernetes/
        
        print_status "Waiting for deployments to be ready..."
        kubectl wait --for=condition=available --timeout=300s deployment --all
        
        print_status "✅ All services deployed to Kubernetes"
    else
        print_error "Kubernetes manifests not found in infrastructure/kubernetes/"
        return 1
    fi
}

# Show service status
show_status() {
    print_header "Service Status"
    
    case $DEPLOYMENT_MODE in
        "local")
            print_status "Local deployment status:"
            for service in "${!SERVICES[@]}"; do
                port=${SERVICES[$service]}
                if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
                    print_status "✅ $service (http://localhost:$port) - HEALTHY"
                else
                    print_error "❌ $service (http://localhost:$port) - UNHEALTHY"
                fi
            done
            ;;
        "docker")
            print_status "Docker deployment status:"
            docker-compose ps
            ;;
        "kubernetes")
            print_status "Kubernetes deployment status:"
            kubectl get pods
            kubectl get services
            ;;
    esac
}

# Show access information
show_access_info() {
    print_header "Access Information"
    
    print_status "🌐 Service Endpoints:"
    for service in "${!SERVICES[@]}"; do
        port=${SERVICES[$service]}
        print_status "  $service: http://localhost:$port"
    done
    
    print_status ""
    print_status "📊 Monitoring & Tools:"
    print_status "  Prometheus: http://localhost:9090"
    print_status "  Grafana: http://localhost:3000 (admin/admin123)"
    print_status "  Jaeger: http://localhost:16686"
    print_status "  MLflow: http://localhost:5000"
    
    print_status ""
    print_status "🧪 Testing:"
    print_status "  Run integration tests: ./scripts/testing/run-integration-tests.sh"
    print_status "  Run load tests: k6 run tests/load/cross-system-load-test.js"
    
    print_status ""
    print_status "💬 ChatOps Examples:"
    print_status "  curl -X POST http://localhost:8092/api/v1/chat \\"
    print_status "    -H 'Content-Type: application/json' \\"
    print_status "    -d '{\"session_id\":\"test\",\"user_id\":\"demo\",\"message\":\"what is the system status?\"}'"
}

# Cleanup function
cleanup() {
    print_header "Cleaning Up"
    
    case $DEPLOYMENT_MODE in
        "local")
            print_status "Stopping local services..."
            if [ -f "logs/event-bus.pid" ]; then
                kill $(cat logs/event-bus.pid) 2>/dev/null || true
                rm logs/event-bus.pid
            fi
            if [ -f "logs/intelligent-orchestrator.pid" ]; then
                kill $(cat logs/intelligent-orchestrator.pid) 2>/dev/null || true
                rm logs/intelligent-orchestrator.pid
            fi
            if [ -f "logs/chatops-engine.pid" ]; then
                kill $(cat logs/chatops-engine.pid) 2>/dev/null || true
                rm logs/chatops-engine.pid
            fi
            ;;
        "docker")
            print_status "Stopping Docker services..."
            docker-compose down
            ;;
        "kubernetes")
            print_status "Deleting Kubernetes resources..."
            kubectl delete -f infrastructure/kubernetes/ || true
            ;;
    esac
}

# Signal handlers
trap cleanup EXIT
trap 'print_error "Deployment interrupted"; exit 1' INT TERM

# Main deployment function
main() {
    print_header "Cross-System Integration Deployment"
    print_status "Deployment mode: $DEPLOYMENT_MODE"
    
    cd "$PROJECT_ROOT"
    
    # Deploy infrastructure first
    if [ "$DEPLOYMENT_MODE" != "kubernetes" ]; then
        deploy_infrastructure
    fi
    
    # Deploy services based on mode
    case $DEPLOYMENT_MODE in
        "local")
            deploy_local
            ;;
        "docker")
            deploy_docker
            ;;
        "kubernetes")
            deploy_kubernetes
            ;;
        *)
            print_error "Invalid deployment mode: $DEPLOYMENT_MODE"
            print_status "Valid modes: local, docker, kubernetes"
            exit 1
            ;;
    esac
    
    # Show status and access information
    show_status
    show_access_info
    
    print_header "Deployment Complete"
    print_status "🎉 All services are deployed and running!"
    print_status "Press Ctrl+C to stop all services"
    
    # Keep script running for local deployment
    if [ "$DEPLOYMENT_MODE" == "local" ]; then
        print_status "Monitoring services... (Press Ctrl+C to stop)"
        while true; do
            sleep 30
            # Quick health check
            failed_services=0
            for service in "${!SERVICES[@]}"; do
                port=${SERVICES[$service]}
                if ! curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
                    ((failed_services++))
                fi
            done
            
            if [ $failed_services -gt 0 ]; then
                print_warning "$failed_services service(s) are unhealthy"
            fi
        done
    fi
}

# Show usage information
show_usage() {
    echo "Usage: $0 [MODE]"
    echo ""
    echo "Modes:"
    echo "  local      - Deploy services locally (default)"
    echo "  docker     - Deploy services using Docker Compose"
    echo "  kubernetes - Deploy services to Kubernetes cluster"
    echo ""
    echo "Examples:"
    echo "  $0                # Deploy locally"
    echo "  $0 docker         # Deploy with Docker"
    echo "  $0 kubernetes     # Deploy to Kubernetes"
}

# Check for help flag
if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    show_usage
    exit 0
fi

# Run main function
main "$@"
