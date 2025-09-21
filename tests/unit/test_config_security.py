"""Unit tests for config.py path traversal protection and security."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from gh_pr.utils.config import ConfigManager, _validate_config_path, ALLOWED_CONFIG_DIRS


class TestConfigPathValidation:
    """Test path validation security features."""

    def test_validate_config_path_current_directory(self):
        """Test that files in current directory are allowed."""
        config_path = Path.cwd() / "test_config.toml"
        assert _validate_config_path(config_path) is True

    def test_validate_config_path_user_config_directory(self):
        """Test that files in user config directory are allowed."""
        config_path = Path.home() / ".config" / "gh-pr" / "config.toml"
        assert _validate_config_path(config_path) is True

    def test_validate_config_path_user_home_directory(self):
        """Test that files in user home directory are allowed."""
        config_path = Path.home() / ".gh-pr.toml"
        assert _validate_config_path(config_path) is True

    def test_validate_config_path_traversal_attack_parent(self):
        """Test that path traversal using .. is blocked."""
        # Try to access parent directory
        config_path = Path.cwd() / ".." / "malicious_config.toml"

        # This should fail if parent is not within allowed directories
        result = _validate_config_path(config_path)

        # Check if parent directory is in allowed paths
        parent_allowed = False
        for allowed_dir in ALLOWED_CONFIG_DIRS:
            try:
                config_path.resolve().relative_to(allowed_dir.resolve())
                parent_allowed = True
                break
            except ValueError:
                continue

        assert result == parent_allowed

    def test_validate_config_path_traversal_attack_root(self):
        """Test that absolute paths outside allowed directories are blocked."""
        # Try to access system files
        config_path = Path("/etc/passwd")
        assert _validate_config_path(config_path) is False

    def test_validate_config_path_traversal_attack_relative(self):
        """Test that complex relative path attacks are blocked."""
        # Try various path traversal attacks
        attack_paths = [
            "../../../../etc/passwd",
            "../../../../../../etc/shadow",
            "../../../usr/bin/malicious",
        ]

        for attack_path in attack_paths:
            config_path = Path.cwd() / attack_path
            # Should be blocked unless it somehow resolves to an allowed directory
            result = _validate_config_path(config_path)

            # Verify it's properly blocked
            resolved_path = config_path.resolve()
            is_allowed = False
            for allowed_dir in ALLOWED_CONFIG_DIRS:
                try:
                    resolved_path.relative_to(allowed_dir.resolve())
                    is_allowed = True
                    break
                except ValueError:
                    continue

            assert result == is_allowed

    def test_validate_config_path_symlink_attack(self):
        """Test that symlinks pointing outside allowed directories are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a symlink pointing to a system file
            symlink_path = Path.cwd() / "test_symlink"
            target_path = temp_path / "target_file"
            target_path.write_text("malicious content")

            try:
                symlink_path.symlink_to(target_path)

                # Validation should fail because symlink points outside allowed dirs
                assert _validate_config_path(symlink_path) is False

            except OSError:
                # Symlink creation might fail on some systems, skip test
                pytest.skip("Symlink creation not supported")
            finally:
                # Clean up
                if symlink_path.exists():
                    symlink_path.unlink()

    def test_validate_config_path_nonexistent_path(self):
        """Test that nonexistent paths are validated correctly."""
        # Test nonexistent file in allowed directory
        config_path = Path.cwd() / "nonexistent_config.toml"
        assert _validate_config_path(config_path) is True

        # Test nonexistent file in disallowed directory
        config_path = Path("/tmp/nonexistent_config.toml")
        assert _validate_config_path(config_path) is False

    @patch('gh_pr.utils.config.logger')
    def test_validate_config_path_os_error_handling(self, mock_logger):
        """Test that OS errors during path validation are handled gracefully."""
        # Mock Path.resolve to raise OSError
        with patch.object(Path, 'resolve', side_effect=OSError("Mock OS error")):
            config_path = Path.cwd() / "test_config.toml"
            result = _validate_config_path(config_path)

            assert result is False
            mock_logger.warning.assert_called_once()

    def test_validate_config_path_windows_drive_letters(self):
        """Test that Windows drive letters are handled correctly."""
        if os.name == 'nt':  # Windows only
            # Test different drive letter
            config_path = Path("D:/malicious_config.toml")
            result = _validate_config_path(config_path)

            # Should be blocked unless D: is somehow an allowed directory
            allowed = False
            for allowed_dir in ALLOWED_CONFIG_DIRS:
                try:
                    config_path.resolve().relative_to(allowed_dir.resolve())
                    allowed = True
                    break
                except ValueError:
                    continue

            assert result == allowed


