#!/bin/bash

# Comprehensive Distributed Microservices Deployment Script
# This script deploys the complete distributed database and microservices architecture

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="infrastructure/docker-compose-distributed.yml"
SERVICES_DIR="services"
INFRASTRUCTURE_DIR="infrastructure"
MONITORING_DIR="monitoring"
CHAOS_DIR="chaos"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check Go
    if ! command -v go &> /dev/null; then
        print_error "Go is not installed"
        exit 1
    fi
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    print_success "All prerequisites are installed"
}

# Function to build services
build_services() {
    print_status "Building microservices..."
    
    # List of services to build
    services=(
        "saga-orchestrator"
        "inventory-service"
        "payment-service"
        "notification-service"
        "sharding-proxy"
        "sync-service"
        "analytics-etl"
        "disaster-recovery"
        "schema-migration"
        "consistency-testing"
        "cqrs-event-store"
    )
    
    for service in "${services[@]}"; do
        if [ -d "$SERVICES_DIR/$service" ]; then
            print_status "Building $service..."
            cd "$SERVICES_DIR/$service"
            
            # Initialize go module if go.mod doesn't exist
            if [ ! -f "go.mod" ]; then
                go mod init "github.com/microservices-saga/services/$service"
                go mod tidy
            fi
            
            # Build the service
            go build -o main .
            
            cd - > /dev/null
            print_success "$service built successfully"
        else
            print_warning "Service directory $service not found, skipping..."
        fi
    done
}

# Function to create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    directories=(
        "logs"
        "data/postgres"
        "data/mongodb"
        "data/clickhouse"
        "data/redis"
        "backups"
        "monitoring/grafana/dashboards"
        "monitoring/prometheus/rules"
    )
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        print_status "Created directory: $dir"
    done
}

# Function to set up environment variables
setup_environment() {
    print_status "Setting up environment variables..."
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        cat > .env << EOF
# Database Configuration
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=microservices

# MongoDB Configuration
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin123

# ClickHouse Configuration
CLICKHOUSE_USER=admin
CLICKHOUSE_PASSWORD=admin123

# Redis Configuration
REDIS_PASSWORD=redis123

# Kafka Configuration
KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181
KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:29092

# Monitoring Configuration
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin123

# AWS Configuration (for backups)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-west-2

# Application Configuration
LOG_LEVEL=info
JAEGER_ENDPOINT=http://jaeger:14268/api/traces
EOF
        print_success "Created .env file"
    else
        print_status ".env file already exists"
    fi
}

# Function to deploy infrastructure
deploy_infrastructure() {
    print_status "Deploying distributed infrastructure..."
    
    # Stop any existing containers
    docker-compose -f "$COMPOSE_FILE" down --remove-orphans
    
    # Pull latest images
    docker-compose -f "$COMPOSE_FILE" pull
    
    # Start infrastructure services first
    print_status "Starting database services..."
    docker-compose -f "$COMPOSE_FILE" up -d \
        postgres-primary \
        postgres-replica \
        postgres-shard1 \
        postgres-shard2 \
        mongodb-primary \
        mongodb-secondary1 \
        mongodb-secondary2 \
        clickhouse \
        clickhouse-replica \
        redis-node1 \
        redis-node2 \
        redis-node3
    
    # Wait for databases to be ready
    print_status "Waiting for databases to be ready..."
    sleep 30
    
    # Initialize MongoDB replica set
    print_status "Initializing MongoDB replica set..."
    docker-compose -f "$COMPOSE_FILE" exec -T mongodb-primary mongo --eval "
        rs.initiate({
            _id: 'rs0',
            members: [
                { _id: 0, host: 'mongodb-primary:27017', priority: 2 },
                { _id: 1, host: 'mongodb-secondary1:27017', priority: 1 },
                { _id: 2, host: 'mongodb-secondary2:27017', priority: 1 }
            ]
        })
    " || print_warning "MongoDB replica set initialization may have failed"
    
    # Initialize Redis cluster
    print_status "Initializing Redis cluster..."
    sleep 10
    docker-compose -f "$COMPOSE_FILE" exec -T redis-node1 redis-cli --cluster create \
        redis-node1:7001 redis-node2:7002 redis-node3:7003 \
        --cluster-replicas 0 --cluster-yes || print_warning "Redis cluster initialization may have failed"
    
    print_success "Infrastructure services started"
}

# Function to deploy application services
deploy_services() {
    print_status "Deploying application services..."
    
    # Start Kafka and Zookeeper
    docker-compose -f "$COMPOSE_FILE" up -d zookeeper kafka schema-registry
    sleep 20
    
    # Start monitoring services
    docker-compose -f "$COMPOSE_FILE" up -d prometheus grafana jaeger
    sleep 10
    
    # Start application services
    docker-compose -f "$COMPOSE_FILE" up -d \
        sharding-proxy \
        cqrs-event-store \
        sync-service \
        analytics-etl \
        disaster-recovery \
        schema-migration \
        consistency-testing
    
    sleep 20
    
    # Start saga orchestrator and business services
    docker-compose -f "$COMPOSE_FILE" up -d \
        saga-orchestrator \
        inventory-service \
        payment-service \
        notification-service
    
    print_success "Application services started"
}

