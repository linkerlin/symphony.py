#!/bin/bash
# Symphony 安装脚本
# 用法: curl -sSL https://raw.githubusercontent.com/openai/symphony/main/symphony.py/install.sh | bash

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 配置
REPO_URL="https://github.com/openai/symphony.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.symphony}"
PYTHON_CMD="${PYTHON_CMD:-python3}"

# 打印函数
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

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 检查 Python 版本
check_python() {
    print_info "检查 Python 版本..."
    
    if ! command_exists "$PYTHON_CMD"; then
        print_error "未找到 Python 3。请安装 Python 3.12 或更高版本。"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]); then
        print_error "需要 Python 3.12+，当前版本为 $PYTHON_VERSION"
        exit 1
    fi
    
    print_success "找到 Python $PYTHON_VERSION"
}

# 检查 pip
check_pip() {
    print_info "检查 pip..."
    
    if ! command_exists pip3 && ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
        print_error "未找到 pip。请安装 pip。"
        exit 1
    fi
    
    print_success "找到 pip"
}

# 通过 pip 安装
install_via_pip() {
    print_info "通过 pip 安装 Symphony..."
    
    if command_exists pip3; then
        pip3 install symphony
    else
        $PYTHON_CMD -m pip install symphony
    fi
    
    print_success "Symphony 安装成功"
}

# 从源码安装
install_from_source() {
    print_info "从源码安装 Symphony..."
    
    # 克隆仓库
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "目录 $INSTALL_DIR 已存在，正在更新..."
        cd "$INSTALL_DIR"
        git pull origin main
    else
        print_info "正在克隆仓库..."
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR/symphony.py"
    fi
    
    # 安装依赖
    print_info "正在安装依赖..."
    $PYTHON_CMD -m pip install -e .
    
    print_success "从源码安装 Symphony 成功"
}

# 设置 shell 自动补全
setup_completion() {
    print_info "设置 shell 自动补全..."
    
    SHELL_NAME=$(basename "$SHELL")
    
    case "$SHELL_NAME" in
        bash)
            COMPLETION_FILE="$HOME/.bash_completion"
            symphony --show-completion bash >> "$COMPLETION_FILE" 2>/dev/null || true
            print_success "Bash 自动补全已添加到 $COMPLETION_FILE"
            ;;
        zsh)
            COMPLETION_DIR="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/completions"
            mkdir -p "$COMPLETION_DIR"
            symphony --show-completion zsh > "$COMPLETION_DIR/_symphony" 2>/dev/null || true
            print_success "Zsh 自动补全已添加"
            ;;
        fish)
            COMPLETION_DIR="$HOME/.config/fish/completions"
            mkdir -p "$COMPLETION_DIR"
            symphony --show-completion fish > "$COMPLETION_DIR/symphony.fish" 2>/dev/null || true
            print_success "Fish 自动补全已添加"
            ;;
        *)
            print_warning "不支持 $SHELL_NAME 的自动补全"
            ;;
    esac
}

# 创建包装脚本
create_wrapper() {
    print_info "创建包装脚本..."
    
    WRAPPER_DIR="$HOME/.local/bin"
    mkdir -p "$WRAPPER_DIR"
    
    cat > "$WRAPPER_DIR/symphony" << 'EOF'
#!/bin/bash
# Symphony 包装脚本

# 如果存在虚拟环境则激活
if [ -d "$HOME/.symphony/.venv" ]; then
    source "$HOME/.symphony/.venv/bin/activate"
fi

# 运行 symphony
exec symphony "$@"
EOF
    
    chmod +x "$WRAPPER_DIR/symphony"
    
    # 如果需要则添加到 PATH
    if [[ ":$PATH:" != *":$WRAPPER_DIR:"* ]]; then
        print_info "正在将 $WRAPPER_DIR 添加到 PATH"
        
        case "$SHELL_NAME" in
            bash)
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
                ;;
            zsh)
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
                ;;
        esac
    fi
    
    print_success "包装脚本已创建"
}

# 打印安装后消息
print_post_install() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Symphony 安装成功！🎼${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo ""
    echo "快速开始："
    echo "  1. symphony init          # 运行设置向导"
    echo "  2. symphony doctor        # 检查环境"
    echo "  3. symphony run           # 启动编排器"
    echo ""
    echo "文档："
    echo "  https://github.com/openai/symphony/blob/main/symphony.py/README.md"
    echo ""
    
    if command_exists symphony; then
        VERSION=$(symphony --version 2>/dev/null || echo "unknown")
        print_success "已安装: $VERSION"
    fi
}

# 主安装流程
main() {
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Symphony 安装${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo ""
    
    # 解析参数
    INSTALL_METHOD="${1:-pip}"
    
    # 前置检查
    check_python
    check_pip
    
    # 安装
    case "$INSTALL_METHOD" in
        pip)
            install_via_pip
            ;;
        source)
            install_from_source
            ;;
        *)
            print_error "未知的安装方式: $INSTALL_METHOD"
            echo "用法: $0 [pip|source]"
            exit 1
            ;;
    esac
    
    # 安装后
    setup_completion || true
    print_post_install
}

# 运行主流程
main "$@"
