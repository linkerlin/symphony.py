---
# Symphony 工作流配置
# 支持从 .env 文件或环境变量读取配置

# LLM 配置
# 优先从环境变量读取: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
# 也支持: ANTHROPIC_*, DEEPSEEK_*, GEMINI_*, AZURE_*
llm:
  provider: openai          # 供应商: openai, anthropic, deepseek, gemini, azure
  # api_key: (从 OPENAI_API_KEY 环境变量读取)
  # base_url: (从 OPENAI_BASE_URL 环境变量读取)
  # model: (从 OPENAI_MODEL 环境变量读取，默认: gpt-4)
  temperature: 0.7
  max_tokens: 4096
  timeout: 120
  max_retries: 3

# Linear 配置
tracker:
  kind: linear
  project_slug: "your-project-slug"
  api_key: $LINEAR_API_KEY
  active_states:
    - Todo
    - In Progress
  terminal_states:
    - Closed
    - Cancelled
    - Canceled
    - Duplicate
    - Done

# 轮询配置
polling:
  interval_ms: 30000

# 工作空间配置
workspace:
  root: ~/symphony-workspaces

# 生命周期钩子
hooks:
  after_create: |
    # 在此处初始化仓库
    # git clone git@github.com:your-org/your-repo.git .
    echo "Workspace created"
  before_run: |
    echo "Starting agent run"
  after_run: |
    echo "Agent run completed"
  timeout_ms: 60000

# Agent 配置
agent:
  max_concurrent_agents: 10
  max_turns: 20
  max_retry_backoff_ms: 300000
  turn_timeout_seconds: 3600
  stall_timeout_seconds: 300

# HTTP 服务器配置 (可选)
server:
  # port: 8080
  host: 127.0.0.1
---

You are working on Linear issue `{{ issue.identifier }}`

{% if attempt %}
Continuation context:

- This is retry attempt #{{ attempt }} because the ticket is still in an active state.
- Resume from the current workspace state instead of restarting from scratch.
{% endif %}

Issue context:
- Identifier: {{ issue.identifier }}
- Title: {{ issue.title }}
- Current status: {{ issue.state }}
- Labels: {{ issue.labels }}
{% if issue.url %}
- URL: {{ issue.url }}
{% endif %}

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

Instructions:

1. This is an unattended orchestration session. Never ask a human to perform follow-up actions.
2. Only stop early for a true blocker (missing required auth/permissions/secrets).
3. Final message must report completed actions and blockers only.

Work only in the provided repository copy. Do not touch any other path.
