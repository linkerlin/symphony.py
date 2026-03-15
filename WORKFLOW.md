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
    echo "工作空间已创建"
  before_run: |
    echo "开始 Agent 运行"
  after_run: |
    echo "Agent 运行完成"
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

您正在处理 Linear 问题 `{{ issue.identifier }}`

{% if attempt %}
继续上下文：

- 这是第 {{ attempt }} 次重试，因为问题仍处于活动状态。
- 从当前工作空间状态恢复，而不是从头开始。
{% endif %}

问题上下文：
- 标识符: {{ issue.identifier }}
- 标题: {{ issue.title }}
- 当前状态: {{ issue.state }}
- 标签: {{ issue.labels }}
{% if issue.url %}
- URL: {{ issue.url }}
{% endif %}

描述：
{% if issue.description %}
{{ issue.description }}
{% else %}
未提供描述。
{% endif %}

指令：

1. 这是一个无人值守的编排会话。永远不要要求人工执行后续操作。
2. 仅在真正阻塞时（缺少必需的认证/权限/密钥）才提前停止。
3. 最终消息必须仅报告已完成的操作和阻塞项。

仅在提供的仓库副本中工作。不要触碰任何其他路径。
