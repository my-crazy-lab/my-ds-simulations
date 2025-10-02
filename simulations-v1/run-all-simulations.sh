#!/bin/bash

# Comprehensive Distributed Systems Simulation Runner
# Runs all simulation categories with both Docker and Kubernetes options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$PROJECT_ROOT/simulation-results"
PLATFORM="docker"  # Default platform
SIMULATION_CATEGORIES=()
CLEANUP_AFTER="true"

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

print_header() {
    echo -e "${PURPLE}$1${NC}"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Comprehensive Distributed Systems Simulation Runner

OPTIONS:
    --platform PLATFORM     Platform to run on (docker|kubernetes) [default: docker]
    --categories CATEGORIES  Comma-separated list of simulation categories to run
                            Available: consistency,availability,scalability,network,
                                     concurrency,state,observability,security,
                                     database,datawarehouse,microservices,cloud,all
                            [default: all]
    --no-cleanup            Don't cleanup resources after simulations
    --results-dir DIR       Directory to store results [default: ./simulation-results]
    --help                  Show this help message

EXAMPLES:
    $0                                          # Run all simulations on Docker
    $0 --platform kubernetes                   # Run all simulations on Kubernetes
    $0 --categories consistency,availability   # Run specific categories
    $0 --platform docker --no-cleanup         # Run on Docker, keep resources

SIMULATION CATEGORIES:
    consistency     - CAP theorem, Raft consensus, CRDT testing
    availability    - Fault tolerance, failover, recovery testing
    scalability     - Auto-scaling, performance, load testing
    network         - Partition tolerance, latency, packet loss
    concurrency     - Distributed locks, coordination, deadlocks
    state           - Migration, checkpointing, snapshots
    observability   - Monitoring, tracing, alerting
    security        - Authentication, encryption, compliance
    database        - ACID, sharding, replication
    datawarehouse   - ETL, analytics, real-time processing
    microservices   - Service mesh, API gateway, transactions
    cloud           - Container orchestration, infrastructure
EOF
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --platform)
                PLATFORM="$2"
                shift 2
                ;;
            --categories)
                IFS=',' read -ra SIMULATION_CATEGORIES <<< "$2"
                shift 2
                ;;
            --no-cleanup)
                CLEANUP_AFTER="false"
                shift
                ;;
            --results-dir)
                RESULTS_DIR="$2"
                shift 2
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

    # Validate platform
    if [[ "$PLATFORM" != "docker" && "$PLATFORM" != "kubernetes" ]]; then
        print_error "Invalid platform: $PLATFORM. Must be 'docker' or 'kubernetes'"
        exit 1
    fi

    # Set default categories if none specified
    if [[ ${#SIMULATION_CATEGORIES[@]} -eq 0 ]]; then
        SIMULATION_CATEGORIES=("all")
    fi

    # Expand "all" category
    if [[ " ${SIMULATION_CATEGORIES[*]} " =~ " all " ]]; then
        SIMULATION_CATEGORIES=(
            "consistency" "availability" "scalability" "network"
            "concurrency" "state" "observability" "security"
            "database" "datawarehouse" "microservices" "cloud"
        )
    fi
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    # Check Docker
    if [[ "$PLATFORM" == "docker" ]]; then
        if ! command -v docker &> /dev/null; then
            print_error "Docker is not installed"
            exit 1
        fi
        if ! command -v docker-compose &> /dev/null; then
            print_error "Docker Compose is not installed"
            exit 1
        fi
        if ! docker info &> /dev/null; then
            print_error "Docker daemon is not running"
            exit 1
        fi
    fi

    # Check Kubernetes
    if [[ "$PLATFORM" == "kubernetes" ]]; then
        if ! command -v kubectl &> /dev/null; then
            print_error "kubectl is not installed"
            exit 1
        fi
        if ! kubectl cluster-info &> /dev/null; then
            print_error "Kubernetes cluster is not accessible"
            exit 1
        fi
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi

    print_success "Prerequisites check passed"
}

# Function to setup results directory
setup_results_directory() {
    print_status "Setting up results directory: $RESULTS_DIR"
    
    mkdir -p "$RESULTS_DIR"
    
    # Create simulation metadata
    cat > "$RESULTS_DIR/simulation_metadata.json" << EOF
{
    "simulation_id": "sim_$(date +%s)",
    "start_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "platform": "$PLATFORM",
    "categories": $(printf '%s\n' "${SIMULATION_CATEGORIES[@]}" | jq -R . | jq -s .),
    "cleanup_after": $CLEANUP_AFTER,
    "results_directory": "$RESULTS_DIR"
}
EOF
}

# Function to run consistency simulations
run_consistency_simulations() {
    print_header "🧪 Running Consistency & CAP Theorem Simulations"
    
    cd "$PROJECT_ROOT"
    
    # Install Python dependencies
    pip3 install -r simulations/scripts/requirements.txt
    
    # Run consistency simulation
    python3 simulations/scripts/run-consistency-simulation.py \
        --platform "$PLATFORM" \
        --tests all
    
    # Move results
    mv consistency_simulation_report_*.json "$RESULTS_DIR/" 2>/dev/null || true
    
    print_success "Consistency simulations completed"
}

# Function to run availability simulations
run_availability_simulations() {
    print_header "🛡️ Running Availability & Fault Tolerance Simulations"
    
    if [[ "$PLATFORM" == "docker" ]]; then
        # Run Docker-based availability tests
        cd "$PROJECT_ROOT/simulations/docker/availability-simulation"
        docker-compose up -d --build
        
        # Run chaos engineering tests
        python3 ../../scripts/run-availability-tests.py --platform docker
        
        if [[ "$CLEANUP_AFTER" == "true" ]]; then
            docker-compose down -v
        fi
    else
        # Run Kubernetes-based availability tests
        kubectl apply -f "$PROJECT_ROOT/simulations/kubernetes/availability-simulation/"
        
        # Run chaos mesh experiments
        python3 "$PROJECT_ROOT/simulations/scripts/run-availability-tests.py" --platform kubernetes
        
        if [[ "$CLEANUP_AFTER" == "true" ]]; then
            kubectl delete namespace availability-simulation
        fi
    fi
    
    print_success "Availability simulations completed"
}

# Function to run scalability simulations
run_scalability_simulations() {
    print_header "📈 Running Scalability & Performance Simulations"
    
    # Run load testing and auto-scaling tests
    python3 "$PROJECT_ROOT/simulations/scripts/run-scalability-tests.py" \
        --platform "$PLATFORM" \
        --load-patterns "gradual,spike,sustained"
    
    print_success "Scalability simulations completed"
}

# Function to run network simulations
run_network_simulations() {
    print_header "🌐 Running Network Partition & Failure Simulations"
    
    # Run network chaos experiments
    python3 "$PROJECT_ROOT/simulations/scripts/run-network-tests.py" \
        --platform "$PLATFORM" \
        --scenarios "partition,latency,packet_loss,clock_skew"
    
    print_success "Network simulations completed"
}

# Function to run database simulations
run_database_simulations() {
    print_header "🗄️ Running Database Infrastructure Simulations"
    
    # Start existing microservices for database testing
    cd "$PROJECT_ROOT"
    
    if [[ "$PLATFORM" == "docker" ]]; then
        docker-compose -f infrastructure/docker-compose.yml up -d
        
        # Run database-specific tests
        python3 tests/integration/run_all_tests.py
        
        if [[ "$CLEANUP_AFTER" == "true" ]]; then
            docker-compose -f infrastructure/docker-compose.yml down -v
        fi
    else
        # Deploy to Kubernetes
        kubectl apply -f infrastructure/kubernetes/
        
        # Run tests
        python3 tests/integration/run_all_tests.py --platform kubernetes
        
        if [[ "$CLEANUP_AFTER" == "true" ]]; then
            kubectl delete namespace microservices
        fi
    fi
    
    print_success "Database simulations completed"
}

# Function to run microservices simulations
run_microservices_simulations() {
    print_header "🔧 Running Microservices Architecture Simulations"
    
    # Use existing microservices system
    cd "$PROJECT_ROOT"
    
    # Run comprehensive integration tests
    ./scripts/run-integration-tests.sh --cleanup
    
    print_success "Microservices simulations completed"
}

# Function to run cloud platform simulations
run_cloud_simulations() {
    print_header "☁️ Running Self-Hosted Cloud Platform Simulations"
    
    if [[ "$PLATFORM" == "docker" ]]; then
        # Test Docker Swarm capabilities
        python3 "$PROJECT_ROOT/simulations/scripts/run-cloud-tests.py" \
            --platform docker-swarm \
            --tests "orchestration,scaling,networking,storage"
    else
        # Test Kubernetes platform features
        python3 "$PROJECT_ROOT/simulations/scripts/run-cloud-tests.py" \
            --platform kubernetes \
            --tests "cluster-management,workload-management,storage,networking"
    fi
    
    print_success "Cloud platform simulations completed"
}

# Function to generate comprehensive report
generate_comprehensive_report() {
    print_header "📊 Generating Comprehensive Simulation Report"
    
    cd "$RESULTS_DIR"
    
    # Collect all result files
    python3 << EOF
import json
import glob
import os
from datetime import datetime

# Collect all JSON result files
result_files = glob.glob("*.json")
all_results = []

for file in result_files:
    try:
        with open(file, 'r') as f:
            data = json.load(f)
            all_results.append(data)
    except Exception as e:
        print(f"Error reading {file}: {e}")

# Generate comprehensive report
report = {
    "comprehensive_simulation_report": {
        "generated_at": datetime.utcnow().isoformat(),
        "platform": "$PLATFORM",
        "categories_tested": $(printf '%s\n' "${SIMULATION_CATEGORIES[@]}" | jq -R . | jq -s .),
        "total_simulations": len(all_results),
        "individual_results": all_results,
        "summary": {
            "total_tests": sum(len(r.get("tests", [])) for r in all_results),
            "successful_simulations": sum(1 for r in all_results if r.get("summary", {}).get("success_rate", 0) > 0.8),
            "overall_success_rate": 0.0
        }
    }
}

# Calculate overall success rate
if report["comprehensive_simulation_report"]["total_simulations"] > 0:
    report["comprehensive_simulation_report"]["summary"]["overall_success_rate"] = (
        report["comprehensive_simulation_report"]["summary"]["successful_simulations"] / 
        report["comprehensive_simulation_report"]["total_simulations"]
    )

# Save comprehensive report
with open("comprehensive_simulation_report.json", "w") as f:
    json.dump(report, f, indent=2)

print(f"📊 Comprehensive report generated with {len(all_results)} simulation results")
print(f"📈 Overall success rate: {report['comprehensive_simulation_report']['summary']['overall_success_rate']:.2%}")
EOF
    
    print_success "Comprehensive report generated: $RESULTS_DIR/comprehensive_simulation_report.json"
}

# Main execution function
main() {
    print_header "🚀 Starting Comprehensive Distributed Systems Simulations"
    echo "Platform: $PLATFORM"
    echo "Categories: ${SIMULATION_CATEGORIES[*]}"
    echo "Results Directory: $RESULTS_DIR"
    echo "Cleanup After: $CLEANUP_AFTER"
    echo ""

    # Setup
    check_prerequisites
    setup_results_directory

    # Run simulations based on selected categories
    for category in "${SIMULATION_CATEGORIES[@]}"; do
        case $category in
            consistency)
                run_consistency_simulations
                ;;
            availability)
                run_availability_simulations
                ;;
            scalability)
                run_scalability_simulations
                ;;
            network)
                run_network_simulations
                ;;
            database)
                run_database_simulations
                ;;
            microservices)
                run_microservices_simulations
                ;;
            cloud)
                run_cloud_simulations
                ;;
            *)
                print_warning "Simulation category '$category' not yet implemented, skipping..."
                ;;
        esac
    done

    # Generate comprehensive report
    generate_comprehensive_report

    print_header "🎉 All Simulations Completed Successfully!"
    echo ""
    echo "Results available in: $RESULTS_DIR"
    echo "Comprehensive report: $RESULTS_DIR/comprehensive_simulation_report.json"
    
    if [[ "$CLEANUP_AFTER" == "false" ]]; then
        print_warning "Resources were not cleaned up. Remember to clean them manually."
    fi
}

# Parse arguments and run main function
parse_arguments "$@"
main
