# LiteLLM GitHub Copilot Instructions

**ALWAYS follow these instructions first and only fallback to additional search and context gathering if the information in these instructions is incomplete or found to be in error.**

LiteLLM is a unified interface for 100+ LLM providers, offering both a Python SDK and a proxy server (LLM Gateway). It translates inputs to provider-specific formats, provides consistent outputs, and includes advanced features like routing, caching, rate limiting, and cost tracking.

## Quick Start Development Setup

**NEVER CANCEL builds or long-running commands** - all operations complete within reasonable timeframes as documented below.

### Bootstrap Repository
```bash
# Install Poetry (if not available)
pip install poetry
export PATH="$HOME/.local/bin:$PATH"

# Basic development setup - NEVER CANCEL: completes in ~15 seconds
make install-dev

# Full proxy development setup - NEVER CANCEL: completes in ~10 seconds  
make install-proxy-dev

# Verify setup works
make help
```

### Development Workflow
```bash
# Format code - NEVER CANCEL: takes ~45 seconds, set timeout to 90+ seconds
make format

# Run all linting - NEVER CANCEL: takes ~5 seconds total
make lint

# Run unit tests on a single file - NEVER CANCEL: takes ~5 seconds per test file
poetry run pytest tests/test_litellm/test_utils.py::test_aaamodel_prices_and_context_window_json_is_valid -v

# Test dependencies (enterprise may fail due to network issues - this is normal)
make install-test-deps
```

### Running the Proxy Server
```bash
# Create test config
cat > /tmp/test_config.yaml << EOF
model_list:
  - model_name: test-gpt
    litellm_params:
      model: gpt-3.5-turbo
      api_key: "test-key"

general_settings:
  master_key: "sk-test-key"
EOF

# Start proxy server - runs immediately
poetry run litellm --config /tmp/test_config.yaml --port 4001

# Test the server is working
curl -X GET "http://localhost:4001/v1/models" -H "Authorization: Bearer sk-test-key"
```

## Critical Timing Information

**NEVER CANCEL these commands - they complete within the specified timeframes:**

- `make install-dev`: **~15 seconds** - Set timeout to 60+ seconds
- `make install-proxy-dev`: **~10 seconds** - Set timeout to 30+ seconds  
- `make format`: **~45 seconds** - Set timeout to 90+ seconds
- `make lint`: **~5 seconds total** - Set timeout to 30+ seconds
- `make test-unit`: **Variable timing** - Set timeout to 300+ seconds for full test suite
- Individual unit tests: **~5 seconds each** - Set timeout to 30+ seconds

## Repository Architecture

### Core Library (`litellm/`)
- **`litellm/main.py`** - Core completion() function entry point
- **`litellm/llms/`** - Provider implementations (100+ providers)
  - Each provider in its own subdirectory (e.g., `openai/`, `anthropic/`, `github_copilot/`)
  - Provider-specific transformation and request handling
- **`litellm/router.py`** + `litellm/router_utils/` - Load balancing and fallback logic
- **`litellm/types/`** - Pydantic models and type definitions
- **`litellm/integrations/`** - Third-party observability, caching, logging
- **`litellm/caching/`** - Multiple cache backends (Redis, in-memory, S3, etc.)

### Proxy Server (`litellm/proxy/`)
- **`proxy_server.py`** - FastAPI application main entry point
- **`auth/`** - API key management, JWT, OAuth2 authentication
- **`db/`** - Prisma ORM with PostgreSQL/SQLite support
- **`management_endpoints/`** - Admin APIs for keys, teams, models
- **`pass_through_endpoints/`** - Provider-specific API forwarding
- **`guardrails/`** - Safety and content filtering hooks

### Key Testing Areas (`tests/`)
- **`tests/test_litellm/`** - Unit tests (mocked, no real API calls)
- **`tests/llm_translation/`** - Integration tests for each provider
- **`tests/proxy_unit_tests/`** - Proxy server tests
- **`tests/load_tests/`** - Performance and load testing

## Development Commands Reference

### Installation Commands
```bash
make install-dev          # Core development dependencies (~15 seconds)
make install-proxy-dev    # Proxy development dependencies (~10 seconds)
make install-test-deps    # Test dependencies + enterprise setup
make install-dev-ci       # CI-compatible install (pins OpenAI version)
```

