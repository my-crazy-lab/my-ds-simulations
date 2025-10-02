#!/bin/bash

# Test runner script for microservices
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TEST_RESULTS_DIR="test-results"
COVERAGE_DIR="coverage"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Create directories
mkdir -p "$TEST_RESULTS_DIR"
mkdir -p "$COVERAGE_DIR"

echo -e "${BLUE}🧪 Starting Microservices Test Suite${NC}"
echo "=================================================="

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}$1${NC}"
    echo "$(printf '=%.0s' {1..50})"
}

# Function to run unit tests for a service
run_unit_tests() {
    local service_name=$1
    local service_path="services/$service_name"
    
    if [ ! -d "$service_path" ]; then
        echo -e "${YELLOW}⚠️  Service $service_name not found, skipping...${NC}"
        return 0
    fi
    
    echo -e "${BLUE}Running unit tests for $service_name...${NC}"
    
    cd "$service_path"
    
    # Check if go.mod exists
    if [ ! -f "go.mod" ]; then
        echo -e "${YELLOW}⚠️  No go.mod found for $service_name, skipping...${NC}"
        cd - > /dev/null
        return 0
    fi
    
    # Run tests with coverage
    if go test -v -race -coverprofile="../../$COVERAGE_DIR/${service_name}_coverage.out" ./...; then
        echo -e "${GREEN}✅ Unit tests passed for $service_name${NC}"
        
        # Generate coverage report
        if [ -f "../../$COVERAGE_DIR/${service_name}_coverage.out" ]; then
            go tool cover -html="../../$COVERAGE_DIR/${service_name}_coverage.out" -o "../../$COVERAGE_DIR/${service_name}_coverage.html"
            COVERAGE=$(go tool cover -func="../../$COVERAGE_DIR/${service_name}_coverage.out" | grep total | awk '{print $3}')
            echo -e "${BLUE}📊 Coverage for $service_name: $COVERAGE${NC}"
        fi
    else
        echo -e "${RED}❌ Unit tests failed for $service_name${NC}"
        cd - > /dev/null
        return 1
    fi
    
    cd - > /dev/null
    return 0
}

# Function to run K6 load tests
run_k6_tests() {
    local test_name=$1
    local test_file="tests/k6/${test_name}.js"
    local service_url=$2
    
    if [ ! -f "$test_file" ]; then
        echo -e "${YELLOW}⚠️  K6 test file $test_file not found, skipping...${NC}"
        return 0
    fi
    
    echo -e "${BLUE}Running K6 load test: $test_name...${NC}"
    
    # Check if service is accessible
    if ! curl -s -f "$service_url/health" > /dev/null; then
        echo -e "${YELLOW}⚠️  Service at $service_url not accessible, skipping K6 test...${NC}"
        return 0
    fi
    
    # Run K6 test
    if k6 run \
        --out json="$TEST_RESULTS_DIR/${test_name}_${TIMESTAMP}.json" \
        --summary-export="$TEST_RESULTS_DIR/${test_name}_summary_${TIMESTAMP}.json" \
        "$test_file"; then
        echo -e "${GREEN}✅ K6 load test passed: $test_name${NC}"
    else
        echo -e "${RED}❌ K6 load test failed: $test_name${NC}"
        return 1
    fi
    
    return 0
}

# Function to check if required tools are installed
check_dependencies() {
    print_section "🔍 Checking Dependencies"
    
    local missing_deps=()
    
    # Check Go
    if ! command -v go &> /dev/null; then
        missing_deps+=("go")
    else
        echo -e "${GREEN}✅ Go: $(go version)${NC}"
    fi
    
    # Check K6
    if ! command -v k6 &> /dev/null; then
        missing_deps+=("k6")
    else
        echo -e "${GREEN}✅ K6: $(k6 version)${NC}"
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    else
        echo -e "${GREEN}✅ curl: $(curl --version | head -n1)${NC}"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo -e "${RED}❌ Missing dependencies: ${missing_deps[*]}${NC}"
        echo -e "${YELLOW}Please install missing dependencies and try again.${NC}"
        exit 1
    fi
}

