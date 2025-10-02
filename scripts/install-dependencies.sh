#!/bin/bash

# Installation script for microservices development environment
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GO_VERSION="1.21.5"
K6_VERSION="0.47.0"

echo -e "${BLUE}🚀 Microservices Development Environment Setup${NC}"
echo "=================================================="

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}$1${NC}"
    echo "$(printf '=%.0s' {1..50})"
}

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Go
install_go() {
    print_section "📦 Installing Go"
    
    if command_exists go; then
        local current_version=$(go version | awk '{print $3}' | sed 's/go//')
        echo -e "${GREEN}✅ Go is already installed: $current_version${NC}"
        
        # Check if version is sufficient
        if [[ "$current_version" < "$GO_VERSION" ]]; then
            echo -e "${YELLOW}⚠️  Go version $current_version is older than recommended $GO_VERSION${NC}"
            echo -e "${YELLOW}Consider upgrading for best compatibility${NC}"
        fi
        return 0
    fi
    
    local os=$(detect_os)
    local arch=$(uname -m)
    
    # Convert architecture names
    case $arch in
        x86_64) arch="amd64" ;;
        arm64|aarch64) arch="arm64" ;;
        *) echo -e "${RED}❌ Unsupported architecture: $arch${NC}"; exit 1 ;;
    esac
    
    case $os in
        "linux")
            local go_package="go${GO_VERSION}.linux-${arch}.tar.gz"
            ;;
        "macos")
            local go_package="go${GO_VERSION}.darwin-${arch}.tar.gz"
            ;;
        *)
            echo -e "${RED}❌ Unsupported OS for automatic Go installation: $os${NC}"
            echo -e "${YELLOW}Please install Go manually from https://golang.org/dl/${NC}"
            exit 1
            ;;
    esac
    
    echo -e "${BLUE}Downloading Go $GO_VERSION...${NC}"
    curl -L "https://golang.org/dl/$go_package" -o "/tmp/$go_package"
    
    echo -e "${BLUE}Installing Go...${NC}"
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf "/tmp/$go_package"
    
    # Add to PATH if not already there
    if ! echo "$PATH" | grep -q "/usr/local/go/bin"; then
        echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
        echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.zshrc 2>/dev/null || true
        export PATH=$PATH:/usr/local/go/bin
    fi
    
    rm "/tmp/$go_package"
    echo -e "${GREEN}✅ Go $GO_VERSION installed successfully${NC}"
}

# Function to install Docker
install_docker() {
    print_section "🐳 Installing Docker"
    
    if command_exists docker; then
        echo -e "${GREEN}✅ Docker is already installed: $(docker --version)${NC}"
        
        # Check if Docker is running
        if docker info >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Docker daemon is running${NC}"
        else
            echo -e "${YELLOW}⚠️  Docker daemon is not running. Please start Docker.${NC}"
        fi
        return 0
    fi
    
    local os=$(detect_os)
    
    case $os in
        "linux")
            echo -e "${BLUE}Installing Docker on Linux...${NC}"
            curl -fsSL https://get.docker.com -o get-docker.sh
            sudo sh get-docker.sh
            sudo usermod -aG docker $USER
            rm get-docker.sh
            echo -e "${YELLOW}⚠️  Please log out and log back in to use Docker without sudo${NC}"
            ;;
        "macos")
            echo -e "${YELLOW}⚠️  Please install Docker Desktop for Mac from:${NC}"
            echo -e "${BLUE}https://docs.docker.com/desktop/install/mac-install/${NC}"
            echo -e "${YELLOW}Then restart this script.${NC}"
            exit 1
            ;;
        *)
            echo -e "${RED}❌ Unsupported OS for automatic Docker installation: $os${NC}"
            echo -e "${YELLOW}Please install Docker manually${NC}"
            exit 1
            ;;
    esac
}

