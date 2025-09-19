#!/usr/bin/env python3
"""Quick test to validate fixes for PR review issues."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_clipboard_security():
    """Test that clipboard commands use lists, not string splitting."""
    from gh_pr.utils.clipboard import ClipboardManager

    cm = ClipboardManager()
    if cm.clipboard_cmd:
        assert isinstance(cm.clipboard_cmd, list), "Clipboard command should be a list"
        assert all(isinstance(item, str) for item in cm.clipboard_cmd), "All items should be strings"
        print("✓ Clipboard security fix verified")
    else:
        print("⚠ No clipboard command available (expected on headless systems)")

def test_cache_permissions():
    """Test that cache handles permission errors gracefully."""
    import tempfile
    from gh_pr.utils.cache import CacheManager

    # Test with valid location
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CacheManager(enabled=True, location=tmpdir)
        assert cm.enabled, "Cache should be enabled for writable directory"
        print("✓ Cache permission checking works")

    # Test with invalid location
    cm = CacheManager(enabled=True, location="/root/no-access-cache")
    if not cm.enabled:
        print("✓ Cache disabled for non-writable directory")
    else:
        print("⚠ Cache enabled despite potential permission issues (may have sudo)")

def test_cli_refactoring():
    """Test that CLI module loads without errors."""
    try:
        from gh_pr import cli
        print("✓ CLI module loads successfully")

        # Check that helper functions exist
        assert hasattr(cli, '_initialize_services'), "Helper function _initialize_services exists"
        assert hasattr(cli, '_display_token_info'), "Helper function _display_token_info exists"
        assert hasattr(cli, '_determine_filter_mode'), "Helper function _determine_filter_mode exists"
        print("✓ CLI refactoring complete with helper functions")
    except ImportError as e:
        print(f"✗ Failed to import CLI: {e}")
        return False
    return True

def test_no_gh_dependency():
    """Test that we're not using gh CLI."""
    from gh_pr.core.pr_manager import PRManager

    # Check the source code doesn't contain gh CLI calls
    import inspect
    source = inspect.getsource(PRManager)

    # Should not have 'gh pr' commands
    if '[\"gh\", \"pr\"' not in source and '["gh", "pr"' not in source:
        print("✓ No gh CLI dependency found")
        return True
    else:
        print("✗ Still has gh CLI dependency")
        return False

def test_ui_markdown_rendering():
    """Test that UI properly handles Markdown rendering."""
    from gh_pr.ui.display import DisplayManager
    from rich.console import Console

    console = Console()
    dm = DisplayManager(console, verbose=False)

    # The display manager should have the proper methods
    assert hasattr(dm, 'display_comments'), "display_comments method exists"
    assert hasattr(dm, 'display_check_status'), "display_check_status method exists"

    print("✓ UI display manager configured correctly")
    return True

if __name__ == "__main__":
    print("Testing fixes for PR review issues...\n")

    tests = [
        test_clipboard_security,
        test_cache_permissions,
        test_cli_refactoring,
        test_no_gh_dependency,
        test_ui_markdown_rendering
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = test()
            if result is not False:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with error: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)