# Function to run health checks
run_health_checks() {
    print_status "Running health checks..."
    
    services=(
        "http://localhost:8080/health"  # saga-orchestrator
        "http://localhost:8081/health"  # inventory-service
        "http://localhost:8082/health"  # payment-service
        "http://localhost:8083/health"  # notification-service
        "http://localhost:8090/health"  # cqrs-event-store
        "http://localhost:8091/health"  # sync-service
        "http://localhost:8092/health"  # analytics-etl
        "http://localhost:8093/health"  # disaster-recovery
        "http://localhost:8094/health"  # schema-migration
        "http://localhost:8095/health"  # consistency-testing
    )
    
    for service in "${services[@]}"; do
        print_status "Checking $service..."
        if curl -f -s "$service" > /dev/null; then
            print_success "$service is healthy"
        else
            print_warning "$service is not responding"
        fi
    done
}

# Function to run smoke tests
run_smoke_tests() {
    print_status "Running smoke tests..."
    
    # Test saga orchestrator
    print_status "Testing saga orchestrator..."
    curl -X POST http://localhost:8080/api/v1/sagas \
        -H "Content-Type: application/json" \
        -d '{
            "type": "order_processing",
            "data": {
                "order_id": "test-order-1",
                "user_id": "test-user-1",
                "items": [{"sku": "LAPTOP001", "quantity": 1}]
            }
        }' || print_warning "Saga orchestrator test failed"
    
    # Test CQRS event store
    print_status "Testing CQRS event store..."
    curl -X POST http://localhost:8090/api/v1/commands \
        -H "Content-Type: application/json" \
        -d '{
            "aggregate_id": "test-aggregate-1",
            "command_type": "CreateItem",
            "data": {"name": "Test Item", "price": 100}
        }' || print_warning "CQRS event store test failed"
    
    print_success "Smoke tests completed"
}

# Function to display service URLs
display_service_urls() {
    print_success "Deployment completed successfully!"
    echo ""
    echo "Service URLs:"
    echo "============="
    echo "Saga Orchestrator:     http://localhost:8080"
    echo "Inventory Service:     http://localhost:8081"
    echo "Payment Service:       http://localhost:8082"
    echo "Notification Service:  http://localhost:8083"
    echo "CQRS Event Store:      http://localhost:8090"
    echo "Sync Service:          http://localhost:8091"
    echo "Analytics ETL:         http://localhost:8092"
    echo "Disaster Recovery:     http://localhost:8093"
    echo "Schema Migration:      http://localhost:8094"
    echo "Consistency Testing:   http://localhost:8095"
    echo ""
    echo "Infrastructure:"
    echo "==============="
    echo "PostgreSQL Primary:    localhost:5432"
    echo "PostgreSQL Replica:    localhost:5433"
    echo "Sharding Proxy:        localhost:5434"
    echo "MongoDB Cluster:       localhost:27017,27018,27019"
    echo "ClickHouse:            localhost:8123"
    echo "Redis Cluster:         localhost:7001,7002,7003"
    echo "Kafka:                 localhost:9092"
    echo ""
    echo "Monitoring:"
    echo "==========="
    echo "Grafana:               http://localhost:3000 (admin/admin123)"
    echo "Prometheus:            http://localhost:9090"
    echo "Jaeger:                http://localhost:16686"
    echo ""
    echo "Metrics endpoints are available at :9090/metrics for each service"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  deploy     Deploy the complete distributed system"
    echo "  stop       Stop all services"
    echo "  restart    Restart all services"
    echo "  logs       Show logs for all services"
    echo "  status     Show status of all services"
    echo "  test       Run smoke tests"
    echo "  cleanup    Clean up all containers and volumes"
    echo "  help       Show this help message"
}

# Main execution
case "${1:-deploy}" in
    "deploy")
        print_status "Starting distributed microservices deployment..."
        check_prerequisites
        create_directories
        setup_environment
        build_services
        deploy_infrastructure
        deploy_services
        sleep 30
        run_health_checks
        run_smoke_tests
        display_service_urls
        ;;
    "stop")
        print_status "Stopping all services..."
        docker-compose -f "$COMPOSE_FILE" down
        print_success "All services stopped"
        ;;
    "restart")
        print_status "Restarting all services..."
        docker-compose -f "$COMPOSE_FILE" restart
        print_success "All services restarted"
        ;;
    "logs")
        docker-compose -f "$COMPOSE_FILE" logs -f
        ;;
    "status")
        docker-compose -f "$COMPOSE_FILE" ps
        ;;
    "test")
        run_smoke_tests
        ;;
    "cleanup")
        print_warning "This will remove all containers, networks, and volumes!"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose -f "$COMPOSE_FILE" down -v --remove-orphans
            docker system prune -f
            print_success "Cleanup completed"
        fi
        ;;
    "help")
        show_usage
        ;;
    *)
        print_error "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac
