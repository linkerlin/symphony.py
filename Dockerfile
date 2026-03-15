# Symphony - Agent 编排系统
# 多阶段构建，用于生产就绪容器

FROM python:3.12-slim AS builder

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 用于更快的 Python 包管理
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 首先复制依赖文件以获得更好的缓存效果
COPY pyproject.toml README.md ./

# 创建虚拟环境并安装依赖
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv pip install -e .

# 生产阶段
FROM python:3.12-slim AS production

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ssh-client \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd -r symphony && useradd -r -g symphony -d /app symphony

WORKDIR /app

# 从构建阶段复制虚拟环境
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# 复制应用程序代码
COPY src/ /app/src/
COPY README.md LICENSE ./

# 以可编辑模式安装（支持开发覆盖）
RUN pip install -e . --no-deps

# 创建工作空间和日志目录
RUN mkdir -p /app/workspaces /app/logs && chown -R symphony:symphony /app

# 切换到非 root 用户
USER symphony

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import symphony; print('OK')" || exit 1

# 默认环境
ENV SYMPHONY_WORKSPACE_ROOT=/app/workspaces
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

ENTRYPOINT ["symphony"]
CMD ["--help"]

# 开发阶段
FROM production AS development

USER root

# 安装开发依赖
RUN pip install -e ".[dev]"

# 安装额外的开发工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    htop \
    && rm -rf /var/lib/apt/lists/*

USER symphony

# 开发环境默认使用 bash
CMD ["/bin/bash"]
