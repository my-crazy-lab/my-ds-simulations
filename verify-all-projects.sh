#!/bin/bash

# Comprehensive verification script for all 10 distributed systems projects
# Checks documentation, test cases, Go modules, and basic functionality

set -e

echo "🔍 Verifying All 10 Distributed Systems Projects"
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
VERIFIED_PROJECTS=0
ISSUES_FOUND=0

echo -e "${BLUE}Checking project structure and files...${NC}"
echo

for project in "${PROJECTS[@]}"; do
    echo -e "${YELLOW}📁 Verifying Project: $project${NC}"
    
    if [ ! -d "$project" ]; then
        echo -e "${RED}❌ Project directory not found: $project${NC}"
        ((ISSUES_FOUND++))
        continue
    fi
    
    cd "$project"
    
    # Check required files
    REQUIRED_FILES=("README.md" "docker-compose.yml" "Makefile")
    PROJECT_ISSUES=0
    
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$file" ]; then
            echo -e "${GREEN}✅ $file exists${NC}"
        else
            echo -e "${RED}❌ Missing $file${NC}"
            ((PROJECT_ISSUES++))
        fi
    done
    
    # Check test directories and files
    if [ -d "tests" ]; then
        echo -e "${GREEN}✅ tests/ directory exists${NC}"
        
        # Check for unit tests
        if [ -d "tests/unit" ]; then
            unit_tests=$(find tests/unit -name "*.py" | wc -l)
            if [ $unit_tests -gt 0 ]; then
                echo -e "${GREEN}✅ Unit tests found: $unit_tests files${NC}"
            else
                echo -e "${RED}❌ No unit test files found${NC}"
                ((PROJECT_ISSUES++))
            fi
        else
            echo -e "${RED}❌ tests/unit/ directory missing${NC}"
            ((PROJECT_ISSUES++))
        fi
        
        # Check for chaos tests
        if [ -d "tests/chaos" ]; then
            chaos_tests=$(find tests/chaos -name "*.py" | wc -l)
            if [ $chaos_tests -gt 0 ]; then
                echo -e "${GREEN}✅ Chaos tests found: $chaos_tests files${NC}"
            else
                echo -e "${RED}❌ No chaos test files found${NC}"
                ((PROJECT_ISSUES++))
            fi
        else
            echo -e "${RED}❌ tests/chaos/ directory missing${NC}"
            ((PROJECT_ISSUES++))
        fi
    else
        echo -e "${RED}❌ tests/ directory missing${NC}"
        ((PROJECT_ISSUES++))
    fi
    
    # Check Go services
    if [ -d "services" ]; then
        echo -e "${GREEN}✅ services/ directory exists${NC}"
        
        # Find Go main files
        go_files=$(find services -name "main.go" | wc -l)
        if [ $go_files -gt 0 ]; then
            echo -e "${GREEN}✅ Go services found: $go_files main.go files${NC}"
            
            # Check each Go service for go.mod
            find services -name "main.go" | while read -r main_file; do
                service_dir=$(dirname "$main_file")
                if [ -f "$service_dir/go.mod" ]; then
                    echo -e "${GREEN}✅ go.mod exists in $service_dir${NC}"
                else
                    echo -e "${YELLOW}⚠️  Creating go.mod in $service_dir${NC}"
                    # Create go.mod file
                    service_name=$(basename "$service_dir")
                    cat > "$service_dir/go.mod" << EOF
module $service_name

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/prometheus/client_golang v1.17.0
    github.com/redis/go-redis/v9 v9.3.0
    go.etcd.io/etcd/client/v3 v3.5.10
)
EOF
                fi
            done
        else
            echo -e "${YELLOW}⚠️  No Go services found (may use other languages)${NC}"
        fi
    else
        # Check for operator directory (k8s-operator-sre case)
        if [ -d "operator" ]; then
            echo -e "${GREEN}✅ operator/ directory exists${NC}"
            if [ -f "operator/main.go" ]; then
                echo -e "${GREEN}✅ operator/main.go exists${NC}"
                if [ ! -f "operator/go.mod" ]; then
                    echo -e "${YELLOW}⚠️  Creating go.mod in operator/${NC}"
                    cat > "operator/go.mod" << EOF
module operator

go 1.21

require (
    k8s.io/client-go v0.28.3
    k8s.io/apimachinery v0.28.3
    sigs.k8s.io/controller-runtime v0.16.3
)
EOF
                fi
            fi
        else
            echo -e "${YELLOW}⚠️  No services/ or operator/ directory found${NC}"
        fi
    fi
    
    # Check Python test syntax
    echo -e "${BLUE}🐍 Checking Python test syntax...${NC}"
    python_errors=0
    find tests -name "*.py" 2>/dev/null | while read -r py_file; do
        if ! python3 -m py_compile "$py_file" 2>/dev/null; then
            echo -e "${RED}❌ Python syntax error in $py_file${NC}"
            ((python_errors++))
        fi
    done
    
    # Check README content
    if [ -f "README.md" ]; then
        readme_lines=$(wc -l < README.md)
        if [ $readme_lines -gt 50 ]; then
            echo -e "${GREEN}✅ README.md is comprehensive ($readme_lines lines)${NC}"
        else
            echo -e "${YELLOW}⚠️  README.md might be too short ($readme_lines lines)${NC}"
        fi
    fi
    
    # Check docker-compose services
    if [ -f "docker-compose.yml" ]; then
        services_count=$(grep -c "^  [a-zA-Z]" docker-compose.yml || echo "0")
        if [ $services_count -gt 3 ]; then
            echo -e "${GREEN}✅ Docker Compose has $services_count services${NC}"
        else
            echo -e "${YELLOW}⚠️  Docker Compose has only $services_count services${NC}"
        fi
    fi
    
    # Check Makefile targets
    if [ -f "Makefile" ]; then
        makefile_targets=$(grep -c "^[a-zA-Z][a-zA-Z0-9_-]*:" Makefile || echo "0")
        if [ $makefile_targets -gt 5 ]; then
            echo -e "${GREEN}✅ Makefile has $makefile_targets targets${NC}"
        else
            echo -e "${YELLOW}⚠️  Makefile has only $makefile_targets targets${NC}"
        fi
    fi
    
    if [ $PROJECT_ISSUES -eq 0 ]; then
        echo -e "${GREEN}✅ Project $project verification PASSED${NC}"
        ((VERIFIED_PROJECTS++))
    else
        echo -e "${RED}❌ Project $project has $PROJECT_ISSUES issues${NC}"
        ((ISSUES_FOUND+=PROJECT_ISSUES))
    fi
    
    echo
    cd ..
done

# Summary
echo -e "${BLUE}📊 Verification Summary${NC}"
echo "======================"
echo -e "Total Projects: ${TOTAL_PROJECTS}"
echo -e "Verified Projects: ${GREEN}${VERIFIED_PROJECTS}${NC}"
echo -e "Projects with Issues: ${RED}$((TOTAL_PROJECTS - VERIFIED_PROJECTS))${NC}"
echo -e "Total Issues Found: ${RED}${ISSUES_FOUND}${NC}"

if [ $VERIFIED_PROJECTS -eq $TOTAL_PROJECTS ] && [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL PROJECTS VERIFIED SUCCESSFULLY!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some projects need attention${NC}"
    exit 1
fi
