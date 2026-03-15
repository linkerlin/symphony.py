#!/bin/bash
# Symphony Test Runner Script
# 
# Usage:
#   ./run_tests.sh          # Run fast unit tests
#   ./run_tests.sh -a       # Run all tests including LLM tests
#   ./run_tests.sh -i       # Run integration tests
#   ./run_tests.sh -f       # Run with fail-fast

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default options
MARKERS="not llm and not slow"
FAIL_FAST=""
VERBOSE="-v"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--all)
            MARKERS=""
            shift
            ;;
        -i|--integration)
            MARKERS="integration"
            shift
            ;;
        -l|--llm)
            MARKERS="llm"
            shift
            ;;
        -u|--unit)
            MARKERS="not llm and not slow"
            shift
            ;;
        -f|--fail-fast)
            FAIL_FAST="-x"
            shift
            ;;
        -q|--quiet)
            VERBOSE=""
            shift
            ;;
        -h|--help)
            echo "Symphony Test Runner"
            echo ""
            echo "Options:"
            echo "  -a, --all           Run all tests (including LLM)"
            echo "  -i, --integration   Run only integration tests"
            echo "  -l, --llm          Run only LLM tests"
            echo "  -u, --unit         Run only unit tests (default)"
            echo "  -f, --fail-fast    Stop on first failure"
            echo "  -q, --quiet        Less verbose output"
            echo "  -h, --help         Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check Python version
echo -e "${BLUE}Checking Python version...${NC}"
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Check for API keys
echo ""
echo -e "${BLUE}Checking API configuration...${NC}"

if [ -n "$OPENAI_API_KEY" ]; then
    echo -e "${GREEN}✓ OPENAI_API_KEY is set${NC}"
else
    echo -e "${YELLOW}⚠ OPENAI_API_KEY not set${NC}"
fi

if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo -e "${GREEN}✓ ANTHROPIC_API_KEY is set${NC}"
else
    echo -e "${YELLOW}⚠ ANTHROPIC_API_KEY not set${NC}"
fi

if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$DEEPSEEK_API_KEY" ] && [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${YELLOW}Warning: No LLM API keys set. LLM tests will be skipped.${NC}"
fi

# Build pytest command
echo ""
echo -e "${BLUE}Running tests...${NC}"
echo "Markers: $MARKERS"
echo ""

PYTEST_ARGS="$VERBOSE $FAIL_FAST"

if [ -n "$MARKERS" ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m \"$MARKERS\""
fi

# Run tests
eval "pytest $PYTEST_ARGS"

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
else
    echo -e "${RED}Tests failed with exit code $exit_code${NC}"
fi

exit $exit_code
