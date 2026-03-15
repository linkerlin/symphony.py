# Symphony Makefile
# 开发和部署的快速命令

.PHONY: help install install-dev test lint format clean docker-build docker-run

# 默认目标
help:
	@echo "Symphony - 可用命令："
	@echo ""
	@echo "  make install       - 通过 pip 安装 Symphony"
	@echo "  make install-dev   - 以开发模式安装"
	@echo "  make test          - 运行测试"
	@echo "  make lint          - 运行代码检查"
	@echo "  make format        - 格式化代码"
	@echo "  make clean         - 清理构建产物"
	@echo ""
	@echo "Docker 命令："
	@echo "  make docker-build  - 构建 Docker 镜像"
	@echo "  make docker-run    - 使用 Docker Compose 运行"
	@echo "  make docker-stop   - 停止 Docker 容器"
	@echo ""
	@echo "开发命令："
	@echo "  make init          - 初始化 Symphony 配置"
	@echo "  make doctor        - 运行环境诊断"
	@echo "  make run           - 运行 Symphony 编排器"
	@echo ""

# 安装
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# 测试
test:
	pytest -v -m "not llm and not slow"

test-all:
	pytest -v

test-llm:
	pytest -v -m llm

test-unit:
	pytest -v -m "not llm and not slow and not integration"

test-integration:
	pytest -v -m integration

test-cov:
	pytest --cov=symphony --cov-report=html --cov-report=term

test-fast:
	pytest -v -m "not llm and not slow" --timeout=10 -x

test-parallel:
	pytest -v -m "not llm and not slow" -n auto

# 代码检查和格式化
lint:
	ruff check src tests
	mypy src

format:
	ruff check --fix src tests
	ruff format src tests

# 清理
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Docker 命令
docker-build:
	docker-compose build

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f symphony

# 开发工作流
init:
	@python -m symphony.cli init

doctor:
	@python -m symphony.cli doctor

run:
	@python -m symphony.cli run WORKFLOW.md --verbose

run-dashboard:
	@python -m symphony.cli run WORKFLOW.md --dashboard

validate:
	@python -m symphony.cli validate WORKFLOW.md

# 发布
build:
	python -m build

upload:
	python -m twine upload dist/*
