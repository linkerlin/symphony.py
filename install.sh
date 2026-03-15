#!/bin/bash
# Symphony Installation Script
# Usage: curl -sSL https://raw.githubusercontent.com/openai/symphony/main/symphony.py/install.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/openai/symphony.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.symphony}"
PYTHON_CMD="${PYTHON_CMD:-python3}"

# Print functions
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python version
check_python() {
    print_info "Checking Python version..."
    
    if ! command_exists "$PYTHON_CMD"; then
        print_error "Python 3 not found. Please install Python 3.12 or later."
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]); then
        print_error "Python 3.12+ required, found $PYTHON_VERSION"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION found"
}

# Check pip
check_pip() {
    print_info "Checking pip..."
    
    if ! command_exists pip3 && ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
        print_error "pip not found. Please install pip."
        exit 1
    fi
    
    print_success "pip found"
}

# Install via pip
install_via_pip() {
    print_info "Installing Symphony via pip..."
    
    if command_exists pip3; then
        pip3 install symphony
    else
        $PYTHON_CMD -m pip install symphony
    fi
    
    print_success "Symphony installed successfully"
}

# Install from source
install_from_source() {
    print_info "Installing Symphony from source..."
    
    # Clone repository
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Directory $INSTALL_DIR exists, updating..."
        cd "$INSTALL_DIR"
        git pull origin main
    else
        print_info "Cloning repository..."
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR/symphony.py"
    fi
    
    # Install dependencies
    print_info "Installing dependencies..."
    $PYTHON_CMD -m pip install -e .
    
    print_success "Symphony installed from source"
}

# Setup shell completion
setup_completion() {
    print_info "Setting up shell completion..."
    
    SHELL_NAME=$(basename "$SHELL")
    
    case "$SHELL_NAME" in
        bash)
            COMPLETION_FILE="$HOME/.bash_completion"
            symphony --show-completion bash >> "$COMPLETION_FILE" 2>/dev/null || true
            print_success "Bash completion added to $COMPLETION_FILE"
            ;;
        zsh)
            COMPLETION_DIR="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/completions"
            mkdir -p "$COMPLETION_DIR"
            symphony --show-completion zsh > "$COMPLETION_DIR/_symphony" 2>/dev/null || true
            print_success "Zsh completion added"
            ;;
        fish)
            COMPLETION_DIR="$HOME/.config/fish/completions"
            mkdir -p "$COMPLETION_DIR"
            symphony --show-completion fish > "$COMPLETION_DIR/symphony.fish" 2>/dev/null || true
            print_success "Fish completion added"
            ;;
        *)
            print_warning "Shell completion not supported for $SHELL_NAME"
            ;;
    esac
}

# Create wrapper script
create_wrapper() {
    print_info "Creating wrapper script..."
    
    WRAPPER_DIR="$HOME/.local/bin"
    mkdir -p "$WRAPPER_DIR"
    
    cat > "$WRAPPER_DIR/symphony" << 'EOF'
#!/bin/bash
# Symphony wrapper script

# Activate virtual environment if it exists
if [ -d "$HOME/.symphony/.venv" ]; then
    source "$HOME/.symphony/.venv/bin/activate"
fi

# Run symphony
exec symphony "$@"
EOF
    
    chmod +x "$WRAPPER_DIR/symphony"
    
    # Add to PATH if needed
    if [[ ":$PATH:" != *":$WRAPPER_DIR:"* ]]; then
        print_info "Adding $WRAPPER_DIR to PATH"
        
        case "$SHELL_NAME" in
            bash)
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
                ;;
            zsh)
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
                ;;
        esac
    fi
    
    print_success "Wrapper script created"
}

# Print post-installation message
print_post_install() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Symphony installed successfully! 🎼${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo ""
    echo "Quick start:"
    echo "  1. symphony init          # Run setup wizard"
    echo "  2. symphony doctor        # Check environment"
    echo "  3. symphony run           # Start orchestrator"
    echo ""
    echo "Documentation:"
    echo "  https://github.com/openai/symphony/blob/main/symphony.py/README.md"
    echo ""
    
    if command_exists symphony; then
        VERSION=$(symphony --version 2>/dev/null || echo "unknown")
        print_success "Installed: $VERSION"
    fi
}

# Main installation
main() {
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Symphony Installation${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo ""
    
    # Parse arguments
    INSTALL_METHOD="${1:-pip}"
    
    # Pre-flight checks
    check_python
    check_pip
    
    # Install
    case "$INSTALL_METHOD" in
        pip)
            install_via_pip
            ;;
        source)
            install_from_source
            ;;
        *)
            print_error "Unknown install method: $INSTALL_METHOD"
            echo "Usage: $0 [pip|source]"
            exit 1
            ;;
    esac
    
    # Post-install
    setup_completion || true
    print_post_install
}

# Run main
main "$@"
