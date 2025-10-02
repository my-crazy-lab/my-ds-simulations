#!/bin/bash

# Cross-System Integration Platform - Local Setup Validation
# This script validates that everything is properly set up and can run locally

set -e  # Exit on any error

echo "🔍 Cross-System Integration Platform - Local Setup Validation"
echo "============================================================"

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
VALIDATION_RESULTS=()

# Function to record validation result
record_result() {
    local test_name=$1
    local result=$2
    local message=$3
    
    VALIDATION_RESULTS+=("$test_name:$result:$message")
    
    if [ "$result" == "PASS" ]; then
        print_status "✅ $test_name: $message"
    else
        print_error "❌ $test_name: $message"
    fi
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Docker
    if command -v docker > /dev/null 2>&1; then
        docker_version=$(docker --version | awk '{print $3}' | sed 's/,//')
        record_result "Docker" "PASS" "Version $docker_version installed"
    else
        record_result "Docker" "FAIL" "Docker is not installed"
    fi
    
    # Check Docker Compose
    if command -v docker-compose > /dev/null 2>&1; then
        compose_version=$(docker-compose --version | awk '{print $3}' | sed 's/,//')
        record_result "Docker Compose" "PASS" "Version $compose_version installed"
    else
        record_result "Docker Compose" "FAIL" "Docker Compose is not installed"
    fi
    
    # Check Python
    if command -v python3 > /dev/null 2>&1; then
        python_version=$(python3 --version | awk '{print $2}')
        record_result "Python3" "PASS" "Version $python_version installed"
    else
        record_result "Python3" "FAIL" "Python3 is not installed"
    fi
    
    # Check Go
    if command -v go > /dev/null 2>&1; then
        go_version=$(go version | awk '{print $3}')
        record_result "Go" "PASS" "Version $go_version installed"
    else
        record_result "Go" "FAIL" "Go is not installed"
    fi
    
    # Check Node.js
    if command -v node > /dev/null 2>&1; then
        node_version=$(node --version)
        record_result "Node.js" "PASS" "Version $node_version installed"
    else
        record_result "Node.js" "FAIL" "Node.js is not installed"
    fi
    
    # Check k6
    if command -v k6 > /dev/null 2>&1; then
        k6_version=$(k6 version | head -n1 | awk '{print $2}')
        record_result "k6" "PASS" "Version $k6_version installed"
    else
        record_result "k6" "FAIL" "k6 is not installed"
    fi
}

# Validate project structure
validate_project_structure() {
    print_header "Validating Project Structure"
    
    cd "$PROJECT_ROOT"
    
    # Check core directories
    directories=(
        "services/event-bus"
        "services/intelligent-orchestrator"
        "services/chatops-engine"
        "shared/events"
        "tests/unit"
        "tests/integration"
        "tests/load"
        "scripts/setup"
        "scripts/deployment"
        "scripts/testing"
        "docs/architecture"
        "docs/tutorials"
    )
    
    for dir in "${directories[@]}"; do
        if [ -d "$dir" ]; then
            record_result "Directory $dir" "PASS" "Exists"
        else
            record_result "Directory $dir" "FAIL" "Missing"
        fi
    done
    
    # Check core files
    files=(
        "docker-compose.yml"
        "README.md"
        "services/event-bus/main.go"
        "services/event-bus/go.mod"
        "services/intelligent-orchestrator/main.py"
        "services/intelligent-orchestrator/requirements.txt"
        "services/chatops-engine/main.py"
        "services/chatops-engine/requirements.txt"
        "shared/events/unified_event.go"
        "shared/events/go.mod"
    )
    
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            record_result "File $file" "PASS" "Exists"
        else
            record_result "File $file" "FAIL" "Missing"
        fi
    done
}