# Function to install Docker Compose
install_docker_compose() {
    print_section "🐙 Installing Docker Compose"
    
    if command_exists docker-compose; then
        echo -e "${GREEN}✅ Docker Compose is already installed: $(docker-compose --version)${NC}"
        return 0
    fi
    
    # Check if it's available as docker compose (newer versions)
    if docker compose version >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Docker Compose (plugin) is already installed${NC}"
        return 0
    fi
    
    local os=$(detect_os)
    local arch=$(uname -m)
    
    case $arch in
        x86_64) arch="x86_64" ;;
        arm64|aarch64) arch="aarch64" ;;
        *) echo -e "${RED}❌ Unsupported architecture: $arch${NC}"; exit 1 ;;
    esac
    
    case $os in
        "linux")
            local compose_url="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${arch}"
            ;;
        "macos")
            local compose_url="https://github.com/docker/compose/releases/latest/download/docker-compose-darwin-${arch}"
            ;;
        *)
            echo -e "${RED}❌ Unsupported OS: $os${NC}"
            exit 1
            ;;
    esac
    
    echo -e "${BLUE}Installing Docker Compose...${NC}"
    sudo curl -L "$compose_url" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    echo -e "${GREEN}✅ Docker Compose installed successfully${NC}"
}

# Function to install K6
install_k6() {
    print_section "⚡ Installing K6"
    
    if command_exists k6; then
        echo -e "${GREEN}✅ K6 is already installed: $(k6 version)${NC}"
        return 0
    fi
    
    local os=$(detect_os)
    
    case $os in
        "linux")
            echo -e "${BLUE}Installing K6 on Linux...${NC}"
            sudo gpg -k
            sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
            echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
            sudo apt-get update
            sudo apt-get install k6
            ;;
        "macos")
            if command_exists brew; then
                echo -e "${BLUE}Installing K6 via Homebrew...${NC}"
                brew install k6
            else
                echo -e "${YELLOW}⚠️  Homebrew not found. Installing K6 manually...${NC}"
                local arch=$(uname -m)
                case $arch in
                    x86_64) arch="amd64" ;;
                    arm64) arch="arm64" ;;
                    *) echo -e "${RED}❌ Unsupported architecture: $arch${NC}"; exit 1 ;;
                esac
                
                local k6_package="k6-v${K6_VERSION}-macos-${arch}.zip"
                curl -L "https://github.com/grafana/k6/releases/download/v${K6_VERSION}/$k6_package" -o "/tmp/$k6_package"
                unzip "/tmp/$k6_package" -d /tmp/
                sudo mv "/tmp/k6-v${K6_VERSION}-macos-${arch}/k6" /usr/local/bin/
                rm -rf "/tmp/$k6_package" "/tmp/k6-v${K6_VERSION}-macos-${arch}"
            fi
            ;;
        *)
            echo -e "${RED}❌ Unsupported OS for K6 installation: $os${NC}"
            echo -e "${YELLOW}Please install K6 manually from https://k6.io/docs/getting-started/installation/${NC}"
            exit 1
            ;;
    esac
    
    echo -e "${GREEN}✅ K6 installed successfully${NC}"
}

# Function to install additional tools
install_additional_tools() {
    print_section "🛠️  Installing Additional Tools"
    
    local os=$(detect_os)
    
    # Install curl if not present
    if ! command_exists curl; then
        echo -e "${BLUE}Installing curl...${NC}"
        case $os in
            "linux")
                sudo apt-get update && sudo apt-get install -y curl
                ;;
            "macos")
                echo -e "${YELLOW}⚠️  curl should be pre-installed on macOS${NC}"
                ;;
        esac
    else
        echo -e "${GREEN}✅ curl is already installed${NC}"
    fi
    
    # Install jq for JSON processing
    if ! command_exists jq; then
        echo -e "${BLUE}Installing jq...${NC}"
        case $os in
            "linux")
                sudo apt-get update && sudo apt-get install -y jq
                ;;
            "macos")
                if command_exists brew; then
                    brew install jq
                else
                    echo -e "${YELLOW}⚠️  Please install jq manually or install Homebrew${NC}"
                fi
                ;;
        esac
    else
        echo -e "${GREEN}✅ jq is already installed${NC}"
    fi
    
    # Install make if not present
    if ! command_exists make; then
        echo -e "${BLUE}Installing make...${NC}"
        case $os in
            "linux")
                sudo apt-get update && sudo apt-get install -y build-essential
                ;;
            "macos")
                if ! command_exists xcode-select; then
                    echo -e "${YELLOW}⚠️  Please install Xcode Command Line Tools:${NC}"
                    echo -e "${BLUE}xcode-select --install${NC}"
                fi
                ;;
        esac
    else
        echo -e "${GREEN}✅ make is already installed${NC}"
    fi
}

