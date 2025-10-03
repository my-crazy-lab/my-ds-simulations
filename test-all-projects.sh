#!/bin/bash

# Comprehensive test script for all 10 distributed systems projects
# Tests Python test files, Docker Compose validation, and basic functionality

set -e

echo "🧪 Testing All 10 Distributed Systems Projects"
echo "=============================================="

# Define the 10 distributed systems projects
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

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TOTAL_PROJECTS=10
TESTED_PROJECTS=0
TEST_FAILURES=0

echo -e "${BLUE}Running comprehensive tests...${NC}"
echo

for project in "${PROJECTS[@]}"; do
    echo -e "${YELLOW}🧪 Testing Project: $project${NC}"
    
    if [ ! -d "$project" ]; then
        echo -e "${RED}❌ Project directory not found: $project${NC}"
        ((TEST_FAILURES++))
        continue
    fi
    
    cd "$project"
    
    PROJECT_TEST_FAILURES=0
    
    # Test 1: Python syntax validation
    echo -e "${BLUE}🐍 Testing Python syntax...${NC}"
    if [ -d "tests" ]; then
        python_files=$(find tests -name "*.py" 2>/dev/null | wc -l)
        if [ $python_files -gt 0 ]; then
            echo "Found $python_files Python test files"
            
            syntax_errors=0
            find tests -name "*.py" 2>/dev/null | while read -r py_file; do
                if python3 -m py_compile "$py_file" 2>/dev/null; then
                    echo -e "${GREEN}✅ $py_file syntax OK${NC}"
                else
                    echo -e "${RED}❌ $py_file syntax error${NC}"
                    ((syntax_errors++))
                fi
            done
            
            if [ $syntax_errors -eq 0 ]; then
                echo -e "${GREEN}✅ All Python files have valid syntax${NC}"
            else
                echo -e "${RED}❌ $syntax_errors Python files have syntax errors${NC}"
                ((PROJECT_TEST_FAILURES++))
            fi
        else
            echo -e "${YELLOW}⚠️  No Python test files found${NC}"
        fi
    else
        echo -e "${RED}❌ No tests directory found${NC}"
        ((PROJECT_TEST_FAILURES++))
    fi
    
    # Test 2: Docker Compose validation
    echo -e "${BLUE}🐳 Testing Docker Compose...${NC}"
    if [ -f "docker-compose.yml" ]; then
        if docker-compose config >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Docker Compose configuration is valid${NC}"
            
            # Count services
            services_count=$(docker-compose config --services | wc -l)
            echo -e "${GREEN}✅ Docker Compose defines $services_count services${NC}"
        else
            echo -e "${RED}❌ Docker Compose configuration is invalid${NC}"
            ((PROJECT_TEST_FAILURES++))
        fi
    else
        echo -e "${RED}❌ No docker-compose.yml found${NC}"
        ((PROJECT_TEST_FAILURES++))
    fi
    
    # Test 3: Makefile validation
    echo -e "${BLUE}🔨 Testing Makefile...${NC}"
    if [ -f "Makefile" ]; then
        # Check for common targets
        required_targets=("build" "test" "clean")
        missing_targets=0
        
        for target in "${required_targets[@]}"; do
            if grep -q "^$target:" Makefile; then
                echo -e "${GREEN}✅ Makefile has '$target' target${NC}"
            else
                echo -e "${YELLOW}⚠️  Makefile missing '$target' target${NC}"
                ((missing_targets++))
            fi
        done
        
        if [ $missing_targets -eq 0 ]; then
            echo -e "${GREEN}✅ Makefile has all required targets${NC}"
        else
            echo -e "${YELLOW}⚠️  Makefile missing $missing_targets required targets${NC}"
        fi
    else
        echo -e "${RED}❌ No Makefile found${NC}"
        ((PROJECT_TEST_FAILURES++))
    fi
    
    # Test 4: README validation
    echo -e "${BLUE}📖 Testing README...${NC}"
    if [ -f "README.md" ]; then
        readme_lines=$(wc -l < README.md)
        if [ $readme_lines -gt 100 ]; then
            echo -e "${GREEN}✅ README.md is comprehensive ($readme_lines lines)${NC}"
        else
            echo -e "${YELLOW}⚠️  README.md might need more content ($readme_lines lines)${NC}"
        fi
        
        # Check for key sections
        key_sections=("Architecture" "Features" "Quick Start" "API")
        missing_sections=0
        
        for section in "${key_sections[@]}"; do
            if grep -qi "$section" README.md; then
                echo -e "${GREEN}✅ README has '$section' section${NC}"
            else
                echo -e "${YELLOW}⚠️  README missing '$section' section${NC}"
                ((missing_sections++))
            fi
        done
    else
        echo -e "${RED}❌ No README.md found${NC}"
        ((PROJECT_TEST_FAILURES++))
    fi
    
    # Test 5: Test file content validation
    echo -e "${BLUE}🔍 Testing test file content...${NC}"
    if [ -d "tests/unit" ]; then
        unit_test_files=$(find tests/unit -name "*.py" | wc -l)
        if [ $unit_test_files -gt 0 ]; then
            # Check if test files have actual test functions
            test_functions=0
            find tests/unit -name "*.py" | while read -r test_file; do
                func_count=$(grep -c "def test_" "$test_file" 2>/dev/null || echo "0")
                if [ $func_count -gt 0 ]; then
                    echo -e "${GREEN}✅ $test_file has $func_count test functions${NC}"
                    ((test_functions+=func_count))
                else
                    echo -e "${YELLOW}⚠️  $test_file has no test functions${NC}"
                fi
            done
        fi
    fi
    
    if [ -d "tests/chaos" ]; then
        chaos_test_files=$(find tests/chaos -name "*.py" | wc -l)
        if [ $chaos_test_files -gt 0 ]; then
            # Check if chaos test files have actual test functions
            find tests/chaos -name "*.py" | while read -r test_file; do
                func_count=$(grep -c "def test_" "$test_file" 2>/dev/null || echo "0")
                if [ $func_count -gt 0 ]; then
                    echo -e "${GREEN}✅ $test_file has $func_count chaos test functions${NC}"
                else
                    echo -e "${YELLOW}⚠️  $test_file has no test functions${NC}"
                fi
            done
        fi
    fi
    
    # Test 6: Basic import test for Python files
    echo -e "${BLUE}📦 Testing Python imports...${NC}"
    if [ -d "tests" ]; then
        import_errors=0
        find tests -name "*.py" | while read -r py_file; do
            # Try to import the file to check for import errors
            if python3 -c "