# Validate Go modules
validate_go_modules() {
    print_header "Validating Go Modules"
    
    cd "$PROJECT_ROOT"
    
    # Check shared events module
    if [ -d "shared/events" ]; then
        cd shared/events
        if go mod verify > /dev/null 2>&1; then
            record_result "Go Shared Events Module" "PASS" "Module is valid"
        else
            record_result "Go Shared Events Module" "FAIL" "Module verification failed"
        fi
        cd ../..
    fi
    
    # Check event-bus module
    if [ -d "services/event-bus" ]; then
        cd services/event-bus
        if go mod verify > /dev/null 2>&1; then
            record_result "Go Event Bus Module" "PASS" "Module is valid"
        else
            record_result "Go Event Bus Module" "FAIL" "Module verification failed"
        fi
        
        # Try to build
        if go build -o /tmp/event-bus-test ./main.go > /dev/null 2>&1; then
            record_result "Go Event Bus Build" "PASS" "Builds successfully"
            rm -f /tmp/event-bus-test
        else
            record_result "Go Event Bus Build" "FAIL" "Build failed"
        fi
        cd ../..
    fi
}

# Validate Python environments
validate_python_environment() {
    print_header "Validating Python Environment"
    
    cd "$PROJECT_ROOT"
    
    # Check if virtual environment exists
    if [ -d "venv" ]; then
        record_result "Python Virtual Environment" "PASS" "Exists"
        
        # Activate and check packages
        source venv/bin/activate
        
        # Check core packages
        packages=("fastapi" "uvicorn" "httpx" "pytest" "scikit-learn" "transformers")
        
        for package in "${packages[@]}"; do
            if pip show "$package" > /dev/null 2>&1; then
                version=$(pip show "$package" | grep Version | awk '{print $2}')
                record_result "Python Package $package" "PASS" "Version $version installed"
            else
                record_result "Python Package $package" "FAIL" "Not installed"
            fi
        done
        
        deactivate
    else
        record_result "Python Virtual Environment" "FAIL" "Not found"
    fi
}

# Test Docker infrastructure
test_docker_infrastructure() {
    print_header "Testing Docker Infrastructure"
    
    cd "$PROJECT_ROOT"
    
    # Check if docker-compose.yml is valid
    if docker-compose config > /dev/null 2>&1; then
        record_result "Docker Compose Config" "PASS" "Configuration is valid"
    else
        record_result "Docker Compose Config" "FAIL" "Configuration is invalid"
        return
    fi
    
    # Try to start infrastructure services
    print_status "Starting infrastructure services for testing..."
    
    if docker-compose up -d redis > /dev/null 2>&1; then
        record_result "Redis Container" "PASS" "Started successfully"
        
        # Wait a moment and test connection
        sleep 5
        if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
            record_result "Redis Connection" "PASS" "Connection successful"
        else
            record_result "Redis Connection" "FAIL" "Connection failed"
        fi
        
        # Stop the container
        docker-compose stop redis > /dev/null 2>&1
    else
        record_result "Redis Container" "FAIL" "Failed to start"
    fi
}

# Test unit tests
test_unit_tests() {
    print_header "Testing Unit Tests"
    
    cd "$PROJECT_ROOT"
    
    # Activate Python environment
    if [ -d "venv" ]; then
        source venv/bin/activate
        
        # Run Python unit tests
        if python -m pytest tests/unit/ -v --tb=short > /tmp/unit-test-output.log 2>&1; then
            test_count=$(grep -c "PASSED\|FAILED" /tmp/unit-test-output.log || echo "0")
            record_result "Python Unit Tests" "PASS" "$test_count tests executed"
        else
            record_result "Python Unit Tests" "FAIL" "Some tests failed"
            print_warning "Check /tmp/unit-test-output.log for details"
        fi
        
        deactivate
    else
        record_result "Python Unit Tests" "FAIL" "Virtual environment not found"
    fi
    
    # Test Go unit tests
    if [ -d "services/event-bus" ]; then
        cd services/event-bus
        if go test ./... -v > /tmp/go-unit-test-output.log 2>&1; then
            record_result "Go Unit Tests" "PASS" "All tests passed"
        else
            record_result "Go Unit Tests" "FAIL" "Some tests failed"
            print_warning "Check /tmp/go-unit-test-output.log for details"
        fi
        cd ../..
    fi
}

