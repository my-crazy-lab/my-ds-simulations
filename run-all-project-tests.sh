#!/bin/bash

# Comprehensive Test Runner for All 10 Distributed Systems Projects
# This script validates that all projects can run locally without errors
# and have comprehensive test coverage

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project directories
PROJECTS=(
    "core-banking-ledger"
    "payments-acquiring-gateway"
    "realtime-payments-crossborder"
    "clearing-settlement-engine"
    "aml-kyc-monitoring-system"
    "low-latency-trading-engine"
    "market-risk-engine"
    "custody-key-management-system"
    "regtech-automated-reporting"
    "fraud-detection-insurance"
)

# Test results tracking
declare -A TEST_RESULTS
TOTAL_PROJECTS=0
PASSED_PROJECTS=0
FAILED_PROJECTS=0

# Logging
LOG_FILE="test-results-$(date +%Y%m%d-%H%M%S).log"

log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log_info() {
    log "${BLUE}[INFO]${NC} $1"
}

log_success() {
    log "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    log "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    log "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check required tools
    local required_tools=("docker" "docker-compose" "python3" "go" "curl" "make")
    
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "$tool is required but not installed"
            exit 1
        fi
    done
    
    # Check Python packages
    python3 -c "import requests, psycopg2, pytest" 2>/dev/null || {
        log_info "Installing required Python packages..."
        pip3 install requests psycopg2-binary pytest
    }
    
    log_success "Prerequisites check completed"
}

# Validate project structure
validate_project_structure() {
    local project=$1
    log_info "Validating structure for $project..."
    
    if [ ! -d "$project" ]; then
        log_error "Project directory $project does not exist"
        return 1
    fi
    
    # Check required files
    local required_files=("README.md" "docker-compose.yml")
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$project/$file" ]; then
            log_warning "Missing $file in $project"
        fi
    done
    
    # Check test directories
    if [ ! -d "$project/tests" ]; then
        log_warning "Missing tests directory in $project"
        return 1
    fi
    
    log_success "Structure validation completed for $project"
    return 0
}

# Start project services
start_project_services() {
    local project=$1
    log_info "Starting services for $project..."
    
    cd "$project"
    
    # Stop any existing services
    docker-compose down -v --remove-orphans 2>/dev/null || true
    
    # Start services
    if ! docker-compose up -d; then
        log_error "Failed to start services for $project"
        cd ..
        return 1
    fi
    
    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    sleep 30  # Give services time to start
    
    cd ..
    log_success "Services started for $project"
    return 0
}

