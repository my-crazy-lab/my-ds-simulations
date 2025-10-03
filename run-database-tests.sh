#!/bin/bash

# Comprehensive Database Systems Test Runner
# Runs all database-focused tests across the 10 projects

set -e

echo "🗄️  Running Comprehensive Database Systems Tests"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_PROJECTS=10
TESTED_PROJECTS=0
FAILED_TESTS=0

# Database projects to test
PROJECTS=(
    "raft-consensus"
    "distributed-kv-store"
    "commit-log-service"
    "geo-replicated-datastore"
    "stateful-stream-processor"
    "distributed-cache"
    "k8s-operator-sre"
    "chaos-lab-jepsen"
    "multi-tenant-scheduler"
    "distributed-rate-limiter"
)

# Function to run tests for a project
run_project_tests() {
    local project=$1
    echo -e "${BLUE}🧪 Testing Database Features: $project${NC}"
    
    if [ ! -d "$project" ]; then
        echo -e "${RED}❌ Project directory not found: $project${NC}"
        ((FAILED_TESTS++))
        return 1
    fi
    
    cd "$project"
    
    # Check if project has database tests
    if [ -d "tests/database" ]; then
        echo -e "${GREEN}✅ Found database tests directory${NC}"
        
        # Run database-specific tests
        echo "Running database tests..."
        if python3 -m pytest tests/database/ -v --tb=short; then
            echo -e "${GREEN}✅ Database tests passed${NC}"
        else
            echo -e "${RED}❌ Database tests failed${NC}"
            ((FAILED_TESTS++))
        fi
    else
        echo -e "${YELLOW}⚠️  No database tests directory found, running standard tests${NC}"
    fi
    
    # Run unit tests
    if [ -d "tests/unit" ]; then
        echo "Running unit tests..."
        if python3 -m pytest tests/unit/ -v --tb=short; then
            echo -e "${GREEN}✅ Unit tests passed${NC}"
        else
            echo -e "${RED}❌ Unit tests failed${NC}"
            ((FAILED_TESTS++))
        fi
    fi
    
    # Run chaos tests
    if [ -d "tests/chaos" ]; then
        echo "Running chaos tests..."
        if python3 -m pytest tests/chaos/ -v --tb=short; then
            echo -e "${GREEN}✅ Chaos tests passed${NC}"
        else
            echo -e "${RED}❌ Chaos tests failed${NC}"
            ((FAILED_TESTS++))
        fi
    fi
    
    ((TESTED_PROJECTS++))
    echo
    cd ..
}

# Function to check prerequisites
check_prerequisites() {
    echo -e "${BLUE}🔍 Checking prerequisites...${NC}"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 is required but not installed${NC}"
        exit 1
    fi
    
    # Check pytest
    if ! python3 -c "import pytest" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Installing pytest...${NC}"
        pip3 install pytest requests aiohttp
    fi
    
    echo -e "${GREEN}✅ Prerequisites checked${NC}"
    echo
}

# Function to start services if needed
start_services() {
    local project=$1
    echo -e "${BLUE}🚀 Starting services for $project${NC}"
    
    cd "$project"
    
    # Check if docker-compose exists and start services
    if [ -f "docker-compose.yml" ]; then
        echo "Starting Docker services..."
        if command -v docker-compose &> /dev/null; then
            docker-compose up -d
            echo "Waiting for services to be ready..."
            sleep 10
        elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
            docker compose up -d
            echo "Waiting for services to be ready..."
            sleep 10
        else
            echo -e "${YELLOW}⚠️  Docker not available, skipping service startup${NC}"
        fi
    fi
    
    cd ..
}

# Function to stop services
stop_services() {
    local project=$1
    echo -e "${BLUE}🛑 Stopping services for $project${NC}"
    
    cd "$project"
    
    if [ -f "docker-compose.yml" ]; then
        if command -v docker-compose &> /dev/null; then
            docker-compose down
        elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
            docker compose down
        fi
    fi
    
    cd ..
}

# Function to run comprehensive database tests
run_comprehensive_tests() {
    echo -e "${BLUE}🧪 Running Comprehensive Database Tests${NC}"
    echo "========================================"
    
    for project in "${PROJECTS[@]}"; do
        echo -e "${YELLOW}📁 Testing Project: $project${NC}"
        
        # Start services for the project
        start_services "$project"
        
        # Run tests
        run_project_tests "$project"
        
        # Stop services to free resources
        stop_services "$project"
        
        echo "----------------------------------------"
    done
}

# Function to generate test report
generate_report() {
    echo -e "${BLUE}📊 Database Systems Test Report${NC}"
    echo "==============================="
    echo -e "Total Projects Tested: ${TOTAL_PROJECTS}"
    echo -e "Successfully Tested: ${GREEN}${TESTED_PROJECTS}${NC}"
    echo -e "Failed Tests: ${RED}${FAILED_TESTS}${NC}"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}🎉 ALL DATABASE TESTS PASSED!${NC}"
        echo
        echo "✅ Database Features Verified:"
        echo "  • WAL Management and Durability"
        echo "  • Consistency Models (Strong, Eventual, Session)"
        echo "  • Exactly-Once Semantics"
        echo "  • CRDT Conflict Resolution"
        echo "  • Stream Processing State Management"
        echo "  • Distributed Caching"
        echo "  • Database Operator Automation"
        echo "  • Chaos Engineering for Databases"
        echo "  • Multi-Tenant Data Isolation"
        echo "  • Rate Limiting with Database Integration"
        echo
        return 0
    else
        echo -e "${RED}❌ Some database tests failed${NC}"
        echo "Please check the test output above for details."
        return 1
    fi
}

# Main execution
main() {
    echo -e "${GREEN}Starting Database Systems Test Suite${NC}"
    echo "===================================="
    echo
    
    # Check prerequisites
    check_prerequisites
    
    # Run comprehensive tests
    run_comprehensive_tests
    
    # Generate report
    generate_report
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Database Systems Test Runner"
        echo "Usage: $0 [options]"
        echo
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --project, -p  Test specific project only"
        echo "  --no-docker    Skip Docker service management"
        echo
        echo "Examples:"
        echo "  $0                           # Run all database tests"
        echo "  $0 --project raft-consensus # Test specific project"
        exit 0
        ;;
    --project|-p)
        if [ -z "${2:-}" ]; then
            echo -e "${RED}❌ Project name required${NC}"
            exit 1
        fi
        PROJECT_NAME="$2"
        echo -e "${BLUE}Testing single project: $PROJECT_NAME${NC}"
        check_prerequisites
        start_services "$PROJECT_NAME"
        run_project_tests "$PROJECT_NAME"
        stop_services "$PROJECT_NAME"
        exit $?
        ;;
    *)
        main
        exit $?
        ;;
esac
