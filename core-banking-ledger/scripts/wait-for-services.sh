#!/bin/bash

# Wait for Services Script
# Waits for all required services to be healthy before proceeding

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MAX_WAIT_TIME=300  # 5 minutes
CHECK_INTERVAL=5   # 5 seconds

# Service endpoints to check
declare -A SERVICES=(
    ["PostgreSQL Primary"]="localhost:5433"
    ["PostgreSQL Replica"]="localhost:5434"
    ["Redis"]="localhost:6380"
    ["Kafka"]="localhost:9093"
    ["Schema Registry"]="localhost:8082"
    ["Prometheus"]="localhost:9091"
    ["Grafana"]="localhost:3001"
    ["Jaeger"]="localhost:16687"
)

# HTTP endpoints to check
declare -A HTTP_SERVICES=(
    ["Schema Registry"]="http://localhost:8082/subjects"
    ["Prometheus"]="http://localhost:9091/-/healthy"
    ["Grafana"]="http://localhost:3001/api/health"
    ["Jaeger"]="http://localhost:16687/api/services"
)

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date +'%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# Function to check if a port is open
check_port() {
    local host_port=$1
    local host=$(echo $host_port | cut -d':' -f1)
    local port=$(echo $host_port | cut -d':' -f2)
    
    nc -z "$host" "$port" >/dev/null 2>&1
}

# Function to check HTTP endpoint
check_http() {
    local url=$1
    curl -f -s "$url" >/dev/null 2>&1
}

# Function to check PostgreSQL
check_postgres() {
    local host_port=$1
    local host=$(echo $host_port | cut -d':' -f1)
    local port=$(echo $host_port | cut -d':' -f2)
    
    PGPASSWORD=secure_banking_pass psql -h "$host" -p "$port" -U banking_user -d core_banking -c "SELECT 1;" >/dev/null 2>&1
}

# Function to check Redis
check_redis() {
    local host_port=$1
    local host=$(echo $host_port | cut -d':' -f1)
    local port=$(echo $host_port | cut -d':' -f2)
    
    redis-cli -h "$host" -p "$port" ping | grep -q "PONG"
}

# Function to check Kafka
check_kafka() {
    local host_port=$1
    
    # Try to list topics
    kafka-topics --bootstrap-server "$host_port" --list >/dev/null 2>&1
}

# Function to wait for a service
wait_for_service() {
    local service_name=$1
    local host_port=$2
    local start_time=$(date +%s)
    
    print_status $YELLOW "Waiting for $service_name at $host_port..."
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $MAX_WAIT_TIME ]; then
            print_status $RED "Timeout waiting for $service_name after ${MAX_WAIT_TIME}s"
            return 1
        fi
        
        # Check service based on type
        case $service_name in
            "PostgreSQL"*)
                if check_postgres "$host_port"; then
                    print_status $GREEN "$service_name is ready!"
                    return 0
                fi
                ;;
            "Redis")
                if check_redis "$host_port"; then
                    print_status $GREEN "$service_name is ready!"
                    return 0
                fi
                ;;
            "Kafka")
                if check_kafka "$host_port"; then
                    print_status $GREEN "$service_name is ready!"
                    return 0
                fi
                ;;
            *)
                if check_port "$host_port"; then
                    print_status $GREEN "$service_name is ready!"
                    return 0
                fi
                ;;
        esac
        
        sleep $CHECK_INTERVAL
    done
}

# Function to wait for HTTP service
wait_for_http_service() {
    local service_name=$1
    local url=$2
    local start_time=$(date +%s)
    
    print_status $YELLOW "Waiting for $service_name at $url..."
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $MAX_WAIT_TIME ]; then
            print_status $RED "Timeout waiting for $service_name after ${MAX_WAIT_TIME}s"
            return 1
        fi
        
        if check_http "$url"; then
            print_status $GREEN "$service_name is ready!"
            return 0
        fi
        
        sleep $CHECK_INTERVAL
    done
}

# Function to check if Docker Compose is running
check_docker_compose() {
    if ! docker-compose ps >/dev/null 2>&1; then
        print_status $RED "Docker Compose is not running. Please start services first:"
        print_status $YELLOW "  docker-compose up -d"
        exit 1
    fi
}

# Function to show service status
show_service_status() {
    print_status $BLUE "Current service status:"
    docker-compose ps
    echo ""
}