# Validate scripts
validate_scripts() {
    print_header "Validating Scripts"
    
    cd "$PROJECT_ROOT"
    
    # Check script permissions
    scripts=(
        "scripts/setup/install-dependencies.sh"
        "scripts/deployment/deploy-all-services.sh"
        "scripts/testing/run-all-tests.sh"
        "scripts/demo/run-complete-demo.py"
    )
    
    for script in "${scripts[@]}"; do
        if [ -f "$script" ]; then
            if [ -x "$script" ]; then
                record_result "Script $script" "PASS" "Executable"
            else
                record_result "Script $script" "FAIL" "Not executable"
            fi
        else
            record_result "Script $script" "FAIL" "Missing"
        fi
    done
    
    # Test script syntax
    if [ -f "scripts/setup/install-dependencies.sh" ]; then
        if bash -n scripts/setup/install-dependencies.sh; then
            record_result "Install Dependencies Script Syntax" "PASS" "Valid bash syntax"
        else
            record_result "Install Dependencies Script Syntax" "FAIL" "Syntax errors"
        fi
    fi
    
    if [ -f "scripts/demo/run-complete-demo.py" ]; then
        if python3 -m py_compile scripts/demo/run-complete-demo.py; then
            record_result "Demo Script Syntax" "PASS" "Valid Python syntax"
        else
            record_result "Demo Script Syntax" "FAIL" "Syntax errors"
        fi
    fi
}

# Generate validation report
generate_validation_report() {
    print_header "Validation Report"
    
    local total_tests=0
    local passed_tests=0
    local failed_tests=0
    
    echo "📊 Validation Results Summary:"
    echo "=============================="
    
    for result in "${VALIDATION_RESULTS[@]}"; do
        IFS=':' read -r test_name result_status message <<< "$result"
        total_tests=$((total_tests + 1))
        
        if [ "$result_status" == "PASS" ]; then
            passed_tests=$((passed_tests + 1))
        else
            failed_tests=$((failed_tests + 1))
        fi
    done
    
    echo "Total Tests: $total_tests"
    echo "Passed: $passed_tests"
    echo "Failed: $failed_tests"
    echo "Success Rate: $(( passed_tests * 100 / total_tests ))%"
    
    if [ $failed_tests -eq 0 ]; then
        print_status ""
        print_status "🎉 All validation tests passed!"
        print_status "The Cross-System Integration Platform is ready to run locally."
        print_status ""
        print_status "Next steps:"
        print_status "1. Start infrastructure: docker-compose up -d"
        print_status "2. Deploy services: ./scripts/deployment/deploy-all-services.sh"
        print_status "3. Run demo: ./scripts/demo/run-complete-demo.py"
        print_status "4. Run tests: ./scripts/testing/run-all-tests.sh"
        return 0
    else
        print_error ""
        print_error "❌ $failed_tests validation test(s) failed."
        print_error "Please address the issues above before proceeding."
        print_error ""
        print_error "Common fixes:"
        print_error "- Install missing dependencies: ./scripts/setup/install-dependencies.sh"
        print_error "- Create Python virtual environment: python3 -m venv venv"
        print_error "- Install Python packages: pip install -r requirements-test.txt"
        print_error "- Run go mod tidy in Go service directories"
        return 1
    fi
}

# Main validation function
main() {
    print_header "Starting Local Setup Validation"
    
    cd "$PROJECT_ROOT"
    
    check_prerequisites
    validate_project_structure
    validate_go_modules
    validate_python_environment
    test_docker_infrastructure
    test_unit_tests
    validate_scripts
    
    if generate_validation_report; then
        exit 0
    else
        exit 1
    fi
}

# Show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --quick        Run only basic checks (skip tests)"
    echo "  --no-docker    Skip Docker infrastructure tests"
    echo "  -h, --help     Show this help message"
    echo ""
    echo "This script validates that the Cross-System Integration Platform"
    echo "is properly set up and ready to run locally."
}

# Parse command line arguments
QUICK_MODE=false
SKIP_DOCKER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --no-docker)
            SKIP_DOCKER=true
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