# Function to run integration tests
run_integration_tests() {
    print_section "🔗 Integration Tests"
    
    # Check if services are running
    local services=(
        "saga-orchestrator:8080"
        "inventory-service:8081"
        "payment-service:8082"
        "sync-service:8091"
    )
    
    local running_services=()
    
    for service_port in "${services[@]}"; do
        local service_name=$(echo "$service_port" | cut -d: -f1)
        local port=$(echo "$service_port" | cut -d: -f2)
        
        if curl -s -f "http://localhost:$port/health" > /dev/null; then
            running_services+=("$service_name:$port")
            echo -e "${GREEN}✅ $service_name is running on port $port${NC}"
        else
            echo -e "${YELLOW}⚠️  $service_name is not running on port $port${NC}"
        fi
    done
    
    if [ ${#running_services[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  No services running, skipping integration tests${NC}"
        return 0
    fi
    
    # Run basic integration test
    echo -e "${BLUE}Running basic integration test...${NC}"
    
    # Test saga creation and completion
    if curl -s -f "http://localhost:8080/health" > /dev/null; then
        local saga_response=$(curl -s -X POST http://localhost:8080/api/v1/sagas \
            -H "Content-Type: application/json" \
            -d '{
                "type": "order_processing",
                "data": {
                    "order_id": "integration-test-001",
                    "user_id": "test-user"
                }
            }')
        
        if echo "$saga_response" | grep -q '"id"'; then
            echo -e "${GREEN}✅ Integration test: Saga creation successful${NC}"
        else
            echo -e "${RED}❌ Integration test: Saga creation failed${NC}"
            echo "Response: $saga_response"
        fi
    fi
}

# Main execution
main() {
    local test_type=${1:-"all"}
    
    check_dependencies
    
    case $test_type in
        "unit")
            print_section "🧪 Unit Tests"
            
            local services=(
                "saga-orchestrator"
                "inventory-service"
                "payment-service"
                "notification-service"
                "sync-service"
                "analytics-etl"
                "disaster-recovery"
                "schema-migration"
                "consistency-testing"
                "cqrs-event-store"
            )
            
            local failed_tests=0
            
            for service in "${services[@]}"; do
                if ! run_unit_tests "$service"; then
                    ((failed_tests++))
                fi
            done
            
            if [ $failed_tests -eq 0 ]; then
                echo -e "\n${GREEN}🎉 All unit tests passed!${NC}"
            else
                echo -e "\n${RED}❌ $failed_tests service(s) failed unit tests${NC}"
                exit 1
            fi
            ;;
            
        "load")
            print_section "🚀 Load Tests (K6)"
            
            local k6_tests=(
                "saga-orchestrator-load-test:http://localhost:8080"
                "inventory-service-load-test:http://localhost:8081"
                "sync-service-load-test:http://localhost:8091"
            )
            
            local failed_tests=0
            
            for test_info in "${k6_tests[@]}"; do
                local test_name=$(echo "$test_info" | cut -d: -f1)
                local service_url=$(echo "$test_info" | cut -d: -f2-3)
                
                if ! run_k6_tests "$test_name" "$service_url"; then
                    ((failed_tests++))
                fi
            done
            
            if [ $failed_tests -eq 0 ]; then
                echo -e "\n${GREEN}🎉 All load tests passed!${NC}"
            else
                echo -e "\n${RED}❌ $failed_tests load test(s) failed${NC}"
                exit 1
            fi
            ;;
            
        "integration")
            run_integration_tests
            ;;
            
        "all")
            # Run all tests
            main "unit"
            main "integration"
            main "load"
            ;;
            
        *)
            echo -e "${RED}❌ Unknown test type: $test_type${NC}"
            echo "Usage: $0 [unit|load|integration|all]"
            exit 1
            ;;
    esac
    
    # Generate summary report
    print_section "📊 Test Summary"
    echo "Test results saved to: $TEST_RESULTS_DIR"
    echo "Coverage reports saved to: $COVERAGE_DIR"
    
    if [ -d "$COVERAGE_DIR" ] && [ "$(ls -A $COVERAGE_DIR)" ]; then
        echo -e "${BLUE}Coverage reports:${NC}"
        for coverage_file in "$COVERAGE_DIR"/*.html; do
            if [ -f "$coverage_file" ]; then
                echo "  - file://$PWD/$coverage_file"
            fi
        done
    fi
    
    echo -e "\n${GREEN}🎉 Test suite completed successfully!${NC}"
}

# Handle script arguments
if [ $# -eq 0 ]; then
    main "all"
else
    main "$1"
fi
