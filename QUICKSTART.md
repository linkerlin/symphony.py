# Symphony Quick Start Guide

Get Symphony up and running in minutes.

## Installation

### Option 1: pip (Recommended)

```bash
pip install symphony
```

### Option 2: From Source

```bash
git clone https://github.com/openai/symphony.git
cd symphony/symphony.py
pip install -e .
```

### Option 3: Docker

```bash
# Clone repository
git clone https://github.com/openai/symphony.git
cd symphony/symphony.py

# Run with Docker Compose
docker-compose up -d
```

## One-Minute Setup

### 1. Initialize Configuration

```bash
symphony init
```

This interactive wizard will:
- Ask for your preferred LLM provider (OpenAI, Anthropic, DeepSeek, Gemini)
- Configure your API keys
- Set up Linear integration
- Generate `WORKFLOW.md` and `.env` files

### 2. Validate Setup

```bash
symphony doctor
```

Checks connectivity to:
- LLM provider API
- Linear API
- System requirements

### 3. Run Symphony

```bash
# Basic run
symphony run WORKFLOW.md

# With terminal dashboard
symphony run WORKFLOW.md --dashboard

# With verbose logging
symphony run WORKFLOW.md --verbose
```

## Manual Setup (Alternative)

If you prefer manual configuration:

### 1. Create `WORKFLOW.md`

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
    Work on Linear issue {{identifier}}: {{title}}
    {{description}}
---
```

### 2. Create `.env`

```bash
OPENAI_API_KEY=sk-...
LINEAR_API_KEY=lin_api_...
LINEAR_PROJECT_SLUG=your-project
```

### 3. Validate and Run

```bash
symphony validate WORKFLOW.md
symphony run WORKFLOW.md
```

## Environment Variables

### LLM Providers

| Variable | Provider | Required |
|----------|----------|----------|
| `OPENAI_API_KEY` | OpenAI | Yes, if using OpenAI |
| `OPENAI_BASE_URL` | OpenAI | No (defaults to api.openai.com) |
| `OPENAI_MODEL` | OpenAI | No (defaults to gpt-4) |
| `ANTHROPIC_API_KEY` | Anthropic | Yes, if using Anthropic |
| `ANTHROPIC_MODEL` | Anthropic | No (defaults to claude-3-sonnet) |
| `DEEPSEEK_API_KEY` | DeepSeek | Yes, if using DeepSeek |
| `GEMINI_API_KEY` | Gemini | Yes, if using Gemini |

### Linear Integration

| Variable | Required | Description |
|----------|----------|-------------|
| `LINEAR_API_KEY` | Yes | Linear API key |
| `LINEAR_PROJECT_SLUG` | Yes | Your Linear team/project slug |

### Symphony Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SYMPHONY_LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `SYMPHONY_MAX_CONCURRENT` | 3 | Maximum concurrent agents |
| `SYMPHONY_WORKSPACE_ROOT` | ./workspaces | Workspace directory |

## Docker Deployment

### Quick Start with Docker

```bash
# Create configuration files first
symphony init

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f symphony

# Stop
docker-compose down
```

### Custom Configuration

Create `docker-compose.override.yml`:

```yaml
version: "3.8"
services:
  symphony:
    volumes:
      - ./my-project:/src:rw
    environment:
      - SYMPHONY_MAX_CONCURRENT=5
```

### Production Deployment

```bash
# With auto-update
docker-compose --profile auto-update up -d

# With monitoring
docker-compose --profile monitoring up -d
```

## Troubleshooting

### Common Issues

**LLM API Error**
```bash
# Check connectivity
symphony doctor

# Verify API key
echo $OPENAI_API_KEY
```

**Linear API Error**
```bash
# Test Linear connection
symphony doctor

# Check project slug is correct
# Should match your Linear team URL: https://linear.app/TEAM_SLUG
```

**Permission Denied**
```bash
# Ensure workspace directory is writable
chmod 755 ./workspaces

# Or change workspace root in WORKFLOW.md
```

### Getting Help

```bash
# Show all commands
symphony --help

# Command-specific help
symphony run --help
symphony init --help

# Validate configuration
symphony validate WORKFLOW.md --strict
```

## Next Steps

- Read the [full documentation](README.md)
- Check [examples](examples/)
- Configure [custom hooks](docs/hooks.md)
- Set up [multiple LLM providers](docs/providers.md)

## Quick Reference

| Command | Description |
|---------|-------------|
| `symphony init` | Interactive setup wizard |
| `symphony run` | Start the orchestrator |
| `symphony validate` | Check configuration |
| `symphony doctor` | Environment diagnostics |
| `symphony --version` | Show version |
| `symphony --help` | Show help |
