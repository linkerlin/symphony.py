# Symphony Test Suite

This directory contains comprehensive tests for Symphony with minimal mocking.

## Test Philosophy

- **Real over Mock**: Use real APIs and filesystem operations where possible
- **Fast execution**: Tests should complete quickly using fast/cheap models
- **Safety first**: Path safety and security tests use controlled temp directories
- **Timeout protection**: All tests have timeouts to prevent hanging

## Test Organization

| File | Description | Dependencies |
|------|-------------|--------------|
| `test_llm_integration.py` | LLM client tests with real APIs | LLM API key |
| `test_agent_integration.py` | Agent execution tests | LLM API key |
| `test_workspace_safety.py` | Path security tests | None |
| `test_orchestrator_state.py` | State machine tests | None |
| `test_tracker_integration.py` | Linear API tests | LINEAR_API_KEY |
| `test_e2e_smoke.py` | End-to-end smoke tests | LLM API key |
| `test_tools_functionality.py` | Tool execution tests | None |

## Running Tests

### Quick Unit Tests (No API calls)
```bash
# Fast tests only (no LLM API calls)
make test

# Or using script
./scripts/run_tests.sh

# Or using pytest directly
pytest -v -m "not llm and not slow"
```

### Integration Tests (With real APIs)
```bash
# All tests including LLM
make test-all

# Or using script
./scripts/run_tests.sh --all

# Just LLM tests
./scripts/run_tests.sh --llm
```

### Specific Test Categories
```bash
# Unit tests only
pytest -v -m "not llm and not slow"

# Integration tests
pytest -v -m integration

# LLM tests only
pytest -v -m llm

# Linear tests only
pytest -v -m linear
```

## Environment Setup

### Required Environment Variables

```bash
# For LLM tests (at least one required)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DEEPSEEK_API_KEY="..."
export GEMINI_API_KEY="..."

# For Linear tests (optional)
export LINEAR_API_KEY="lin_api_..."
export LINEAR_PROJECT_SLUG="your-team"
```

### Test Configuration

Tests use fast/cheap models by default:

- **OpenAI**: `gpt-4o-mini` (fast and cheap)
- **Anthropic**: `claude-3-haiku-20240307` (fastest Claude)
- **DeepSeek**: `deepseek-chat`
- **Gemini**: `gemini-1.5-flash`

## Test Fixtures

### `fast_llm_client`
Provides LLM client with minimal token limits for speed.

### `temp_workspace`
Provides temporary directory for file operations.

### `workspace_manager`
Provides WorkspaceManager with automatic cleanup.

### `test_issue_data`
Provides sample issue data for testing.

## Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.llm` | Test calls real LLM API (incur costs) |
| `@pytest.mark.integration` | Integration test with external services |
| `@pytest.mark.slow` | Test takes longer than 10 seconds |
| `@pytest.mark.linear` | Test requires Linear API |
| `@pytest.mark.timeout(N)` | Test timeout in seconds |

## Writing New Tests

### Unit Test Example (No API calls)
```python
def test_something_local():
    """Test that doesn't need external services."""
    result = some_function()
    assert result == expected
```

### Integration Test Example (With LLM)
```python
@pytest.mark.llm
@pytest.mark.timeout(10)
async def test_with_llm(fast_llm_client):
    """Test that uses real LLM."""
    response = await fast_llm_client.complete([...])
    assert response.content is not None
```

### Test with Workspace
```python
async def test_with_workspace(temp_workspace):
    """Test that needs filesystem."""
    file_path = temp_workspace / "test.txt"
    file_path.write_text("content")
    # ... test code
```

## Troubleshooting

### Tests Hanging
- Tests have built-in timeouts via `@pytest.mark.timeout(N)`
- Fast model settings limit token generation
- Use `pytest --timeout=10` for global timeout

### API Key Issues
```bash
# Check if keys are set
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Run doctor command to verify
symphony doctor
```

### Test Isolation
- Each test gets fresh temp workspace
- LLM clients are recreated per test
- State is cleaned up automatically

## CI/CD Integration

For CI/CD, run fast tests only:
```bash
pytest -v -m "not llm and not slow" --cov=symphony
```

For nightly builds, run all tests:
```bash
pytest -v --cov=symphony
```
