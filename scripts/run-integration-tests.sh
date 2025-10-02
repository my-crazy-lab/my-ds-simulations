#!/bin/bash

# Integration Test Runner Script
# Runs comprehensive integration tests for the microservices system

set -e

echo "🚀 Starting Microservices Integration Tests"
echo "============================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker-compose.yml"
TEST_DIR="$PROJECT_ROOT/tests/integration"

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

# Function to check if Docker is running
check_docker() {
    print_status "Checking Docker..."
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    print_success "Docker is running"
}

# Function to check if docker-compose is available
check_docker_compose() {
    print_status "Checking Docker Compose..."
    if ! command -v docker-compose > /dev/null 2>&1; then
        print_error "docker-compose is not installed. Please install it and try again."
        exit 1
    fi
    print_success "Docker Compose is available"
}

# Function to start services
start_services() {
    print_status "Starting microservices..."
    cd "$PROJECT_ROOT"
    
    # Build and start all services
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d --build
    
    print_status "Waiting for services to be healthy..."
    
    # Wait for services to be ready
    local max_attempts=60
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        print_status "Health check attempt $attempt/$max_attempts"
        
        # Check key services
        local services_ready=true
        
        # Check PostgreSQL
        if ! docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
            services_ready=false
        fi
        
        # Check Redis
        if ! docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
            services_ready=false
        fi
        
        # Check Kafka
        if ! docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list > /dev/null 2>&1; then
            services_ready=false
        fi
        
        # Check MongoDB
        if ! docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T mongodb mongosh --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
            services_ready=false
        fi
        
        if [ "$services_ready" = true ]; then
            print_success "All infrastructure services are ready"
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            print_error "Services failed to become ready within timeout"
            print_status "Showing service logs..."
            docker-compose -f "$DOCKER_COMPOSE_FILE" logs --tail=50
            exit 1
        fi
        
        sleep 5
        ((attempt++))
    done
    
    # Wait a bit more for application services
    print_status "Waiting for application services to start..."
    sleep 30
}

# Function to setup test environment
setup_test_environment() {
    print_status "Setting up test environment..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "$TEST_DIR/venv" ]; then
        print_status "Creating Python virtual environment..."
        python3 -m venv "$TEST_DIR/venv"
    fi
    
    # Activate virtual environment and install dependencies
    print_status "Installing test dependencies..."
    source "$TEST_DIR/venv/bin/activate"
    pip install -r "$TEST_DIR/requirements.txt"
    
    print_success "Test environment setup complete"
}

# Function to run integration tests
run_tests() {
    print_status "Running integration tests..."
    
    cd "$TEST_DIR"
    source venv/bin/activate
    
    # Run the test suite
    python run_all_tests.py
    
    local test_exit_code=$?
    
    if [ $test_exit_code -eq 0 ]; then
        print_success "All integration tests passed!"
    else
        print_error "Some integration tests failed!"
        return $test_exit_code
    fi
}

# Function to cleanup
cleanup() {
    print_status "Cleaning up..."
    
    if [ "$CLEANUP_SERVICES" = "true" ]; then
        print_status "Stopping services..."
        cd "$PROJECT_ROOT"
        docker-compose -f "$DOCKER_COMPOSE_FILE" down
        print_success "Services stopped"
    else
        print_warning "Services left running (use --cleanup to stop them)"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --cleanup     Stop services after tests complete"
    echo "  --no-build    Skip building services (use existing images)"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Run tests, leave services running"
    echo "  $0 --cleanup          # Run tests and stop services"
    echo "  $0 --no-build         # Run tests without rebuilding"
}

# Parse command line arguments
CLEANUP_SERVICES="false"
BUILD_SERVICES="true"

while [[ $# -gt 0 ]]; do
    case $1 in
        --cleanup)
            CLEANUP_SERVICES="true"
            shift
            ;;
        --no-build)
            BUILD_SERVICES="false"
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_status "Starting integration test run..."
    print_status "Project root: $PROJECT_ROOT"
    print_status "Test directory: $TEST_DIR"
    
    # Pre-flight checks
    check_docker
    check_docker_compose
    
    # Setup and run tests
    if [ "$BUILD_SERVICES" = "true" ]; then
        start_services
    else
        print_status "Skipping service build (--no-build specified)"
    fi
    
    setup_test_environment
    
    # Run tests and capture exit code
    local test_result=0
    run_tests || test_result=$?
    
    # Cleanup
    cleanup
    
    # Final status
    if [ $test_result -eq 0 ]; then
        print_success "Integration test run completed successfully!"
        echo ""
        echo "🎉 All tests passed! Your microservices system is working correctly."
    else
        print_error "Integration test run failed!"
        echo ""
        echo "❌ Some tests failed. Please check the output above for details."
        exit $test_result
    fi
}

# Set trap for cleanup on script exit
trap cleanup EXIT

# Run main function
main "$@"