# Function to setup Go modules
setup_go_modules() {
    print_section "📦 Setting up Go modules"
    
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
        "sharding-proxy"
    )
    
    for service in "${services[@]}"; do
        local service_path="services/$service"
        
        if [ -d "$service_path" ]; then
            echo -e "${BLUE}Setting up Go modules for $service...${NC}"
            cd "$service_path"
            
            if [ -f "go.mod" ]; then
                go mod tidy
                echo -e "${GREEN}✅ Go modules updated for $service${NC}"
            else
                echo -e "${YELLOW}⚠️  No go.mod found for $service${NC}"
            fi
            
            cd - > /dev/null
        fi
    done
}

# Function to verify installation
verify_installation() {
    print_section "✅ Verifying Installation"
    
    local all_good=true
    
    # Check Go
    if command_exists go; then
        echo -e "${GREEN}✅ Go: $(go version)${NC}"
    else
        echo -e "${RED}❌ Go not found${NC}"
        all_good=false
    fi
    
    # Check Docker
    if command_exists docker; then
        echo -e "${GREEN}✅ Docker: $(docker --version)${NC}"
        if docker info >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Docker daemon is running${NC}"
        else
            echo -e "${YELLOW}⚠️  Docker daemon is not running${NC}"
        fi
    else
        echo -e "${RED}❌ Docker not found${NC}"
        all_good=false
    fi
    
    # Check Docker Compose
    if command_exists docker-compose || docker compose version >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Docker Compose is available${NC}"
    else
        echo -e "${RED}❌ Docker Compose not found${NC}"
        all_good=false
    fi
    
    # Check K6
    if command_exists k6; then
        echo -e "${GREEN}✅ K6: $(k6 version)${NC}"
    else
        echo -e "${RED}❌ K6 not found${NC}"
        all_good=false
    fi
    
    # Check additional tools
    if command_exists curl; then
        echo -e "${GREEN}✅ curl is available${NC}"
    else
        echo -e "${YELLOW}⚠️  curl not found${NC}"
    fi
    
    if command_exists jq; then
        echo -e "${GREEN}✅ jq is available${NC}"
    else
        echo -e "${YELLOW}⚠️  jq not found${NC}"
    fi
    
    if command_exists make; then
        echo -e "${GREEN}✅ make is available${NC}"
    else
        echo -e "${YELLOW}⚠️  make not found${NC}"
    fi
    
    if $all_good; then
        echo -e "\n${GREEN}🎉 All required dependencies are installed!${NC}"
        echo -e "${BLUE}You can now run:${NC}"
        echo -e "  ${YELLOW}make help${NC}                 - See available commands"
        echo -e "  ${YELLOW}make examples${NC}             - Try minimal examples"
        echo -e "  ${YELLOW}./scripts/run-tests.sh${NC}    - Run test suite"
        echo -e "  ${YELLOW}make basic-saga${NC}           - Start basic saga demo"
    else
        echo -e "\n${RED}❌ Some dependencies are missing. Please install them manually.${NC}"
        exit 1
    fi
}

# Main execution
main() {
    local os=$(detect_os)
    echo -e "${BLUE}Detected OS: $os${NC}"
    
    if [ "$os" = "unknown" ]; then
        echo -e "${RED}❌ Unsupported operating system${NC}"
        exit 1
    fi
    
    # Install dependencies
    install_go
    install_docker
    install_docker_compose
    install_k6
    install_additional_tools
    
    # Setup Go modules
    setup_go_modules
    
    # Verify everything is working
    verify_installation
    
    echo -e "\n${GREEN}🎉 Development environment setup completed!${NC}"
}

# Run main function
main "$@"