# Main function
main() {
    print_status $BLUE "Core Banking Ledger - Service Health Check"
    print_status $BLUE "=========================================="
    echo ""
    
    # Check if Docker Compose is running
    check_docker_compose
    
    # Show current status
    show_service_status
    
    # Wait for infrastructure services first
    print_status $BLUE "Checking infrastructure services..."
    
    # Check port-based services
    for service_name in "${!SERVICES[@]}"; do
        if ! wait_for_service "$service_name" "${SERVICES[$service_name]}"; then
            print_status $RED "Failed to start $service_name"
            exit 1
        fi
    done
    
    # Check HTTP services
    for service_name in "${!HTTP_SERVICES[@]}"; do
        if ! wait_for_http_service "$service_name" "${HTTP_SERVICES[$service_name]}"; then
            print_status $RED "Failed to start $service_name"
            exit 1
        fi
    done
    
    # Additional health checks
    print_status $BLUE "Running additional health checks..."
    
    # Check if Kafka topics can be created
    print_status $YELLOW "Testing Kafka topic creation..."
    if kafka-topics --bootstrap-server localhost:9093 --create --topic health-check --partitions 1 --replication-factor 1 --if-not-exists >/dev/null 2>&1; then
        print_status $GREEN "Kafka topic creation successful"
        kafka-topics --bootstrap-server localhost:9093 --delete --topic health-check >/dev/null 2>&1 || true
    else
        print_status $RED "Kafka topic creation failed"
        exit 1
    fi
    
    # Check database connectivity with sample query
    print_status $YELLOW "Testing database connectivity..."
    if PGPASSWORD=secure_banking_pass psql -h localhost -p 5433 -U banking_user -d core_banking -c "SELECT COUNT(*) FROM chart_of_accounts;" >/dev/null 2>&1; then
        print_status $GREEN "Database connectivity successful"
    else
        print_status $RED "Database connectivity failed"
        exit 1
    fi
    
    # Check Redis connectivity
    print_status $YELLOW "Testing Redis connectivity..."
    if redis-cli -h localhost -p 6380 set health-check "ok" >/dev/null 2>&1 && redis-cli -h localhost -p 6380 get health-check >/dev/null 2>&1; then
        print_status $GREEN "Redis connectivity successful"
        redis-cli -h localhost -p 6380 del health-check >/dev/null 2>&1 || true
    else
        print_status $RED "Redis connectivity failed"
        exit 1
    fi
    
    echo ""
    print_status $GREEN "✅ All services are healthy and ready!"
    print_status $BLUE "You can now run tests or start the application services."
    echo ""
    
    # Show useful endpoints
    print_status $BLUE "Useful endpoints:"
    echo "  🔍 Grafana Dashboard: http://localhost:3001 (admin/banking_admin)"
    echo "  📊 Prometheus Metrics: http://localhost:9091"
    echo "  🔍 Jaeger Tracing: http://localhost:16687"
    echo "  📋 Schema Registry: http://localhost:8082"
    echo ""
    
    # Show next steps
    print_status $BLUE "Next steps:"
    echo "  1. Build services: make build"
    echo "  2. Run tests: make test"
    echo "  3. Start application services: make start"
    echo "  4. Load sample data: make load-sample-data"
    echo ""
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Wait for all Core Banking Ledger services to be healthy"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --quiet, -q    Suppress output except errors"
        echo "  --timeout, -t  Set timeout in seconds (default: 300)"
        echo ""
        echo "Environment Variables:"
        echo "  MAX_WAIT_TIME    Maximum time to wait in seconds (default: 300)"
        echo "  CHECK_INTERVAL   Check interval in seconds (default: 5)"
        echo ""
        exit 0
        ;;
    --quiet|-q)
        # Redirect stdout to /dev/null for quiet mode
        exec 1>/dev/null
        ;;
    --timeout|-t)
        if [ -n "$2" ]; then
            MAX_WAIT_TIME=$2
            shift 2
        else
            print_status $RED "Error: --timeout requires a value"
            exit 1
        fi
        ;;
esac

# Check for required tools
for tool in nc curl psql redis-cli kafka-topics docker-compose; do
    if ! command -v $tool >/dev/null 2>&1; then
        print_status $RED "Error: Required tool '$tool' is not installed"
        exit 1
    fi
done

# Run main function
main "$@"
