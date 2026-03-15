# Symphony (Python Edition)

Symphony 是一个智能 Agent 编排系统，将项目工作转化为独立的、自主的执行任务，让团队能够专注于管理工作而非监督编码 Agent。

这是 Symphony 的 Python 3.12 实现版本，使用 AgentScope 作为 Agent 基础库。

## 特性

- 自动轮询 Linear 获取候选任务
- 为每个 Issue 创建独立的工作空间
- 智能并发控制和状态管理
- 自动重试和指数退避
- 实时的终端状态仪表板
- 可选的 HTTP API 服务器
- 支持远程 SSH 工作节点

## 安装

### 要求

- Python 3.12 或更高版本
- Linear API 密钥
- Codex CLI (或其他兼容的 coding agent)

### 从源码安装

```bash
git clone https://github.com/openai/symphony
cd symphony/symphony.py
pip install -e .
```

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

## 快速开始

### 1. 创建工作流配置

创建 `WORKFLOW.md` 文件：

```yaml
---
tracker:
  kind: linear
  project_slug: "your-project-slug"
  api_key: $LINEAR_API_KEY

polling:
  interval_ms: 30000

workspace:
  root: ~/symphony-workspaces

hooks:
  after_create: |
    git clone git@github.com:your-org/your-repo.git .

agent:
  max_concurrent_agents: 10
  max_turns: 20

codex:
  command: codex app-server
  approval_policy: never
---

You are working on issue {{ issue.identifier }}: {{ issue.title }}

Description:
{{ issue.description }}

Please implement the necessary changes.
```

### 2. 设置环境变量

```bash
export LINEAR_API_KEY="your-linear-api-key"
```

### 3. 运行 Symphony

```bash
python -m symphony WORKFLOW.md
```

## 配置说明

### Tracker 配置

```yaml
tracker:
  kind: linear              # Tracker 类型: linear 或 memory
  endpoint: https://api.linear.app/graphql
  api_key: $LINEAR_API_KEY  # API 密钥或环境变量引用
  project_slug: "..."       # Linear 项目 slug
  assignee: "me"           # 可选: 只处理分配给当前用户的 Issue
  active_states:           # 视为活跃的状态
    - Todo
    - In Progress
  terminal_states:         # 视为终态的状态
    - Closed
    - Done
```

### Agent 配置

```yaml
agent:
  max_concurrent_agents: 10      # 最大并发 Agent 数
  max_turns: 20                  # 每个会话最大轮数
  max_retry_backoff_ms: 300000   # 最大重试退避时间 (5分钟)
```

### Codex 配置

```yaml
codex:
  command: codex app-server      # 启动 coding agent 的命令
  approval_policy: never         # 审批策略
  thread_sandbox: workspace-write # 沙盒模式
  turn_timeout_ms: 3600000       # 单轮超时 (1小时)
  stall_timeout_ms: 300000       # 停滞检测超时 (5分钟)
```

## 项目结构

```
symphony.py/
├── src/symphony/
│   ├── config/          # 配置管理
│   ├── models/          # 数据模型
│   ├── workflow/        # 工作流解析
│   ├── trackers/        # Issue Tracker 适配器
│   ├── workspace/       # 工作空间管理
│   ├── agents/          # Agent 实现
│   ├── orchestrator/    # 核心调度器
│   ├── dashboard/       # 状态仪表板
│   ├── web/             # HTTP API
│   └── utils/           # 工具函数
├── tests/               # 测试
└── docs/                # 文档
```

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│         (调度器: 轮询、分派、重试、状态调和)                    │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
┌───────────┐ ┌────────┐ ┌──────────┐
│  Linear   │ │ Agent  │ │ Workspace│
│  Tracker  │ │ Runner │ │ Manager  │
└───────────┘ └───┬────┘ └──────────┘
                  │
                  ▼
         ┌────────────────┐
         │  AgentScope    │
         │  ReActAgent    │
         └────────────────┘
```

## 开发

### 运行测试

```bash
pytest
```

### 代码检查

```bash
ruff check src
ruff format src
mypy src
```

## 与原 Elixir 版本的差异

1. **异步模型**: 使用 Python asyncio 替代 Elixir OTP
2. **Agent 框架**: 使用 AgentScope 替代直接与 Codex app-server 通信
3. **类型系统**: 使用 Pydantic 进行运行时类型验证
4. **配置**: 保持相同的 WORKFLOW.md 格式

## 许可证

Apache License 2.0
