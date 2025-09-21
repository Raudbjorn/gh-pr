# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

gh-pr is a Python-based GitHub Pull Request review tool that enhances PR workflows with advanced filtering, automation, and rich terminal formatting. It's designed as a powerful replacement for basic bash scripts with enterprise-grade features.

## Development Commands

### Setup and Installation
```bash
# Install dependencies (uses hatchling build system)
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_token_manager.py

# Run tests with coverage
pytest --cov=src/gh_pr --cov-report=html

# Run integration tests
pytest tests/integration/

# Run unit tests only
pytest tests/unit/
```

### Code Quality
```bash
# Run all linting and formatting
ruff check src/ tests/
black src/ tests/
mypy src/

# Auto-fix linting issues
ruff check --fix src/ tests/

# Format code
black src/ tests/
```

## Architecture Overview

### Core Design Patterns

**Layered Architecture**: The application follows a clean layered architecture separating concerns:
- **CLI Layer** (`cli.py`): Click-based command interface with rich formatting
- **Core Layer** (`core/`): Business logic for PR management, GitHub API interactions
- **Auth Layer** (`auth/`): Token management and permission checking
- **Utils Layer** (`utils/`): Configuration, caching, logging, and export functionality
- **UI Layer** (`ui/`): Rich/Textual-based display and formatting

**Service Initialization Pattern**: The application uses a three-phase initialization:
1. **ConfigManager**: Loads configuration and sets up logging
2. **CacheManager**: Manages persistent caching with TTL
3. **TokenManager**: Handles GitHub authentication with multiple token sources

### Key Components

**TokenManager** (`auth/token.py`): Centralized authentication with token source priority:
1. Provided parameter → 2. GH_TOKEN env → 3. GITHUB_TOKEN env → 4. Config file → 5. gh CLI

**PRManager** (`core/pr_manager.py`): Core business logic orchestrating GitHub API calls, comment processing, and filtering. Integrates with both REST API (PyGithub) and GraphQL clients.

**Universal Logging** (`utils/rich_logger.py`): Rich-formatted logging with comprehensive features:
- Rich console output with colors and syntax highlighting
- File logging with automatic rotation (10MB max, 5 backups)
- Syslog integration for centralized logging (local and remote)
- Atlantic/Reykjavik timezone standardization (configurable)
- Session UUID tracking across all operations
- Security-aware environment variable masking (tokens, keys, passwords)
- Function tracing with `@traced` decorator for debugging
- Thread-safe operations with proper locking
- PEP-257 compliant docstrings and 44 comprehensive unit tests

**BatchOperations** (`core/batch.py`): Concurrent processing framework for multiple PRs with rate limiting, progress tracking, and error handling.

**CommentFilter** (`core/filters.py`): Sophisticated filtering system supporting:
- Unresolved comments, resolved comments, outdated comments
- Author-based filtering, date ranges, regex patterns
- Permission-aware operations

### Configuration System

**Hierarchical Configuration**:
- Global: `~/.config/gh-pr/config.toml`
- Project: `.gh-pr.toml`
- Runtime: CLI arguments override all

**Key Configuration Sections**:
```toml
[github]         # Token management and API settings
[display]        # UI formatting and themes
[cache]          # Caching behavior and TTL
[logging]        # Log levels, output, timezone
[clipboard]      # WSL2-aware clipboard settings
```

### Authentication Architecture

**Multi-Source Token Resolution**: TokenManager implements a priority-based token discovery system with validation and expiration checking. Permission checking is performed before any destructive operations.

**Fine-Grained Permissions**: PermissionChecker maps operations to required GitHub scopes and validates repository access levels (read/write/admin) before execution.

### Caching Strategy

**Intelligent Cache Invalidation**: CacheManager uses diskcache with TTL-based expiration and PR update detection. Cache keys incorporate PR metadata to automatically invalidate when PRs are updated.

### Error Handling Patterns

**Structured Exception Management**: All modules use consistent error handling with rich logging context. GitHub API errors include status codes and hint messages for common issues (401 → token permissions).

## Key File Relationships

- `cli.py` → orchestrates all managers and handles user interaction
- `pr_manager.py` → coordinates `github.py`, `comments.py`, `filters.py`
- `token.py` → integrates with `config.py` for persistent token storage
- `rich_logger.py` → used universally across all modules for consistent logging
- `batch.py` → uses `pr_manager.py` with concurrent execution and progress tracking

## Development Patterns

**Manager Pattern**: Core functionality is organized into manager classes (TokenManager, PRManager, CacheManager) that encapsulate related operations and maintain internal state.

**Factory Pattern**: `get_logger()` function provides module-specific loggers with consistent configuration.

**Decorator Pattern**: `@traced` decorator for automatic function entry/exit logging with parameter capture.

**Dependency Injection**: Managers accept dependencies through constructors rather than creating them internally, enabling easier testing and flexibility.

## Testing Architecture

**Comprehensive Test Coverage**: Tests are organized into unit tests (`tests/unit/`) and integration tests (`tests/integration/`) with extensive mocking of GitHub API calls.

**Test Categories**:
- **Unit tests**: Individual component testing with mocks
- **Integration tests**: End-to-end workflows with simulated GitHub responses
- **CLI tests**: Command-line interface testing with various argument combinations
- **Token tests**: Authentication flow testing across different token sources

## Special Considerations

**Rate Limiting**: All GitHub API interactions respect rate limits with configurable delays and concurrent request limiting.

**Security**: Sensitive data (tokens, secrets) is automatically masked in logs and never stored in plain text configuration.

**WSL2 Compatibility**: Clipboard operations are specifically designed to work in WSL2 environments.

**Session Tracking**: Every operation is tagged with a unique session UUID for correlation across logs and debugging.