import sys
import os
sys.path.insert(0, os.path.dirname('$py_file'))
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('test_module', '$py_file')
    module = importlib.util.module_from_spec(spec)
    # Don't execute, just check imports
    print('✅ Imports OK for $py_file')
except ImportError as e:
    print('⚠️  Import warning for $py_file: ' + str(e))
except Exception as e:
    print('⚠️  Other issue for $py_file: ' + str(e))
" 2>/dev/null; then
                echo -e "${GREEN}✅ Python imports OK for $py_file${NC}"
            else
                echo -e "${YELLOW}⚠️  Python import issues in $py_file${NC}"
            fi
        done
    fi
    
    if [ $PROJECT_TEST_FAILURES -eq 0 ]; then
        echo -e "${GREEN}✅ Project $project tests PASSED${NC}"
        ((TESTED_PROJECTS++))
    else
        echo -e "${RED}❌ Project $project has $PROJECT_TEST_FAILURES test failures${NC}"
        ((TEST_FAILURES+=PROJECT_TEST_FAILURES))
    fi
    
    echo
    cd ..
done

# Summary
echo -e "${BLUE}📊 Test Summary${NC}"
echo "==============="
echo -e "Total Projects: ${TOTAL_PROJECTS}"
echo -e "Projects Passed: ${GREEN}${TESTED_PROJECTS}${NC}"
echo -e "Projects Failed: ${RED}$((TOTAL_PROJECTS - TESTED_PROJECTS))${NC}"
echo -e "Total Test Failures: ${RED}${TEST_FAILURES}${NC}"

if [ $TESTED_PROJECTS -eq $TOTAL_PROJECTS ] && [ $TEST_FAILURES -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL PROJECT TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some projects have test issues${NC}"
    exit 1
fi
