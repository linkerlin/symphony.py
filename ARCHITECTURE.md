# Symphony Architecture

## Overview

Symphony is an agent orchestration system that automates software engineering tasks using LLM-powered agents. It integrates with Linear for issue tracking and supports multiple LLM providers.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLI / API                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────────────┐  │
│  │  init    │  │ validate │  │  doctor  │  │  run (with --dashboard) │  │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Orchestrator                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │    State     │  │  Dispatcher  │  │  Scheduler   │  │   Retry     │ │
│  │   Manager    │  │              │  │              │  │   Handler   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Agent Layer                                   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      SymphonyAgent                                │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │  LLM     │  │  Tools   │  │  Prompt  │  │   Token Tracker  │  │   │
│  │  │  Client  │  │  (File,  │  │  Builder │  │                  │  │   │
│  │  │          │  │  Shell,  │  │          │  │                  │  │   │
│  │  │          │  │  Linear) │  │          │  │                  │  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         External Services                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  OpenAI  │  │ Anthropic│  │ DeepSeek │  │  Gemini  │  │  Azure   │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                         Linear API                                │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Configuration System (`symphony/config/`)

**Purpose**: Manage configuration from multiple sources with priority ordering.

**Key Classes**:
- `Config`: Main configuration container
- `LLMConfig`: LLM provider settings
- `TrackerConfig`: Linear integration settings
- `WorkspaceConfig`: Workspace management settings

**Configuration Priority**:
1. WORKFLOW.md YAML frontmatter
2. Environment variables
3. .env file
4. Default values

### 2. LLM Client (`symphony/llm/`)

**Purpose**: Provider-agnostic LLM interface supporting multiple backends.

**Key Classes**:
- `LLMClient`: Unified interface for all providers
- `Message`: Message format standardization
- `LLMResponse`: Normalized response handling

**Supported Providers**:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude 3)
- DeepSeek
- Google Gemini
- Azure OpenAI

### 3. Orchestrator (`symphony/orchestrator/`)

**Purpose**: Central scheduler managing agent lifecycle.

**Key Classes**:
- `Orchestrator`: Main orchestration loop
- `OrchestratorState`: State persistence
- `RunningEntry`, `RetryEntry`: State tracking

**Responsibilities**:
- Polling Linear for new issues
- Managing concurrent agent slots
- Handling retries with exponential backoff
- State reconciliation

### 4. Agent (`symphony/agents/`)

**Purpose**: Execute tasks using LLM with tool support.

**Key Classes**:
- `SymphonyAgent`: Main agent implementation
- `AgentSession`: Session state management

**Tools**:
- `read_file` / `write_file`: File operations
- `execute_command`: Shell command execution
- `linear_graphql`: Linear API queries
- `add_comment`: Add comments to issues

### 5. Tracker (`symphony/trackers/`)

**Purpose**: Interface with issue tracking systems.

**Key Classes**:
- `LinearTracker`: Linear GraphQL API client
- `Issue`: Normalized issue representation

### 6. Workspace Manager (`symphony/workspace/`)

**Purpose**: Manage agent working directories.

**Key Classes**:
- `WorkspaceManager`: Directory lifecycle management
- `WorkspaceContext`: Path safety validation

**Hooks**:
- `after_create`: Initialize workspace
- `before_run`: Prepare for execution
- `after_run`: Post-execution cleanup
- `before_remove`: Final cleanup

### 7. Dashboard (`symphony/dashboard/`)

**Purpose**: Real-time terminal UI for monitoring.

**Key Classes**:
- `Dashboard`: Rich-based terminal interface

**Features**:
- Running agents list
- LLM token usage statistics
- Retry queue status
- System health

## Data Flow

### Issue Processing Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Linear    │────▶│  Issue      │────▶│  Claim      │
│   Issue     │     │  Fetched    │     │  Attempt    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Linear     │◀────│  Results    │◀────│  Agent      │
│  Updated    │     │  Reported   │     │  Execution  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                        ┌──────┴──────┐
                                        │   Workspace  │
                                        │   Created    │
                                        └─────────────┘
