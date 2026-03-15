# Symphony - Agent Orchestration System
# Multi-stage build for production-ready container

FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml README.md ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv pip install -e .

# Production stage
FROM python:3.12-slim AS production

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ssh-client \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r symphony && useradd -r -g symphony -d /app symphony

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ /app/src/
COPY README.md LICENSE ./

# Install in editable mode (for development override support)
RUN pip install -e . --no-deps

# Create directories for workspaces and logs
RUN mkdir -p /app/workspaces /app/logs && chown -R symphony:symphony /app

# Switch to non-root user
USER symphony

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import symphony; print('OK')" || exit 1

# Default environment
ENV SYMPHONY_WORKSPACE_ROOT=/app/workspaces
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

ENTRYPOINT ["symphony"]
CMD ["--help"]

# Development stage
FROM production AS development

USER root

# Install development dependencies
RUN pip install -e ".[dev]"

# Install additional dev tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    htop \
    && rm -rf /var/lib/apt/lists/*

USER symphony

# Default to bash for development
CMD ["/bin/bash"]