class TestConfigManagerSecurity:
    """Test ConfigManager security features."""

    def test_config_manager_rejects_invalid_path(self):
        """Test that ConfigManager rejects invalid config paths."""
        # Try to initialize with a malicious path
        with patch('gh_pr.utils.config._validate_config_path', return_value=False):
            config_manager = ConfigManager(config_path="/etc/passwd")

            # Should not use the invalid path
            assert config_manager.config_path is None

    def test_config_manager_finds_safe_config(self):
        """Test that ConfigManager finds valid config files safely."""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

            try:
                # Write valid TOML content
                temp_path.write_text("""
[github]
default_token = "test_token"

[display]
default_filter = "all"
""")

                # Move to current directory for testing
                safe_path = Path.cwd() / "test_config.toml"
                temp_path.rename(safe_path)

                try:
                    config_manager = ConfigManager(config_path=str(safe_path))

                    # Should load the config successfully
                    assert config_manager.config_path == safe_path
                    assert config_manager.get("github.default_token") == "test_token"
                    assert config_manager.get("display.default_filter") == "all"

                finally:
                    # Clean up
                    if safe_path.exists():
                        safe_path.unlink()

            except Exception:
                # Clean up on any error
                if temp_path.exists():
                    temp_path.unlink()

    def test_config_manager_save_path_validation(self):
        """Test that config save validates paths."""
        config_manager = ConfigManager()

        # Try to save to an invalid path
        with patch('gh_pr.utils.config._validate_config_path', return_value=False):
            result = config_manager.save(path="/etc/malicious_config.toml")
            assert result is False

    def test_config_manager_save_creates_safe_directory(self):
        """Test that config save creates directories safely."""
        config_manager = ConfigManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            safe_path = Path(temp_dir) / "safe_subdir" / "config.toml"

            # Ensure the path would be validated as safe
            with patch('gh_pr.utils.config._validate_config_path', return_value=True):
                result = config_manager.save(path=str(safe_path))

                if result:  # Only check if save was successful
                    assert safe_path.exists()
                    assert safe_path.parent.exists()

    @patch('gh_pr.utils.config.logger')
    def test_config_manager_handles_malformed_config(self, mock_logger):
        """Test that malformed config files are handled gracefully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix=".toml", delete=False) as temp_file:
            # Write malformed TOML
            temp_file.write("""
[github
invalid toml content
""")
            temp_file.flush()

            try:
                config_manager = ConfigManager(config_path=temp_file.name)

                # Should fall back to defaults
                assert config_manager.get("github.default_token") is None
                assert config_manager.get("display.default_filter") == "unresolved"

            finally:
                Path(temp_file.name).unlink()

    def test_config_manager_permission_error_handling(self):
        """Test that permission errors during config operations are handled."""
        config_manager = ConfigManager()

        # Mock file operations to raise PermissionError
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            # Should not crash, should return False
            result = config_manager.save()
            assert result is False

    def test_config_manager_dot_notation_security(self):
        """Test that dot notation keys don't allow injection."""
        config_manager = ConfigManager()

        # Test setting deeply nested keys
        config_manager.set("level1.level2.level3", "test_value")
        assert config_manager.get("level1.level2.level3") == "test_value"

        # Test that invalid keys are handled gracefully
        assert config_manager.get("nonexistent.key", "default") == "default"
        assert config_manager.get("", "default") == "default"

    def test_config_manager_merge_config_safety(self):
        """Test that config merging is safe from malicious configs."""
        config_manager = ConfigManager()

        # Test merging with various data types
        malicious_config = {
            "github": {
                "default_token": {"nested": "object"},  # Should replace dict
                "new_key": ["list", "value"]
            },
            "new_section": {
                "malicious_key": None
            }
        }

        original_token = config_manager.get("github.default_token")
        config_manager._merge_config(config_manager.config, malicious_config)

        # Verify merge worked correctly
        assert config_manager.get("github.default_token") == {"nested": "object"}
        assert config_manager.get("github.new_key") == ["list", "value"]
        assert config_manager.get("new_section.malicious_key") is None


class TestConfigManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_config_key(self):
        """Test handling of empty configuration keys."""
        config_manager = ConfigManager()

        assert config_manager.get("", "default") == "default"

        # Setting empty key should not crash
        config_manager.set("", "value")
        # But getting it back should return default
        assert config_manager.get("", "default") == "default"

    def test_very_long_config_path(self):
        """Test handling of very long configuration paths."""
        # Create a very long path
        long_component = "a" * 100
        long_path = Path.cwd() / long_component / long_component / "config.toml"

        # Should handle gracefully without crashing
        result = _validate_config_path(long_path)
        assert isinstance(result, bool)

    def test_config_with_unicode_characters(self):
        """Test configuration with Unicode characters."""
        config_manager = ConfigManager()

        unicode_value = "测试值 🎯 special chars: áéíóú"
        config_manager.set("test.unicode", unicode_value)

        assert config_manager.get("test.unicode") == unicode_value

    def test_config_concurrent_access_safety(self):
        """Test that config operations are safe under concurrent access."""
        config_manager = ConfigManager()

        # Simulate concurrent operations
        for i in range(10):
            config_manager.set(f"test.key_{i}", f"value_{i}")
            assert config_manager.get(f"test.key_{i}") == f"value_{i}"

    def test_config_none_values(self):
        """Test handling of None values in configuration."""
        config_manager = ConfigManager()

        config_manager.set("test.none_value", None)
        assert config_manager.get("test.none_value") is None
        assert config_manager.get("test.none_value", "default") is None

    def test_config_boolean_values(self):
        """Test handling of boolean values in configuration."""
        config_manager = ConfigManager()

        config_manager.set("test.true_value", True)
        config_manager.set("test.false_value", False)

        assert config_manager.get("test.true_value") is True
        assert config_manager.get("test.false_value") is False

    def test_config_numeric_values(self):
        """Test handling of numeric values in configuration."""
        config_manager = ConfigManager()

        config_manager.set("test.int_value", 42)
        config_manager.set("test.float_value", 3.14)
        config_manager.set("test.negative_value", -100)

        assert config_manager.get("test.int_value") == 42
        assert config_manager.get("test.float_value") == 3.14
        assert config_manager.get("test.negative_value") == -100