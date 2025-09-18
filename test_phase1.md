# Phase 1 Test File

This file is created to test the Phase 1 features of gh-pr:

## Features Tested
1. Basic PR fetching and display
2. Comment filtering system
3. Code context display

## Test Results
- ✅ Basic PR fetching works with `gh-pr 1`
- ✅ Filter modes work (`--all`, `--unresolved-outdated`, etc.)
- ✅ Code context display works (shown by default, hidden with `--no-code`)

## Example Commands
```bash
# Fetch PR #1
gh-pr 1 -r Raudbjorn/gh-pr

# Show all comments
gh-pr 1 -r Raudbjorn/gh-pr --all

# Show unresolved outdated comments
gh-pr 1 -r Raudbjorn/gh-pr --unresolved-outdated

# Hide code context
gh-pr 1 -r Raudbjorn/gh-pr --no-code
```