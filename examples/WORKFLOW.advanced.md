---
symphony:
  version: "1.0"
  
  settings:
    # LLM Configuration - Using Anthropic Claude
    llm:
      provider: anthropic
      model: claude-3-sonnet-20240229
      temperature: 0.7
      max_tokens: 8192
    
    # Advanced Agent Configuration
    agent:
      max_turns: 50
      # File context patterns
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
    
    # Linear Integration
    tracker:
      kind: linear
      endpoint: https://api.linear.app/graphql
      project_slug: my-team
      # Only process issues assigned to this user
      assignee: user_uuid_here
      active_states:
        - "Backlog"
        - "Todo"
        - "In Progress"
      terminal_states:
        - "In Review"
        - "Done"
        - "Canceled"
    
    # Workspace with custom hooks
    workspace:
      root: ./workspaces
      max_concurrent_agents: 5
    
    # Lifecycle hooks
    hooks:
      timeout_ms: 60000
      # Called after workspace is created
      after_create: |
        echo "Workspace created at $SYMPHONY_WORKSPACE"
        echo "Issue: $SYMPHONY_ISSUE_ID"
        # Initialize git if needed
        if [ ! -d "$SYMPHONY_WORKSPACE/.git" ]; then
          git clone https://github.com/myorg/myrepo.git "$SYMPHONY_WORKSPACE"
        fi
      
      # Called before agent starts
      before_run: |
        echo "Starting work on $SYMPHONY_ISSUE_ID"
        cd "$SYMPHONY_WORKSPACE"
        git fetch origin
        git checkout -b "feature/$SYMPHONY_ISSUE_ID" || true
      
      # Called after agent finishes
      after_run: |
        echo "Completed $SYMPHONY_ISSUE_ID"
        cd "$SYMPHONY_WORKSPACE"
        git add -A
        git commit -m "WIP: $SYMPHONY_ISSUE_ID" || true
      
      # Called before workspace is removed
      before_remove: |
        echo "Cleaning up $SYMPHONY_WORKSPACE"

  # Advanced Prompt Template with Handlebars
  prompt: |
    You are an expert software engineer working on Linear issue {{identifier}}: {{title}}
    
    {{#if labels}}
    Labels: {{#each labels}}{{#if @index}}, {{/if}}{{this}}{{/each}}
    {{/if}}
    
    {{#if blockers}}
    ⚠️ Blocked by: {{#each blockers}}{{#if @index}}, {{/if}}{{this}}{{/each}}
    Please note any blockers encountered.
    {{/if}}
    
    ## Description
    {{description}}
    
    {{#if attempt}}
    ## Retry Context
    This is attempt {{attempt}} of a previous failed run.
    Please review previous changes carefully and fix any issues.
    {{/if}}
    
    ## Your Task
    
    1. **Understand**: Read and understand the requirements
    2. **Explore**: Use tools to explore the codebase structure
    3. **Plan**: Create a plan of action
    4. **Implement**: Make the necessary changes
    5. **Test**: Run tests or verify the changes work
    6. **Document**: Update relevant documentation
    
    ## Guidelines
    
    - Write clean, well-documented code
    - Follow existing code style and patterns
    - Add tests for new functionality
    - Update README/docs if needed
    - Use `add_comment` to report progress on the Linear issue
    
    {{#if workspace}}
    Workspace: {{workspace}}
    {{/if}}
---

# Advanced Symphony Workflow

This configuration demonstrates advanced Symphony features:

- Custom lifecycle hooks for git operations
- Multiple file type support
- Retry context handling
- Detailed prompt template

## Setup

```bash
# Set environment variables
export ANTHROPIC_API_KEY=sk-ant-...
export LINEAR_API_KEY=lin_api_...

# Run Symphony
symphony run WORKFLOW.advanced.md --dashboard
```