### Code Quality Commands  
```bash
make format               # Apply Black formatting (~45 seconds)
make format-check         # Check formatting only (~5 seconds)
make lint                 # All linting checks (~5 seconds total)
make lint-ruff           # Ruff linting only (~2 seconds)
make lint-mypy           # MyPy type checking (~3 seconds)
```

### Testing Commands
```bash
# Unit tests (tests/test_litellm) - NEVER CANCEL: 4 parallel workers
make test-unit

# Integration tests (excludes unit tests)  
make test-integration

# Single test file
poetry run pytest tests/test_litellm/test_utils.py -v

# Single test function
poetry run pytest tests/test_litellm/test_utils.py::test_function_name -v
```

## Manual Validation Scenarios

**ALWAYS test these scenarios after making changes:**

### Core Library Changes
1. **Basic completion test:**
   ```python
   from litellm import completion
   # Test with mock/dummy data - no real API calls in unit tests
   ```

2. **Provider-specific changes:**
   - Add tests in `tests/test_litellm/llms/provider_name/`
   - Follow existing test patterns using mocks

### Proxy Server Changes
1. **Start proxy and verify endpoints:**
   ```bash
   poetry run litellm --config /tmp/test_config.yaml --port 4001
   curl -X GET "http://localhost:4001/v1/models" -H "Authorization: Bearer sk-test-key"
   curl -X GET "http://localhost:4001/health"
   ```

2. **Test key functionality:**
   ```bash
   # Test model listing
   curl -X GET "http://localhost:4001/v1/models" -H "Authorization: Bearer sk-test-key"
   ```

## Common Development Patterns

### Adding a New LLM Provider
1. Create directory: `litellm/llms/new_provider/`
2. Implement transformation functions following existing patterns
3. Add to provider registry in `litellm/llms/__init__.py`
4. Add tests in `tests/test_litellm/llms/new_provider/`
5. Update documentation

### Adding Proxy Endpoints
1. Add endpoint in appropriate file under `litellm/proxy/`
2. Add authentication/authorization if needed
3. Add tests in `tests/proxy_unit_tests/`
4. Update OpenAPI specs if necessary

### Working with Types
- All types defined in `litellm/types/`
- Use Pydantic v2 for data validation
- Add type hints for all public APIs

## Known Issues & Workarounds

### Enterprise Package Installation
The enterprise package installation may fail with network timeouts:
```bash
cd enterprise && python -m pip install -e . && cd ..
# ERROR: Network timeout (this is expected)
```
**Workaround:** Core development works without enterprise package. Only needed for specific enterprise features.

### Poetry Not Found
If Poetry is not available:
```bash
pip install poetry
export PATH="$HOME/.local/bin:$PATH"
```

## CI Validation Commands

**Always run these before committing to ensure CI passes:**
```bash
make lint                # Must pass - runs all linting checks
make test-unit          # Must pass - runs unit test suite with 4 workers
```

## File Naming Conventions

### Tests
- `litellm/proxy/caching_routes.py` → `tests/test_litellm/proxy/test_caching_routes.py`
- `litellm/utils.py` → `tests/test_litellm/test_utils.py`
- Follow the same directory structure as the main codebase

### Providers
- Each provider in its own directory: `litellm/llms/provider_name/`
- Common files: `chat/transformation.py`, `common_utils.py`, etc.

## Quick Reference - Repository Root Files

```
/home/runner/work/litellm/litellm/
├── Makefile              # Development commands
├── pyproject.toml        # Poetry dependencies and metadata  
├── CONTRIBUTING.md       # Detailed contributor guidelines
├── README.md            # Project overview and examples
├── litellm/             # Core library code
├── tests/               # Test suite
├── docs/                # Documentation  
├── .github/workflows/   # CI/CD pipelines
└── enterprise/          # Enterprise features (optional)
```

## Support and Resources

- **Documentation:** https://docs.litellm.ai
- **Issues:** https://github.com/BerriAI/litellm/issues
- **Contributing Guide:** [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Architecture Details:** [CLAUDE.md](../CLAUDE.md) and [GEMINI.md](../GEMINI.md)

---

**Remember:** Always validate your changes work by running the proxy server and testing real endpoints. The instructions above have been validated and all timing estimates are based on actual measurements.