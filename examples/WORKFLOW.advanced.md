---
symphony:
  version: "1.0"
  
  settings:
    # LLM 配置 - 使用 Anthropic Claude
    llm:
      provider: anthropic
      model: claude-3-sonnet-20240229
      temperature: 0.7
      max_tokens: 8192
    
    # 高级 Agent 配置
    agent:
      max_turns: 50
      # 文件上下文匹配模式
      include_patterns:
        - "**/*.py"
        - "**/*.js"
        - "**/*.ts"
        - "**/*.tsx"
        - "**/*.json"
        - "**/*.yaml"
        - "**/*.yml"
        - "**/*.md"
        - "**/*.txt"
        - "Makefile"
        - "Dockerfile"
      exclude_patterns:
        - "**/.git/**"
        - "**/.github/**"
        - "**/node_modules/**"
        - "**/__pycache__/**"
        - "**/.venv/**"
        - "**/venv/**"
        - "**/dist/**"
        - "**/build/**"
        - "**/*.min.js"
        - "**/*.min.css"
    
    # Linear 集成
    tracker:
      kind: linear
      endpoint: https://api.linear.app/graphql
      project_slug: my-team
      # 仅处理分配给此用户的问题
      assignee: user_uuid_here
      active_states:
        - "Backlog"
        - "Todo"
        - "In Progress"
      terminal_states:
        - "In Review"
        - "Done"
        - "Canceled"
    
    # 带自定义钩子的工作空间
    workspace:
      root: ./workspaces
      max_concurrent_agents: 5
    
    # 生命周期钩子
    hooks:
      timeout_ms: 60000
      # 在工作空间创建后调用
      after_create: |
        echo "工作空间创建于 $SYMPHONY_WORKSPACE"
        echo "问题: $SYMPHONY_ISSUE_ID"
        # 如果需要则初始化 git
        if [ ! -d "$SYMPHONY_WORKSPACE/.git" ]; then
          git clone https://github.com/myorg/myrepo.git "$SYMPHONY_WORKSPACE"
        fi
      
      # 在 Agent 启动前调用
      before_run: |
        echo "开始处理 $SYMPHONY_ISSUE_ID"
        cd "$SYMPHONY_WORKSPACE"
        git fetch origin
        git checkout -b "feature/$SYMPHONY_ISSUE_ID" || true
      
      # 在 Agent 完成后调用
      after_run: |
        echo "完成 $SYMPHONY_ISSUE_ID"
        cd "$SYMPHONY_WORKSPACE"
        git add -A
        git commit -m "WIP: $SYMPHONY_ISSUE_ID" || true
      
      # 在工作空间移除前调用
      before_remove: |
        echo "清理 $SYMPHONY_WORKSPACE"

  # 带 Handlebars 的高级提示词模板
  prompt: |
    您是一位处理 Linear 问题 {{identifier}}: {{title}} 的资深软件工程师
    
    {{#if labels}}
    标签: {{#each labels}}{{#if @index}}, {{/if}}{{this}}{{/each}}
    {{/if}}
    
    {{#if blockers}}
    ⚠️ 被阻塞: {{#each blockers}}{{#if @index}}, {{/if}}{{this}}{{/each}}
    请记录遇到的任何阻塞项。
    {{/if}}
    
    ## 描述
    {{description}}
    
    {{#if attempt}}
    ## 重试上下文
    这是之前失败运行的第 {{attempt}} 次尝试。
    请仔细查看之前的更改并修复任何问题。
    {{/if}}
    
    ## 您的任务
    
    1. **理解**: 阅读并理解需求
    2. **探索**: 使用工具探索代码库结构
    3. **计划**: 制定行动计划
    4. **实现**: 进行必要的更改
    5. **测试**: 运行测试或验证更改是否有效
    6. **文档**: 更新相关文档
    
    ## 指南
    
    - 编写干净、文档完善的代码
    - 遵循现有代码风格和模式
    - 为新功能添加测试
    - 如有需要更新 README/文档
    - 使用 `add_comment` 在 Linear 问题上报告进度
    
    {{#if workspace}}
    工作空间: {{workspace}}
    {{/if}}
---

# 高级 Symphony 工作流

此配置演示了 Symphony 的高级特性：

- 用于 git 操作的自定义生命周期钩子
- 多种文件类型支持
- 重试上下文处理
- 详细的提示词模板

## 设置

```bash
# 设置环境变量
export ANTHROPIC_API_KEY=sk-ant-...
export LINEAR_API_KEY=lin_api_...

# 运行 Symphony
symphony run WORKFLOW.advanced.md --dashboard
```
