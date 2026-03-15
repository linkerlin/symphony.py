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
      project_slug: my-project
      active_states:
        - "Todo"
        - "In Progress"
      terminal_states:
        - "Done"
        - "Canceled"
    
    workspace:
      root: ./workspaces
      max_concurrent_agents: 3

  prompt: |
    您正在处理 Linear 问题 {{identifier}}: {{title}}
    
    描述：
    {{description}}
    
    您的任务：
    1. 理解需求
    2. 探索代码库
    3. 实现解决方案
    4. 测试您的更改
    5. 总结完成的内容
---

# 简单 Symphony 工作流

这是一个用于快速入门的 Symphony 最小配置。

## 用法

1. 将此文件复制为 `WORKFLOW.md`
2. 在配置中编辑 `project_slug`
3. 使用您的 API 密钥创建 `.env`：
   ```
   OPENAI_API_KEY=sk-...
   LINEAR_API_KEY=lin_api_...
   LINEAR_PROJECT_SLUG=my-project
   ```
4. 运行: `symphony run WORKFLOW.md`
