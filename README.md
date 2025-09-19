# gh-pr - GitHub PR Review Tool (Python Edition)

A powerful, feature-rich GitHub Pull Request review tool that enhances your PR workflow with advanced filtering, automation, and rich terminal formatting.

## Features

### Core Features (From Original Bash Script)
- [x] **Auto-detection**: Automatically finds PR for current branch or subdirectories
- [x] **Interactive Mode**: Choose from all open PRs in a repository
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
- [x] **Token Management**:
  - [x] Accept custom GitHub tokens via environment variable or config
  - [x] Token validation and expiration checking
  - [x] Display token expiration date and days remaining
  - [x] Permission checking before executing commands
- [x] **Enhanced PR Information**:
  - [x] Show count of open PRs in repository
  - [x] Display PR review status and approvals
  - [x] Show CI/CD check status
  - [x] Display merge conflicts status
- [x] **Smart Automation**:
  - [x] Auto-resolve outdated comments with permission check
  - [x] Accept all suggestions with permission check
  - [x] Batch operations support
- [x] **Rich Terminal UI**:
  - [x] Beautiful formatting with Rich library
  - [x] Progress indicators and spinners
  - [x] Color-coded status indicators
  - [x] Interactive menus with keyboard navigation
- [x] **Advanced Caching**:
  - [x] Persistent cache across sessions
  - [x] Cache invalidation strategies
  - [x] Selective cache refresh
- [x] **Configuration Management**:
  - [x] User configuration file (~/.config/gh-pr/config.toml)
  - [x] Project-specific settings (.gh-pr.toml)
  - [x] Default filter preferences
  - [x] Custom keyboard shortcuts
- [x] **Export Capabilities**:
  - [x] Export comments to Markdown
  - [x] Generate review reports
  - [x] CSV export for tracking
- [x] **Batch Operations**:
  - [x] Process multiple PRs at once
  - [x] Bulk comment resolution
  - [x] Mass suggestion acceptance
- [x] **Interactive TUI Mode**:
  - [x] Full terminal user interface with Textual
  - [x] Real-time PR browsing and filtering
  - [x] Vim-style keyboard navigation (j/k for up/down)
  - [x] Interactive filter and sort menus
  - [x] Theme system with 6 predefined themes (default, dark, light, monokai, dracula, github)
  - [x] Export functionality from within TUI
  - [x] Help screen with keyboard shortcuts
  - [x] Search functionality for PRs and comments
  - [x] PR details view with comment threads
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

# Launch interactive TUI mode (Terminal User Interface)
gh-pr --tui

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

## TUI Mode

Launch the interactive Terminal User Interface with `gh-pr --tui` for a full-featured PR review experience.

### Keyboard Shortcuts

| Key | Action | Description |
|-----|--------|-------------|
| `q` | Quit | Exit the application |
| `r` | Refresh | Reload PR data |
| `j` / `↓` | Next | Move to next item |
| `k` / `↑` | Previous | Move to previous item |
| `g` | Top | Go to first item |
| `G` | Bottom | Go to last item |
| `Enter` | Select | View PR details |
| `/` | Search | Focus the search input |
| `s` | Sort | Open sort menu |
| `e` | Export | Export data |
| `c` | Copy | Copy to clipboard |
| `o` | Browser | Open in browser |
| `,` | Settings | Open settings menu |
| `?` | Help | Show help screen |
| `Tab` | Next pane | Switch focus to next pane |
| `Shift+Tab` | Prev pane | Switch focus to previous pane |

### Available Themes

The TUI supports multiple color themes that can be switched from the settings menu:
- **default**: VSCode-inspired dark theme
- **dark**: GitHub dark mode
- **light**: GitHub light mode
- **monokai**: Classic Monokai theme
- **dracula**: Dracula theme
- **github**: Classic GitHub theme

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

### Phase 1: Core Conversion ✅
- [x] Basic PR fetching and display
- [x] Comment filtering system
- [x] Code context display

### Phase 2: Token Management ✅
- [x] Token validation and storage
- [x] Permission checking system
- [x] Token expiry monitoring

### Phase 3: Enhanced Features ✅
- [x] Rich terminal formatting
- [x] Interactive mode with TUI
- [x] Advanced caching system
- [x] Configuration management

### Phase 4: Automation & Export ✅
- [x] Auto-resolve commands
- [x] Suggestion acceptance
- [x] Export functionality
- [x] Batch operations

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