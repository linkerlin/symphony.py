# Symphony 快速入门指南

在几分钟内启动并运行 Symphony。

## 安装

### 方式 1: pip（推荐）

```bash
pip install symphony
```

### 方式 2: 从源码安装

```bash
git clone https://github.com/openai/symphony.git
cd symphony/symphony.py
pip install -e .
```

### 方式 3: Docker

```bash
# 克隆仓库
git clone https://github.com/openai/symphony.git
cd symphony/symphony.py

# 使用 Docker Compose 运行
docker-compose up -d
```

## 一分钟设置

### 1. 初始化配置

```bash
symphony init
```

此交互式向导将：
- 询问您首选的 LLM 供应商（OpenAI、Anthropic、DeepSeek、Gemini）
- 配置您的 API 密钥
- 设置 Linear 集成
- 生成 `WORKFLOW.md` 和 `.env` 文件

### 2. 验证设置

```bash
symphony doctor
```

检查以下连接：
- LLM 供应商 API
- Linear API
- 系统要求

### 3. 运行 Symphony

```bash
# 基本运行
symphony run WORKFLOW.md

# 带终端仪表板
symphony run WORKFLOW.md --dashboard

# 带详细日志
symphony run WORKFLOW.md --verbose
```

## 手动设置（替代方式）

如果您更喜欢手动配置：

### 1. 创建 `WORKFLOW.md`

```yaml
---
symphony:
  version: "1.0"
  
  settings:
    llm:
      provider: openai
      model: gpt-4
      temperature: 0.7
    
    tracker:
      kind: linear
      project_slug: your-project
      active_states: ["Todo", "In Progress"]
      terminal_states: ["Done"]
    
    workspace:
      root: ./workspaces
      max_concurrent_agents: 3

  prompt: |
    处理 Linear 问题 {{identifier}}: {{title}}
    {{description}}
---
```

### 2. 创建 `.env`

```bash
OPENAI_API_KEY=sk-...
LINEAR_API_KEY=lin_api_...
LINEAR_PROJECT_SLUG=your-project
```

### 3. 验证并运行

```bash
symphony validate WORKFLOW.md
symphony run WORKFLOW.md
```

## 环境变量

### LLM 供应商

| 变量 | 供应商 | 必需 |
|----------|----------|----------|
| `OPENAI_API_KEY` | OpenAI | 使用 OpenAI 时必需 |
| `OPENAI_BASE_URL` | OpenAI | 否（默认为 api.openai.com） |
| `OPENAI_MODEL` | OpenAI | 否（默认为 gpt-4） |
| `ANTHROPIC_API_KEY` | Anthropic | 使用 Anthropic 时必需 |
| `ANTHROPIC_MODEL` | Anthropic | 否（默认为 claude-3-sonnet） |
| `DEEPSEEK_API_KEY` | DeepSeek | 使用 DeepSeek 时必需 |
| `GEMINI_API_KEY` | Gemini | 使用 Gemini 时必需 |

### Linear 集成

| 变量 | 必需 | 描述 |
|----------|----------|-------------|
| `LINEAR_API_KEY` | 是 | Linear API 密钥 |
| `LINEAR_PROJECT_SLUG` | 是 | 您的 Linear 团队/项目标识 |

### Symphony 设置

| 变量 | 默认值 | 描述 |
|----------|---------|-------------|
| `SYMPHONY_LOG_LEVEL` | INFO | 日志级别（DEBUG、INFO、WARNING、ERROR） |
| `SYMPHONY_MAX_CONCURRENT` | 3 | 最大并发 Agent 数 |
| `SYMPHONY_WORKSPACE_ROOT` | ./workspaces | 工作空间目录 |

## Docker 部署

### 使用 Docker 快速开始

```bash
# 首先创建配置文件
symphony init

# 构建并运行
docker-compose up -d

# 查看日志
docker-compose logs -f symphony

# 停止
docker-compose down
```

### 自定义配置

创建 `docker-compose.override.yml`：

```yaml
version: "3.8"
services:
  symphony:
    volumes:
      - ./my-project:/src:rw
    environment:
      - SYMPHONY_MAX_CONCURRENT=5
```

### 生产部署

```bash
# 带自动更新
docker-compose --profile auto-update up -d

# 带监控
docker-compose --profile monitoring up -d
```

## 故障排除

### 常见问题

**LLM API 错误**
```bash
# 检查连接
symphony doctor

# 验证 API 密钥
echo $OPENAI_API_KEY
```

**Linear API 错误**
```bash
# 测试 Linear 连接
symphony doctor

# 检查项目标识是否正确
# 应与您的 Linear 团队 URL 匹配：https://linear.app/TEAM_SLUG
```

**权限被拒绝**
```bash
# 确保工作空间目录可写
chmod 755 ./workspaces

# 或在 WORKFLOW.md 中更改工作空间根目录
```

### 获取帮助

```bash
# 显示所有命令
symphony --help

# 命令特定帮助
symphony run --help
symphony init --help

# 验证配置
symphony validate WORKFLOW.md --strict
```

## 下一步

- 阅读[完整文档](README.md)
- 查看[示例](examples/)
- 配置[自定义钩子](docs/hooks.md)
- 设置[多个 LLM 供应商](docs/providers.md)

## 快速参考

| 命令 | 描述 |
|---------|-------------|
| `symphony init` | 交互式设置向导 |
| `symphony run` | 启动编排器 |
| `symphony validate` | 检查配置 |
| `symphony doctor` | 环境诊断 |
| `symphony --version` | 显示版本 |
| `symphony --help` | 显示帮助 |
