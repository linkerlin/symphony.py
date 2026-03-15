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

# Simple Symphony Workflow

This is a minimal Symphony configuration for quick start.

## Usage

1. Copy this file to `WORKFLOW.md`
2. Edit `project_slug` in the configuration
3. Create `.env` with your API keys:
   ```
   OPENAI_API_KEY=sk-...
   LINEAR_API_KEY=lin_api_...
   LINEAR_PROJECT_SLUG=my-project
   ```
4. Run: `symphony run WORKFLOW.md`