```

### Agent Execution Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Start     │────▶│  Build      │────▶│  LLM        │
│   Session   │     │  Prompt     │     │  Request    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                        ┌──────────────────────┼──────────────────────┐
                        │                      │                      │
                        ▼                      ▼                      ▼
                 ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
                 │  Tool Call  │       │  Content    │       │   Error     │
                 │  Detected   │       │  Response   │       │             │
                 └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
                        │                      │                      │
                        ▼                      │                      │
                 ┌─────────────┐               │                      │
                 │  Execute    │               │                      │
                 │  Tools      │               │                      │
                 └──────┬──────┘               │                      │
                        │                      │                      │
                        └──────────────────────┼──────────────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Done?     │
                                        │  (max turns │
                                        │  or finish) │
                                        └──────┬──────┘
                                               │
                         ┌─────────────────────┴─────────────────────┐
                         │                                             │
                         ▼                                             ▼
                  ┌─────────────┐                             ┌─────────────┐
                  │   Report    │                             │   Next      │
                  │   Results   │                             │   Turn      │
                  └─────────────┘                             └─────────────┘
```

## Multi-Provider LLM Support

```
                    ┌─────────────────────────────────────┐
                    │           LLMClient                 │
                    │  ┌─────────────────────────────┐    │
                    │  │    Unified Interface        │    │
                    │  │  - chat_completion()        │    │
                    │  │  - embed()                  │    │
                    │  └─────────────────────────────┘    │
                    └──────────────┬──────────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
    │   OpenAI    │        │  Anthropic  │        │  DeepSeek   │
    │   Adapter   │        │   Adapter   │        │   Adapter   │
    └─────────────┘        └─────────────┘        └─────────────┘
           │                       │                       │
           ▼                       ▼                       ▼
    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
    │   GPT-4     │        │   Claude    │        │   Chat      │
    │   GPT-4o    │        │   3 Opus    │        │   Model     │
    │   o1        │        │   3 Sonnet  │        │             │
    └─────────────┘        └─────────────┘        └─────────────┘
```

## Security Considerations

### Path Safety
- All file operations use `_resolve_path()` to ensure paths stay within workspace
- Symbolic link traversal is prevented
- Relative path resolution is validated

### API Key Handling
- Keys are loaded from environment variables or .env files
- Keys are never logged or exposed in error messages
- Support for key rotation via environment

### Hook Execution
- Hooks run with configurable timeouts
- Shell commands are sandboxed to workspace
- Output is captured and logged

## Scalability

### Concurrent Agents
- Configurable max concurrent agents
- Slot-based allocation
- Graceful handling of resource limits

### State Persistence
- In-memory state with optional persistence
- State reconciliation on restart
- Atomic state transitions

### Retry Strategy
- Exponential backoff for failures
- Separate queue for continuation retries
- Configurable retry limits

## Extension Points

### Adding New LLM Providers
1. Create adapter class in `symphony/llm/providers/`
2. Implement `chat_completion()` method
3. Register in `LLMClient._get_provider_client()`

### Adding New Tools
1. Define tool function in `symphony/agents/tools/`
2. Add to `__all__` in `__init__.py`
3. Register in agent's tool registry
4. Update system prompt to describe tool

### Custom Trackers
1. Implement `BaseTracker` interface
2. Override `poll()`, `claim()`, `complete()`
3. Register in orchestrator factory

## Configuration Examples

### Minimal Configuration
```yaml
symphony:
  version: "1.0"
  settings:
    llm:
      provider: openai
      model: gpt-4
    tracker:
      kind: linear
      project_slug: my-team
```

### Advanced Configuration
```yaml
symphony:
  version: "1.0"
  settings:
    llm:
      provider: anthropic
      model: claude-3-opus-20240229
      temperature: 0.5
      max_tokens: 8192
    agent:
      max_turns: 50
      include_patterns: ["**/*.py", "**/*.ts"]
      exclude_patterns: ["**/tests/**"]
    tracker:
      kind: linear
      project_slug: my-team
      assignee: user-uuid
      active_states: ["Backlog", "Todo"]
    workspace:
      root: /var/symphony/workspaces
      max_concurrent_agents: 10
    hooks:
      after_create: |
        git clone $REPO_URL $SYMPHONY_WORKSPACE
```

## Development

### Running Tests
```bash
make test          # Run all tests
make test-cov      # Run with coverage
make lint          # Run linters
make format        # Format code
```

### Docker Development
```bash
make docker-build  # Build image
make docker-run    # Run containers
make docker-logs   # View logs
```

### Local Development
```bash
make install-dev   # Install with dev dependencies
symphony init      # Initialize config
symphony doctor    # Check environment
symphony run       # Start orchestrator
```
