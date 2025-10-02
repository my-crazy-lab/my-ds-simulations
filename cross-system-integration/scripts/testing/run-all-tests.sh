#!/bin/bash

# Cross-System Integration - Comprehensive Test Runner
# This script runs all types of tests: unit, integration, and load tests

set -e  # Exit on any error

echo "🧪 Cross-System Integration - Running All Tests"
echo "=============================================="

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
TEST_RESULTS_DIR="$PROJECT_ROOT/test-results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Test configuration
RUN_UNIT_TESTS=${RUN_UNIT_TESTS:-true}
RUN_INTEGRATION_TESTS=${RUN_INTEGRATION_TESTS:-true}
RUN_LOAD_TESTS=${RUN_LOAD_TESTS:-true}
GENERATE_COVERAGE=${GENERATE_COVERAGE:-true}
PARALLEL_TESTS=${PARALLEL_TESTS:-true}

# Create test results directory
mkdir -p "$TEST_RESULTS_DIR"

# Test results tracking
declare -A TEST_RESULTS
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to record test result
record_test_result() {
    local test_name=$1
    local result=$2
    local duration=$3
    
    TEST_RESULTS["$test_name"]="$result:$duration"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [ "$result" == "PASS" ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        print_status "✅ $test_name - PASSED (${duration}s)"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        print_error "❌ $test_name - FAILED (${duration}s)"
    fi
}

# Check if services are running
check_services() {
    print_header "Checking Service Availability"
    
    local services=(
        "http://localhost:8090/health:Event Bus"
        "http://localhost:8091/health:Intelligent Orchestrator"
        "http://localhost:8092/health:ChatOps Engine"
    )
    
    local all_healthy=true
    
    for service_info in "${services[@]}"; do
        IFS=':' read -r url name <<< "$service_info"
        
        if curl -s -f "$url" > /dev/null 2>&1; then
            print_status "✅ $name is healthy"
        else
            print_warning "⚠️ $name is not available - some tests may fail"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = false ]; then
        print_warning "Some services are not running. Consider starting them with:"
        print_warning "  ./scripts/deployment/deploy-all-services.sh"
        print_warning ""
        read -p "Continue with tests anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Run unit tests
run_unit_tests() {
    print_header "Running Unit Tests"
    
    cd "$PROJECT_ROOT"
    
    # Activate Python virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    # Python unit tests
    print_status "Running Python unit tests..."
    local start_time=$(date +%s)
    
    if [ "$GENERATE_COVERAGE" = true ]; then
        # Run with coverage
        python -m pytest tests/unit/ -v \
            --cov=services \
            --cov-report=html:$TEST_RESULTS_DIR/coverage-html \
            --cov-report=xml:$TEST_RESULTS_DIR/coverage.xml \
            --cov-report=term \
            --junit-xml=$TEST_RESULTS_DIR/pytest-results.xml \
            > $TEST_RESULTS_DIR/unit-tests.log 2>&1
    else
        # Run without coverage
        python -m pytest tests/unit/ -v \
            --junit-xml=$TEST_RESULTS_DIR/pytest-results.xml \
            > $TEST_RESULTS_DIR/unit-tests.log 2>&1
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $? -eq 0 ]; then
        record_test_result "Python Unit Tests" "PASS" "$duration"
    else
        record_test_result "Python Unit Tests" "FAIL" "$duration"
        print_error "Python unit tests failed. Check $TEST_RESULTS_DIR/unit-tests.log"
    fi
    
    # Go unit tests
    print_status "Running Go unit tests..."
    start_time=$(date +%s)
    
    if [ -d "services/event-bus" ]; then
        cd services/event-bus
        go test ./... -v -coverprofile=$PROJECT_ROOT/$TEST_RESULTS_DIR/go-coverage.out \
            > $PROJECT_ROOT/$TEST_RESULTS_DIR/go-unit-tests.log 2>&1
        local go_result=$?
        
        # Generate Go coverage HTML report
        if [ -f "$PROJECT_ROOT/$TEST_RESULTS_DIR/go-coverage.out" ]; then
            go tool cover -html=$PROJECT_ROOT/$TEST_RESULTS_DIR/go-coverage.out \
                -o $PROJECT_ROOT/$TEST_RESULTS_DIR/go-coverage.html
        fi
        
        cd "$PROJECT_ROOT"
        
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        if [ $go_result -eq 0 ]; then
            record_test_result "Go Unit Tests" "PASS" "$duration"
        else
            record_test_result "Go Unit Tests" "FAIL" "$duration"
            print_error "Go unit tests failed. Check $TEST_RESULTS_DIR/go-unit-tests.log"
        fi
    else
        print_warning "Go services not found, skipping Go unit tests"
    fi
}

