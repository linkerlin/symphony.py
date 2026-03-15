# Symphony (Python Edition) 🎼

Symphony 是一个智能 Agent 编排系统，将项目工作转化为独立的、自主的执行任务，让团队能够专注于管理工作而非监督编码 Agent。

这是 Symphony 的 Python 3.12 实现版本，支持多种 LLM 供应商（OpenAI、Anthropic、DeepSeek、Gemini、Azure 等）。

## 特性

- **🤖 LLM 供应商无关**: 支持 OpenAI、Anthropic、DeepSeek、Gemini、Azure OpenAI
- **📋 Linear 集成**: 自动轮询 Linear 获取候选任务
- **📁 独立工作空间**: 为每个 Issue 创建隔离的工作环境
- **⚡ 智能并发控制**: 可配置的最大并发 Agent 数
- **🔄 自动重试机制**: 指数退避和状态恢复
- **🔧 交互式配置向导**: 一键初始化项目
- **📊 实时监控仪表板**: 终端 UI 显示运行状态
- **🔍 环境诊断工具**: 一键检查配置和连接
- **🐳 Docker 支持**: 容器化部署，快速启动

## 快速开始

### 一键安装

```bash
curl -sSL https://raw.githubusercontent.com/openai/symphony/main/symphony.py/install.sh | bash
```

或使用 pip:

```bash
pip install symphony
```

### 一分钟配置

```bash
# 1. 初始化配置（交互式向导）
symphony init

# 2. 检查环境
symphony doctor

# 3. 启动（带实时仪表板）
symphony run --dashboard
```

## 安装

### 要求

- Python 3.12+
- Linear API 密钥
- LLM API 密钥（OpenAI、Anthropic 等）

### 从源码安装

```bash
git clone https://github.com/openai/symphony
cd symphony/symphony.py
pip install -e .
```

### Docker 部署

```bash
# 克隆仓库
git clone https://github.com/openai/symphony
cd symphony/symphony.py

# 启动（使用 Docker Compose）
docker-compose up -d

# 查看日志
docker-compose logs -f symphony
```

## CLI 命令

| 命令 | 描述 |
|------|------|
| `symphony init` | 交互式配置向导 |
| `symphony run [WORKFLOW.md]` | 启动编排器 |
| `symphony validate [WORKFLOW.md]` | 验证配置 |
| `symphony doctor` | 环境诊断 |
| `symphony --version` | 显示版本 |

### 运行选项

```bash
# 基本运行
symphony run WORKFLOW.md

# 带实时仪表板
symphony run --dashboard

# 详细日志
symphony run --verbose

# 指定环境文件
symphony run --env-file .env.local

# 指定端口
symphony run --port 8080
```

## 配置

### 环境变量

#### LLM 供应商

| 变量 | 描述 | 必需 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | 使用 OpenAI 时 |
| `OPENAI_BASE_URL` | 自定义 API 地址 | 否 |
| `OPENAI_MODEL` | 模型名称 (gpt-4, gpt-4o) | 否 |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | 使用 Anthropic 时 |
| `ANTHROPIC_MODEL` | 模型名称 | 否 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 使用 DeepSeek 时 |
| `GEMINI_API_KEY` | Google Gemini API 密钥 | 使用 Gemini 时 |

#### Linear 集成

| 变量 | 描述 | 必需 |
|------|------|------|
| `LINEAR_API_KEY` | Linear API 密钥 | 是 |
| `LINEAR_PROJECT_SLUG` | Linear 团队/项目标识 | 是 |

### WORKFLOW.md 配置

```yaml
---
symphony:
  version: "1.0"
  
  settings:
    llm:
      provider: openai
      model: gpt-4
      temperature: 0.7
      max_tokens: 4096
    
    agent:
      max_turns: 20
      include_patterns:
        - "**/*.py"
        - "**/*.md"
      exclude_patterns:
        - "**/.git/**"
        - "**/__pycache__/**"
    
    tracker:
      kind: linear
      project_slug: my-team
      active_states:
        - "Todo"
        - "In Progress"
      terminal_states:
        - "Done"
        - "Canceled"
    
    workspace:
      root: ./workspaces
      max_concurrent_agents: 3
    
    hooks:
      timeout_ms: 30000
      after_create: |
        echo "Workspace created: $SYMPHONY_WORKSPACE"
      before_run: |
        echo "Starting: $SYMPHONY_ISSUE_ID"
      after_run: |
        echo "Completed: $SYMPHONY_ISSUE_ID"

  prompt: |
    You are working on Linear issue {{identifier}}: {{title}}
    
    Description:
    {{description}}
    
    Your task:
    1. Understand the requirements
    2. Explore the codebase
    3. Implement the solution
    4. Test your changes
    5. Summarize what was done
---
```

## Agent 工具

Agent 可以使用的工具：

| 工具 | 描述 |
|------|------|
| `read_file(path)` | 读取工作区内文件 |
| `write_file(path, content)` | 写入文件 |
| `execute_command(cmd, timeout)` | 执行 shell 命令 |
| `linear_graphql(query, variables)` | Linear GraphQL 查询 |
| `add_comment(issue_id, body)` | 添加评论到 Issue |
| `get_issue(issue_id)` | 获取 Issue 详情 |

## 项目结构

```
symphony.py/
├── src/symphony/           # 源代码
│   ├── agents/             # Agent 实现
│   ├── cli_commands/       # CLI 命令
│   ├── config/             # 配置管理
│   ├── dashboard/          # 终端仪表板
│   ├── llm/                # LLM 客户端
│   ├── orchestrator/       # 编排器
│   ├── trackers/           # 任务追踪器
│   └── workspace/          # 工作空间管理
├── examples/               # 示例配置
├── Dockerfile              # Docker 构建
├── docker-compose.yml      # Docker Compose 配置
├── install.sh              # 安装脚本
├── Makefile                # 开发命令
└── QUICKSTART.md           # 快速入门指南
```

## 开发

```bash
# 安装开发依赖
make install-dev

# 运行测试
make test

# 代码检查
make lint

# 格式化代码
make format

# Docker 构建
make docker-build
```

## 文档

- [快速入门指南](QUICKSTART.md)
- [架构文档](ARCHITECTURE.md)
- [示例配置](examples/)

## 许可证

Apache 2.0
