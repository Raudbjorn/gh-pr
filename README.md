# gh-pr - GitHub PR Review Tool (Python Edition)

A powerful, feature-rich GitHub Pull Request review tool that enhances your PR workflow with advanced filtering, automation, and rich terminal formatting.

## Features

### Core Features (From Original Bash Script)
- [x] **Auto-detection**: Automatically finds PR for current branch or subdirectories
- [ ] **Interactive Mode**: Choose from all open PRs in a repository
- [x] **Advanced Filtering**:
  - [x] All comments
  - [x] Unresolved comments only
  - [x] Resolved but active comments
  - [x] Unresolved outdated comments
  - [x] Current unresolved only
- [x] **Code Context**: Show code snippets around comments with syntax highlighting
- [x] **Caching**: Smart caching with TTL and PR update detection
- [x] **Clipboard Support**: WSL2-aware clipboard functionality

### New Python Features
- [ ] **Token Management**:
  - [ ] Accept custom GitHub tokens via environment variable or config
  - [ ] Token validation and expiration checking
  - [ ] Display token expiration date and days remaining
  - [ ] Permission checking before executing commands
- [ ] **Enhanced PR Information**:
  - [ ] Show count of open PRs in repository
  - [ ] Display PR review status and approvals
  - [ ] Show CI/CD check status
  - [ ] Display merge conflicts status
- [ ] **Smart Automation**:
  - [ ] Auto-resolve outdated comments with permission check
  - [ ] Accept all suggestions with permission check
  - [ ] Batch operations support
- [ ] **Rich Terminal UI**:
  - [ ] Beautiful formatting with Rich library
  - [ ] Progress indicators and spinners
  - [ ] Color-coded status indicators
  - [ ] Interactive menus with keyboard navigation
- [ ] **Advanced Caching**:
  - [ ] Persistent cache across sessions
  - [ ] Cache invalidation strategies
  - [ ] Selective cache refresh
- [ ] **Configuration Management**:
  - [ ] User configuration file (~/.config/gh-pr/config.toml)
  - [ ] Project-specific settings (.gh-pr.toml)
  - [ ] Default filter preferences
  - [ ] Custom keyboard shortcuts
- [ ] **Export Capabilities**:
  - [ ] Export comments to Markdown
  - [ ] Generate review reports
  - [ ] CSV export for tracking
- [ ] **Batch Operations**:
  - [ ] Process multiple PRs at once
  - [ ] Bulk comment resolution
  - [ ] Mass suggestion acceptance
- [ ] **Webhook Support** (Future):
  - [ ] Real-time PR updates
  - [ ] Desktop notifications
- [ ] **Plugin System** (Future):
  - [ ] Custom filters
  - [ ] External tool integration
  - [ ] Custom formatters

## Installation

### Prerequisites
- Python 3.9+
- uv (for package management)
- Git

### Install with uv
```bash
# Clone the repository
git clone https://github.com/Raudbjorn/gh-pr.git
cd gh-pr

# Install as a tool with uv
uv tool install .

# Or for development
uv pip install -e .
```

## Usage

```bash
# Auto-detect PR from current branch
gh-pr

# Interactive mode - choose from open PRs
gh-pr -i

# View specific PR
gh-pr 123
gh-pr https://github.com/owner/repo/pull/123

# With custom token
GH_TOKEN=your_token gh-pr 123
# Or
gh-pr --token your_token 123

# Filter options
gh-pr --all                    # Show all comments
gh-pr --unresolved-outdated    # Show likely fixed issues
gh-pr --current-unresolved     # Show active issues only

# Automation (with permission checking)
gh-pr --resolve-outdated       # Auto-resolve outdated comments
gh-pr --accept-suggestions     # Accept all code suggestions

# Display options
gh-pr --no-code                # Don't show code context
gh-pr -v                       # Verbose output
gh-pr --checks                 # Show CI/CD status

# Export options
gh-pr --export markdown        # Export to Markdown
gh-pr --export csv            # Export to CSV

# Cache management
gh-pr --no-cache              # Bypass cache
gh-pr --clear-cache           # Clear all cache
```

## Configuration

### Global Configuration (~/.config/gh-pr/config.toml)
```toml
[github]
default_token = "ghp_..."
check_token_expiry = true

[display]
default_filter = "unresolved"
context_lines = 3
show_code = true
color_theme = "monokai"

[cache]
enabled = true
ttl_minutes = 5
location = "~/.cache/gh-pr"

[clipboard]
auto_strip_ansi = true
```

### Project Configuration (.gh-pr.toml)
```toml
[project]
default_repo = "owner/repo"
auto_fetch_on_startup = true

[filters]
custom_filters = [
    { name = "my_comments", query = "author:@me" }
]
```

## Development Status

### Phase 1: Core Functionality ✅
- [x] Project setup and structure
- [x] README with feature planning
- [ ] Basic PR fetching and display
- [ ] Comment filtering system
- [ ] Code context display

### Phase 2: Token Management 🚧
- [ ] Token validation and storage
- [ ] Permission checking system
- [ ] Token expiry monitoring

### Phase 3: Enhanced Features 📋
- [ ] Rich terminal formatting
- [ ] Interactive mode with TUI
- [ ] Advanced caching system
- [ ] Configuration management

### Phase 4: Automation & Export 📋
- [ ] Auto-resolve commands
- [ ] Suggestion acceptance
- [ ] Export functionality
- [ ] Batch operations

### Phase 5: Advanced Features 🔮
- [ ] Webhook support
- [ ] Plugin system
- [ ] Desktop notifications
- [ ] Multi-repo support

## Technical Stack

- **Core**: Python 3.9+
- **CLI Framework**: Click (with Typer consideration)
- **GitHub API**: PyGithub
- **Terminal UI**: Rich + Textual
- **Configuration**: TOML (tomli/tomli-w)
- **Caching**: diskcache
- **Testing**: pytest + pytest-mock
- **Type Checking**: mypy
- **Code Quality**: ruff, black

## Architecture

```
gh-pr/
├── src/
│   └── gh_pr/
│       ├── __init__.py
│       ├── __main__.py         # Entry point
│       ├── cli.py              # Click CLI definitions
│       ├── core/
│       │   ├── __init__.py
│       │   ├── github.py       # GitHub API interactions
│       │   ├── pr_manager.py   # PR business logic
│       │   ├── comments.py     # Comment processing
│       │   └── filters.py      # Filtering logic
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── token.py        # Token management
│       │   └── permissions.py  # Permission checking
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── display.py      # Rich formatting
│       │   ├── interactive.py  # TUI components
│       │   └── themes.py       # Color themes
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── cache.py        # Caching system
│       │   ├── clipboard.py    # Clipboard operations
│       │   ├── config.py       # Configuration management
│       │   └── export.py       # Export functionality
│       └── plugins/            # Future plugin system
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_*.py
├── pyproject.toml
├── README.md
├── LICENSE
└── gh-pr                       # Executable wrapper

```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.

## Credits

Original bash script inspiration and functionality baseline.
Enhanced Python implementation with additional features and improved user experience.