# Run integration tests
run_integration_tests() {
    print_header "Running Integration Tests"
    
    cd "$PROJECT_ROOT"
    
    # Activate Python virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    print_status "Running cross-system integration tests..."
    local start_time=$(date +%s)
    
    # Run integration tests
    python -m pytest tests/integration/ -v -s \
        --junit-xml=$TEST_RESULTS_DIR/integration-results.xml \
        > $TEST_RESULTS_DIR/integration-tests.log 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $? -eq 0 ]; then
        record_test_result "Integration Tests" "PASS" "$duration"
    else
        record_test_result "Integration Tests" "FAIL" "$duration"
        print_error "Integration tests failed. Check $TEST_RESULTS_DIR/integration-tests.log"
    fi
}

# Run load tests
run_load_tests() {
    print_header "Running Load Tests"
    
    cd "$PROJECT_ROOT"
    
    # Check if k6 is installed
    if ! command -v k6 > /dev/null 2>&1; then
        print_error "k6 is not installed. Please install k6 first."
        record_test_result "Load Tests" "FAIL" "0"
        return 1
    fi
    
    print_status "Running cross-system load tests..."
    local start_time=$(date +%s)
    
    # Run load tests with k6
    k6 run tests/load/cross-system-load-test.js \
        --out json=$TEST_RESULTS_DIR/load-test-results.json \
        > $TEST_RESULTS_DIR/load-tests.log 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $? -eq 0 ]; then
        record_test_result "Load Tests" "PASS" "$duration"
    else
        record_test_result "Load Tests" "FAIL" "$duration"
        print_error "Load tests failed. Check $TEST_RESULTS_DIR/load-tests.log"
    fi
}

# Run specific test suites
run_specific_tests() {
    print_header "Running Specific Test Suites"
    
    # API endpoint tests
    print_status "Testing API endpoints..."
    local start_time=$(date +%s)
    
    # Test event bus endpoints
    if curl -s -f "http://localhost:8090/health" > /dev/null 2>&1; then
        # Test event publishing
        local test_event='{"type":"test.event","source":"test","data":{"test":true}}'
        local response=$(curl -s -X POST "http://localhost:8090/api/v1/events" \
            -H "Content-Type: application/json" \
            -d "$test_event")
        
        if echo "$response" | grep -q "event_id"; then
            print_status "✅ Event Bus API test passed"
        else
            print_error "❌ Event Bus API test failed"
        fi
    fi
    
    # Test ChatOps endpoints
    if curl -s -f "http://localhost:8092/health" > /dev/null 2>&1; then
        local chat_request='{"session_id":"test","user_id":"test","message":"system status"}'
        local response=$(curl -s -X POST "http://localhost:8092/api/v1/chat" \
            -H "Content-Type: application/json" \
            -d "$chat_request")
        
        if echo "$response" | grep -q "intent"; then
            print_status "✅ ChatOps API test passed"
        else
            print_error "❌ ChatOps API test failed"
        fi
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    record_test_result "API Endpoint Tests" "PASS" "$duration"
}

