# Security Audit: Subprocess Usage

This document provides a security analysis of all subprocess calls in the gh-pr codebase.

## Security Principles

All subprocess calls in this codebase follow these security principles:

1. **No User Input in Commands**: Commands are hardcoded constants, never constructed from user input
2. **Explicit Command Lists**: Use list format (`["cmd", "arg"]`) to prevent shell injection
3. **Timeout Protection**: All calls have timeouts to prevent hanging processes
4. **Error Handling**: Proper exception handling for all subprocess failures
5. **Minimal Privileges**: Commands are run with minimal necessary privileges

## Subprocess Usage Analysis

### 1. Git Operations (src/gh_pr/core/pr_manager.py)

**Location**: Lines 129, 169, 177, 250
**Commands Used**:
- `["git", "remote", "get-url", "origin"]`
- `["git", "rev-parse", "--git-dir"]`
- `["git", "branch", "--show-current"]`

**Security Assessment**: ✅ SAFE
- All commands are hardcoded constant lists
- No user input incorporated into commands
- Used for read-only git repository information
- Proper timeout and error handling
- Commands are standard git operations with no privilege escalation

### 2. GitHub CLI Token Operations (src/gh_pr/auth/token.py)

**Location**: Lines 105, 124
**Commands Used**:
- `GH_CLI_AUTH_STATUS_CMD = ["gh", "auth", "status", "--show-token"]`
- `GH_CLI_AUTH_TOKEN_CMD = ["gh", "auth", "token"]`

**Security Assessment**: ✅ SAFE
- Commands are defined as module-level constants
- No user input can influence command construction
- Used for authentication token retrieval from GitHub CLI
- Proper timeout and error handling
- Read-only operations that don't modify system state

### 3. Clipboard Operations (src/gh_pr/utils/clipboard.py)

**Location**: Lines 70-77
**Commands Used**:
- Platform-detected clipboard commands (pbcopy, xclip, clip.exe)
- Commands determined by `_detect_clipboard_command()` method

**Security Assessment**: ✅ SAFE
- Clipboard commands are detected and validated during initialization
- No user input incorporated into command execution
- Commands are selected from predefined safe options
- Timeout protection (5 seconds) prevents hanging
- Used only for copying text to system clipboard

## Risk Mitigation Strategies

### Command Injection Prevention
- **List Format**: All subprocess calls use list format instead of shell strings
- **No String Interpolation**: No user input is interpolated into commands
- **Constant Commands**: All commands are predefined constants or safely detected system commands

### Process Control
- **Timeouts**: All subprocess calls have explicit or implicit timeouts
- **Resource Limits**: Commands are limited to read-only operations or safe system utilities
- **Error Handling**: Comprehensive exception handling prevents uncontrolled failures

### Privilege Management
- **No Elevation**: No commands require or attempt privilege escalation
- **User Context**: All commands run in the current user's security context
- **Read-Only**: Most operations are read-only (git info, auth status)

## Testing Coverage

All subprocess operations are covered by unit tests that:
- Mock subprocess calls to prevent actual execution during testing
- Verify proper error handling for subprocess failures
- Test timeout scenarios
- Validate command structure and arguments

## Conclusion

All subprocess usage in gh-pr follows security best practices:
- No command injection vulnerabilities
- No privilege escalation risks
- Proper error handling and timeout protection
- Comprehensive test coverage

The subprocess calls are necessary for:
1. Git repository information (branch detection, remote URLs)
2. GitHub CLI integration (token retrieval)
3. System clipboard integration (output copying)

All operations are safe and follow the principle of least privilege.