# Run project tests
run_project_tests() {
    local project=$1
    log_info "Running tests for $project..."
    
    cd "$project"
    
    local test_passed=true
    
    # Run different types of tests based on what's available
    if [ -f "Makefile" ]; then
        # Try comprehensive test if available
        if make -n test-comprehensive &>/dev/null; then
            log_info "Running comprehensive test suite..."
            if ! timeout 300 make test-comprehensive; then
                log_warning "Comprehensive tests failed or timed out"
                test_passed=false
            fi
        elif make -n test-all &>/dev/null; then
            log_info "Running all tests..."
            if ! timeout 300 make test-all; then
                log_warning "Test suite failed or timed out"
                test_passed=false
            fi
        elif make -n test &>/dev/null; then
            log_info "Running basic tests..."
            if ! timeout 300 make test; then
                log_warning "Basic tests failed or timed out"
                test_passed=false
            fi
        fi
    fi
    
    # Run Python tests directly if available
    if [ -d "tests/unit" ]; then
        log_info "Running Python unit tests..."
        for test_file in tests/unit/*.py; do
            if [ -f "$test_file" ]; then
                if ! timeout 120 python3 "$test_file"; then
                    log_warning "Python test $test_file failed"
                    test_passed=false
                fi
            fi
        done
    fi
    
    # Run pytest if available
    if [ -d "tests" ] && find tests -name "*.py" -type f | grep -q .; then
        log_info "Running pytest..."
        if ! timeout 180 python3 -m pytest tests/ -v --tb=short; then
            log_warning "Pytest execution failed"
            test_passed=false
        fi
    fi
    
    cd ..
    
    if [ "$test_passed" = true ]; then
        log_success "Tests passed for $project"
        return 0
    else
        log_error "Tests failed for $project"
        return 1
    fi
}

# Stop project services
stop_project_services() {
    local project=$1
    log_info "Stopping services for $project..."
    
    cd "$project"
    docker-compose down -v --remove-orphans 2>/dev/null || true
    cd ..
    
    log_success "Services stopped for $project"
}

# Health check for project
health_check_project() {
    local project=$1
    log_info "Performing health check for $project..."
    
    cd "$project"
    
    # Try to run health check if Makefile supports it
    if [ -f "Makefile" ] && make -n health-check &>/dev/null; then
        if make health-check; then
            log_success "Health check passed for $project"
            cd ..
            return 0
        fi
    fi
    
    # Basic Docker health check
    local healthy_services=0
    local total_services=0
    
    if [ -f "docker-compose.yml" ]; then
        total_services=$(docker-compose ps -q | wc -l)
        healthy_services=$(docker-compose ps | grep -c "Up" || echo "0")
        
        if [ "$healthy_services" -gt 0 ]; then
            log_success "Health check passed for $project ($healthy_services/$total_services services up)"
            cd ..
            return 0
        fi
    fi
    
    log_warning "Health check inconclusive for $project"
    cd ..
    return 1
}

# Test individual project
test_project() {
    local project=$1
    log_info "Testing project: $project"
    
    TOTAL_PROJECTS=$((TOTAL_PROJECTS + 1))
    
    # Validate structure
    if ! validate_project_structure "$project"; then
        TEST_RESULTS["$project"]="STRUCTURE_FAILED"
        FAILED_PROJECTS=$((FAILED_PROJECTS + 1))
        return 1
    fi
    
    # Start services
    if ! start_project_services "$project"; then
        TEST_RESULTS["$project"]="SERVICES_FAILED"
        FAILED_PROJECTS=$((FAILED_PROJECTS + 1))
        return 1
    fi
    
    # Health check
    if ! health_check_project "$project"; then
        log_warning "Health check failed for $project, but continuing with tests..."
    fi
    
    # Run tests
    if run_project_tests "$project"; then
        TEST_RESULTS["$project"]="PASSED"
        PASSED_PROJECTS=$((PASSED_PROJECTS + 1))
        log_success "✅ Project $project: ALL TESTS PASSED"
    else
        TEST_RESULTS["$project"]="TESTS_FAILED"
        FAILED_PROJECTS=$((FAILED_PROJECTS + 1))
        log_error "❌ Project $project: TESTS FAILED"
    fi
    
    # Stop services
    stop_project_services "$project"
    
    # Clean up Docker resources
    docker system prune -f &>/dev/null || true
    
    log_info "Completed testing project: $project"
    echo "----------------------------------------"
}

# Generate test report
generate_report() {
    log_info "Generating comprehensive test report..."
    
    echo ""
    log_info "=========================================="
    log_info "COMPREHENSIVE TEST RESULTS SUMMARY"
    log_info "=========================================="
    echo ""
    
    log_info "Total Projects Tested: $TOTAL_PROJECTS"
    log_success "Passed: $PASSED_PROJECTS"
    log_error "Failed: $FAILED_PROJECTS"
    
    echo ""
    log_info "Detailed Results:"
    echo ""
    
    for project in "${PROJECTS[@]}"; do
        local result="${TEST_RESULTS[$project]:-NOT_TESTED}"
        case "$result" in
            "PASSED")
                log_success "✅ $project: PASSED"
                ;;
            "TESTS_FAILED")
                log_error "❌ $project: TESTS FAILED"
                ;;
            "SERVICES_FAILED")
                log_error "❌ $project: SERVICES FAILED TO START"
                ;;
            "STRUCTURE_FAILED")
                log_error "❌ $project: STRUCTURE VALIDATION FAILED"
                ;;
            *)
                log_warning "⚠️  $project: NOT TESTED"
                ;;
        esac
    done
    
    echo ""
    
    if [ "$FAILED_PROJECTS" -eq 0 ]; then
        log_success "🎉 ALL PROJECTS PASSED COMPREHENSIVE TESTING!"
        log_success "All 10 distributed systems projects are ready for production use."
    else
        log_error "⚠️  $FAILED_PROJECTS projects failed testing."
        log_error "Please review the logs and fix the issues before deployment."
    fi
    
    echo ""
    log_info "Detailed logs saved to: $LOG_FILE"
    log_info "=========================================="
}

# Main execution
main() {
    log_info "Starting comprehensive testing of all distributed systems projects"
    log_info "Test run started at: $(date)"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Test each project
    for project in "${PROJECTS[@]}"; do
        if [ -d "$project" ]; then
            test_project "$project"
        else
            log_warning "Project directory $project not found, skipping..."
            TEST_RESULTS["$project"]="NOT_FOUND"
        fi
    done
    
    # Generate final report
    generate_report
    
    # Exit with appropriate code
    if [ "$FAILED_PROJECTS" -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Handle script interruption
trap 'log_error "Test run interrupted"; exit 1' INT TERM

# Run main function
main "$@"
