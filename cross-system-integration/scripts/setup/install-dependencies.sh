#!/bin/bash

# Cross-System Integration - Dependency Installation Script
# This script installs all required dependencies for the cross-system integration platform

set -e  # Exit on any error

echo "🚀 Cross-System Integration - Installing Dependencies"
echo "=================================================="

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

# Check if running on supported OS
check_os() {
    print_header "Checking Operating System"
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        print_status "Detected Linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        print_status "Detected macOS"
    else
        print_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install Docker and Docker Compose
install_docker() {
    print_header "Installing Docker and Docker Compose"
    
    if command_exists docker; then
        print_status "Docker is already installed"
        docker --version
    else
        print_status "Installing Docker..."
        
        if [[ "$OS" == "linux" ]]; then
            # Install Docker on Linux
            curl -fsSL https://get.docker.com -o get-docker.sh
            sudo sh get-docker.sh
            sudo usermod -aG docker $USER
            rm get-docker.sh
            print_warning "Please log out and log back in for Docker group changes to take effect"
        elif [[ "$OS" == "macos" ]]; then
            print_error "Please install Docker Desktop for Mac from https://docs.docker.com/desktop/mac/install/"
            exit 1
        fi
    fi
    
    if command_exists docker-compose; then
        print_status "Docker Compose is already installed"
        docker-compose --version
    else
        print_status "Installing Docker Compose..."
        
        if [[ "$OS" == "linux" ]]; then
            sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
            sudo chmod +x /usr/local/bin/docker-compose
        elif [[ "$OS" == "macos" ]]; then
            # Docker Compose comes with Docker Desktop on macOS
            print_status "Docker Compose comes with Docker Desktop"
        fi
    fi
}

# Install Go
install_go() {
    print_header "Installing Go"
    
    if command_exists go; then
        GO_VERSION=$(go version | awk '{print $3}' | sed 's/go//')
        print_status "Go is already installed (version: $GO_VERSION)"
        
        # Check if version is 1.19 or higher
        if [[ $(echo "$GO_VERSION 1.19" | tr " " "\n" | sort -V | head -n1) == "1.19" ]]; then
            print_status "Go version is compatible"
        else
            print_warning "Go version $GO_VERSION may be too old. Recommended: 1.19+"
        fi
    else
        print_status "Installing Go..."
        
        GO_VERSION="1.21.5"
        if [[ "$OS" == "linux" ]]; then
            wget https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz
            sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz
            rm go${GO_VERSION}.linux-amd64.tar.gz
            
            # Add to PATH
            echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
            export PATH=$PATH:/usr/local/go/bin
        elif [[ "$OS" == "macos" ]]; then
            wget https://go.dev/dl/go${GO_VERSION}.darwin-amd64.tar.gz
            sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go${GO_VERSION}.darwin-amd64.tar.gz
            rm go${GO_VERSION}.darwin-amd64.tar.gz
            
            # Add to PATH
            echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.zshrc
            export PATH=$PATH:/usr/local/go/bin
        fi
        
        print_status "Go installed successfully"
    fi
}

# Install Python and pip
install_python() {
    print_header "Installing Python"
    
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        print_status "Python3 is already installed (version: $PYTHON_VERSION)"
        
        # Check if version is 3.9 or higher
        if [[ $(echo "$PYTHON_VERSION 3.9" | tr " " "\n" | sort -V | head -n1) == "3.9" ]]; then
            print_status "Python version is compatible"
        else
            print_warning "Python version $PYTHON_VERSION may be too old. Recommended: 3.9+"
        fi
    else
        print_status "Installing Python3..."
        
        if [[ "$OS" == "linux" ]]; then
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv
        elif [[ "$OS" == "macos" ]]; then
            # Check if Homebrew is installed
            if command_exists brew; then
                brew install python@3.9
            else
                print_error "Please install Homebrew first: https://brew.sh/"
                exit 1
            fi
        fi
    fi
    
    # Install pip if not available
    if ! command_exists pip3; then
        print_status "Installing pip3..."
        curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
        python3 get-pip.py
        rm get-pip.py
    fi
    
    # Upgrade pip
    print_status "Upgrading pip..."
    python3 -m pip install --upgrade pip
}

# Install Node.js and npm
install_nodejs() {
    print_header "Installing Node.js"
    
    if command_exists node; then
        NODE_VERSION=$(node --version | sed 's/v//')
        print_status "Node.js is already installed (version: $NODE_VERSION)"
        
        # Check if version is 18 or higher
        if [[ $(echo "$NODE_VERSION 18.0.0" | tr " " "\n" | sort -V | head -n1) == "18.0.0" ]]; then
            print_status "Node.js version is compatible"
        else
            print_warning "Node.js version $NODE_VERSION may be too old. Recommended: 18+"
        fi
    else
        print_status "Installing Node.js..."
        
        if [[ "$OS" == "linux" ]]; then
            curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
            sudo apt-get install -y nodejs
        elif [[ "$OS" == "macos" ]]; then
            if command_exists brew; then
                brew install node@18
            else
                print_error "Please install Homebrew first: https://brew.sh/"
                exit 1
            fi
        fi
    fi
    
    # Install global npm packages
    print_status "Installing global npm packages..."
    npm install -g k6
}

# Install Python dependencies
install_python_deps() {
    print_header "Installing Python Dependencies"
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        print_status "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    print_status "Activating virtual environment..."
    source venv/bin/activate
    
    # Install dependencies for each Python service
    services=("intelligent-orchestrator" "chatops-engine")
    
    for service in "${services[@]}"; do
        if [ -f "services/$service/requirements.txt" ]; then
            print_status "Installing dependencies for $service..."
            pip install -r "services/$service/requirements.txt"
        else
            print_warning "requirements.txt not found for $service"
        fi
    done
    
    # Install test dependencies
    if [ -f "requirements-test.txt" ]; then
        print_status "Installing test dependencies..."
        pip install -r requirements-test.txt
    fi
    
    print_status "Python dependencies installed successfully"
}

# Install Go dependencies
install_go_deps() {
    print_header "Installing Go Dependencies"
    
    # Install dependencies for Go services
    if [ -d "services/event-bus" ]; then
        print_status "Installing dependencies for event-bus..."
        cd services/event-bus
        go mod tidy
        go mod download
        cd ../..
    fi
    
    print_status "Go dependencies installed successfully"
}

# Create necessary directories
create_directories() {
    print_header "Creating Directories"
    
    directories=(
        "logs"
        "data"
        "models"
        "cache"
        "tmp"
    )
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_status "Created directory: $dir"
        fi
    done
}

# Set up environment files
setup_environment() {
    print_header "Setting Up Environment"
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        print_status "Creating .env file..."
        cat > .env << EOF
# Cross-System Integration Environment Configuration

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Kafka Configuration
KAFKA_BROKERS=localhost:9092

# Service URLs
EVENT_BUS_URL=http://localhost:8090
ORCHESTRATOR_URL=http://localhost:8091
CHATOPS_URL=http://localhost:8092

# Monitoring
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000

# Logging
LOG_LEVEL=info

# Development
ENVIRONMENT=development
EOF
        print_status ".env file created"
    else
        print_status ".env file already exists"
    fi
}

# Verify installation
verify_installation() {
    print_header "Verifying Installation"
    
    # Check Docker
    if command_exists docker && command_exists docker-compose; then
        print_status "✅ Docker and Docker Compose are installed"
    else
        print_error "❌ Docker or Docker Compose is missing"
    fi
    
    # Check Go
    if command_exists go; then
        print_status "✅ Go is installed ($(go version | awk '{print $3}'))"
    else
        print_error "❌ Go is missing"
    fi
    
    # Check Python
    if command_exists python3; then
        print_status "✅ Python3 is installed ($(python3 --version | awk '{print $2}'))"
    else
        print_error "❌ Python3 is missing"
    fi
    
    # Check Node.js
    if command_exists node; then
        print_status "✅ Node.js is installed ($(node --version))"
    else
        print_error "❌ Node.js is missing"
    fi
    
    # Check k6
    if command_exists k6; then
        print_status "✅ k6 is installed ($(k6 version | head -n1))"
    else
        print_error "❌ k6 is missing"
    fi
}

# Main installation process
main() {
    print_header "Starting Dependency Installation"
    
    check_os
    install_docker
    install_go
    install_python
    install_nodejs
    create_directories
    setup_environment
    install_python_deps
    install_go_deps
    verify_installation
    
    print_header "Installation Complete"
    print_status "All dependencies have been installed successfully!"
    print_status ""
    print_status "Next steps:"
    print_status "1. Start the infrastructure: docker-compose up -d"
    print_status "2. Run the services: ./scripts/deployment/deploy-all-services.sh"
    print_status "3. Run tests: ./scripts/testing/run-integration-tests.sh"
    print_status ""
    print_warning "Note: If you installed Docker on Linux, please log out and log back in"
    print_warning "for Docker group changes to take effect."
}

# Run main function
main "$@"