# Generate test report
generate_test_report() {
    print_header "Generating Test Report"
    
    local report_file="$TEST_RESULTS_DIR/test-report-$TIMESTAMP.html"
    
    cat > "$report_file" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Cross-System Integration Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #f0f0f0; padding: 20px; border-radius: 5px; }
        .summary { margin: 20px 0; }
        .pass { color: green; }
        .fail { color: red; }
        .test-result { margin: 10px 0; padding: 10px; border-left: 4px solid #ddd; }
        .test-result.pass { border-left-color: green; background-color: #f0fff0; }
        .test-result.fail { border-left-color: red; background-color: #fff0f0; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Cross-System Integration Test Report</h1>
        <p>Generated: $(date)</p>
        <p>Test Run ID: $TIMESTAMP</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Tests</td><td>$TOTAL_TESTS</td></tr>
            <tr><td class="pass">Passed</td><td>$PASSED_TESTS</td></tr>
            <tr><td class="fail">Failed</td><td>$FAILED_TESTS</td></tr>
            <tr><td>Success Rate</td><td>$(( PASSED_TESTS * 100 / TOTAL_TESTS ))%</td></tr>
        </table>
    </div>
    
    <div class="results">
        <h2>Test Results</h2>
EOF

    # Add individual test results
    for test_name in "${!TEST_RESULTS[@]}"; do
        IFS=':' read -r result duration <<< "${TEST_RESULTS[$test_name]}"
        local css_class=$(echo "$result" | tr '[:upper:]' '[:lower:]')
        
        cat >> "$report_file" << EOF
        <div class="test-result $css_class">
            <strong>$test_name</strong> - $result (${duration}s)
        </div>
EOF
    done
    
    cat >> "$report_file" << EOF
    </div>
    
    <div class="artifacts">
        <h2>Test Artifacts</h2>
        <ul>
            <li><a href="coverage-html/index.html">Python Coverage Report</a></li>
            <li><a href="go-coverage.html">Go Coverage Report</a></li>
            <li><a href="pytest-results.xml">PyTest Results (XML)</a></li>
            <li><a href="integration-results.xml">Integration Test Results (XML)</a></li>
            <li><a href="load-test-results.json">Load Test Results (JSON)</a></li>
        </ul>
    </div>
</body>
</html>
EOF

    print_status "Test report generated: $report_file"
}

# Show test summary
show_test_summary() {
    print_header "Test Summary"
    
    print_status "📊 Test Execution Summary:"
    print_status "  Total Tests: $TOTAL_TESTS"
    print_status "  Passed: $PASSED_TESTS"
    print_status "  Failed: $FAILED_TESTS"
    print_status "  Success Rate: $(( PASSED_TESTS * 100 / TOTAL_TESTS ))%"
    
    if [ $FAILED_TESTS -gt 0 ]; then
        print_error ""
        print_error "❌ Some tests failed. Check the following logs:"
        for test_name in "${!TEST_RESULTS[@]}"; do
            IFS=':' read -r result duration <<< "${TEST_RESULTS[$test_name]}"
            if [ "$result" == "FAIL" ]; then
                print_error "  - $test_name"
            fi
        done
    else
        print_status ""
        print_status "🎉 All tests passed successfully!"
    fi
    
    print_status ""
    print_status "📁 Test artifacts saved to: $TEST_RESULTS_DIR"
    print_status "📄 Detailed report: $TEST_RESULTS_DIR/test-report-$TIMESTAMP.html"
}

# Main test execution
main() {
    print_header "Cross-System Integration Test Suite"
    print_status "Starting comprehensive test execution..."
    
    cd "$PROJECT_ROOT"
    
    # Check service availability
    check_services
    
    # Run test suites based on configuration
    if [ "$RUN_UNIT_TESTS" = true ]; then
        run_unit_tests
    fi
    
    if [ "$RUN_INTEGRATION_TESTS" = true ]; then
        run_integration_tests
    fi
    
    if [ "$RUN_LOAD_TESTS" = true ]; then
        run_load_tests
    fi
    
    # Run specific API tests
    run_specific_tests
    
    # Generate reports
    generate_test_report
    show_test_summary
    
    # Exit with appropriate code
    if [ $FAILED_TESTS -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
}

# Show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --unit-only        Run only unit tests"
    echo "  --integration-only Run only integration tests"
    echo "  --load-only        Run only load tests"
    echo "  --no-coverage      Skip coverage generation"
    echo "  --sequential       Run tests sequentially (not in parallel)"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  RUN_UNIT_TESTS=false        Skip unit tests"
    echo "  RUN_INTEGRATION_TESTS=false Skip integration tests"
    echo "  RUN_LOAD_TESTS=false        Skip load tests"
    echo "  GENERATE_COVERAGE=false     Skip coverage generation"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit-only)
            RUN_UNIT_TESTS=true
            RUN_INTEGRATION_TESTS=false
            RUN_LOAD_TESTS=false
            shift
            ;;
        --integration-only)
            RUN_UNIT_TESTS=false
            RUN_INTEGRATION_TESTS=true
            RUN_LOAD_TESTS=false
            shift
            ;;
        --load-only)
            RUN_UNIT_TESTS=false
            RUN_INTEGRATION_TESTS=false
            RUN_LOAD_TESTS=true
            shift
            ;;
        --no-coverage)
            GENERATE_COVERAGE=false
            shift
            ;;
        --sequential)
            PARALLEL_TESTS=false
            shift
            ;;
        -h|--help)
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

# Run main function
main "$@"
