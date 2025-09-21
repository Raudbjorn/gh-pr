"""
Unit tests for utils.config module.

Tests configuration management functionality.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w

from gh_pr.utils.config import ConfigManager, _validate_config_path, ALLOWED_CONFIG_DIRS


class TestValidateConfigPath(unittest.TestCase):
    """Test _validate_config_path function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_config_path_allowed_directory(self):
        """Test validation with path in allowed directory."""
        # Use current working directory (which is in ALLOWED_CONFIG_DIRS)
        config_path = Path.cwd() / "test_config.toml"

        result = _validate_config_path(config_path)
        self.assertTrue(result)

    def test_validate_config_path_home_directory(self):
        """Test validation with path in home directory."""
        config_path = Path.home() / ".gh-pr.toml"

        result = _validate_config_path(config_path)
        self.assertTrue(result)

    def test_validate_config_path_user_config_directory(self):
        """Test validation with path in user config directory."""
        config_path = Path.home() / ".config" / "gh-pr" / "config.toml"

        result = _validate_config_path(config_path)
        self.assertTrue(result)

    def test_validate_config_path_disallowed_directory(self):
        """Test validation with path outside allowed directories."""
        # Use a path that's definitely not in allowed directories
        config_path = Path("/etc/passwd")

        with patch('gh_pr.utils.config.logger') as mock_logger:
            result = _validate_config_path(config_path)

            self.assertFalse(result)
            mock_logger.warning.assert_called_once()
            self.assertIn("Config path not in allowed directories", mock_logger.warning.call_args[0][0])

    def test_validate_config_path_relative_path(self):
        """Test validation with relative path."""
        config_path = Path("./config.toml")

        result = _validate_config_path(config_path)
        self.assertTrue(result)  # Should resolve to current directory

    def test_validate_config_path_symlink(self):
        """Test validation with symlink path."""
        # Create a symlink in temp directory pointing to allowed location
        target_path = Path.cwd() / "target_config.toml"
        symlink_path = self.temp_dir / "symlink_config.toml"

        try:
            symlink_path.symlink_to(target_path)
            result = _validate_config_path(symlink_path)
            self.assertTrue(result)  # Should resolve symlink and validate target
        except OSError:
            # Skip test if symlinks not supported
            self.skipTest("Symlinks not supported on this platform")

    def test_validate_config_path_os_error(self):
        """Test validation handling OS errors."""
        # Mock Path.resolve to raise OSError
        with patch('pathlib.Path.resolve', side_effect=OSError("Permission denied")):
            with patch('gh_pr.utils.config.logger') as mock_logger:
                result = _validate_config_path(Path("test"))

                self.assertFalse(result)
                mock_logger.warning.assert_called_once()
                self.assertIn("Failed to validate config path", mock_logger.warning.call_args[0][0])


class TestConfigManager(unittest.TestCase):
    """Test ConfigManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_no_config_file(self):
        """Test initialization when no config file exists."""
        with patch.object(ConfigManager, '_find_config_file', return_value=None):
            manager = ConfigManager()

            # Should use default config
            self.assertEqual(manager.config, ConfigManager.DEFAULT_CONFIG)
            self.assertIsNone(manager.config_path)

    def test_init_with_existing_config_file(self):
        """Test initialization with existing config file."""
        config_path = self.temp_dir / "test_config.toml"

        # Create a test config file
        test_config = {
            "github": {"default_token": "test_token"},
            "display": {"default_filter": "all"}
        }

        with open(config_path, "wb") as f:
            tomli_w.dump(test_config, f)

        with patch.object(ConfigManager, '_find_config_file', return_value=config_path):
            manager = ConfigManager()

            # Should merge with defaults
            self.assertEqual(manager.config["github"]["default_token"], "test_token")
            self.assertEqual(manager.config["display"]["default_filter"], "all")
            # Should preserve defaults not overridden
            self.assertEqual(manager.config["display"]["context_lines"], 3)

    def test_init_with_explicit_config_path(self):
        """Test initialization with explicit config path."""
        config_path = self.temp_dir / "explicit_config.toml"

        # Create config file
        test_config = {"github": {"default_token": "explicit_token"}}
        with open(config_path, "wb") as f:
            tomli_w.dump(test_config, f)

        # Mock validation to pass
        with patch('gh_pr.utils.config._validate_config_path', return_value=True):
            manager = ConfigManager(config_path=str(config_path))

            self.assertEqual(manager.config["github"]["default_token"], "explicit_token")

    def test_init_with_invalid_explicit_config_path(self):
        """Test initialization with invalid explicit config path."""
        invalid_path = "/invalid/path/config.toml"

        with patch('gh_pr.utils.config._validate_config_path', return_value=False):
            with patch('gh_pr.utils.config.logger') as mock_logger:
                manager = ConfigManager(config_path=invalid_path)

                # Should use defaults and log warning
                self.assertEqual(manager.config, ConfigManager.DEFAULT_CONFIG)
                self.assertIsNone(manager.config_path)
                mock_logger.warning.assert_called_once()

    def test_find_config_file_precedence(self):
        """Test config file location precedence."""
        # Create config files in different locations
        project_config = self.temp_dir / ".gh-pr.toml"
        user_config = self.temp_dir / ".config" / "gh-pr" / "config.toml"
        legacy_config = self.temp_dir / ".gh-pr.toml"

        # Create project config
        project_config.write_text("[github]\ndefault_token = 'project'")

        # Mock Path.home() to return our temp directory
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            with patch('pathlib.Path.cwd', return_value=self.temp_dir):
                with patch('gh_pr.utils.config._validate_config_path', return_value=True):
                    manager = ConfigManager()

                    # Should find the project config (.gh-pr.toml in current dir)
                    found_config = manager._find_config_file()
                    self.assertEqual(found_config.name, ".gh-pr.toml")

    def test_find_config_file_user_config_directory(self):
        """Test finding config in user config directory."""
        user_config_dir = self.temp_dir / ".config" / "gh-pr"
        user_config_dir.mkdir(parents=True)
        user_config = user_config_dir / "config.toml"
        user_config.write_text("[github]\ndefault_token = 'user'")

        with patch('pathlib.Path.home', return_value=self.temp_dir):
            with patch('pathlib.Path.cwd', return_value=Path("/nonexistent")):
                with patch('gh_pr.utils.config._validate_config_path', return_value=True):
                    manager = ConfigManager()

                    found_config = manager._find_config_file()
                    self.assertEqual(found_config, user_config)

    def test_load_config_file_not_found(self):
        """Test _load_config when file doesn't exist."""
        manager = ConfigManager()
        manager.config_path = Path("/nonexistent/config.toml")

        # Should not raise exception
        manager._load_config()
        # Config should remain as defaults
        self.assertEqual(manager.config, ConfigManager.DEFAULT_CONFIG)

    def test_load_config_permission_error(self):
        """Test _load_config with permission error."""
        config_path = self.temp_dir / "readonly_config.toml"
        config_path.write_text("[github]\ndefault_token = 'test'")
        config_path.chmod(0o000)  # Make unreadable

        manager = ConfigManager()
        manager.config_path = config_path

        try:
            with patch('gh_pr.utils.config.logger') as mock_logger:
                manager._load_config()

                # Should use defaults and log debug message
                self.assertEqual(manager.config, ConfigManager.DEFAULT_CONFIG)
        finally:
            # Restore permissions for cleanup
            config_path.chmod(0o644)

    def test_load_config_invalid_toml(self):
        """Test _load_config with invalid TOML syntax."""
        config_path = self.temp_dir / "invalid_config.toml"
        config_path.write_text("invalid toml [[[")

        manager = ConfigManager()
        manager.config_path = config_path

        with patch('gh_pr.utils.config.logger') as mock_logger:
            manager._load_config()

            # Should use defaults and log debug message
            self.assertEqual(manager.config, ConfigManager.DEFAULT_CONFIG)

    def test_merge_config_simple(self):
        """Test _merge_config with simple values."""
        manager = ConfigManager()
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}

        manager._merge_config(base, update)

        expected = {"a": 1, "b": 3, "c": 4}
        self.assertEqual(base, expected)

    def test_merge_config_nested(self):
        """Test _merge_config with nested dictionaries."""
        manager = ConfigManager()
        base = {
            "github": {"token": "old", "timeout": 30},
            "display": {"theme": "dark"}
        }
        update = {
            "github": {"token": "new"},
            "cache": {"enabled": True}
        }

        manager._merge_config(base, update)

        expected = {
            "github": {"token": "new", "timeout": 30},
            "display": {"theme": "dark"},
            "cache": {"enabled": True}
        }
        self.assertEqual(base, expected)

    def test_merge_config_type_override(self):
        """Test _merge_config when update changes value type."""
        manager = ConfigManager()
        base = {"config": {"value": "string"}}
        update = {"config": 42}  # Override dict with int

        manager._merge_config(base, update)

        self.assertEqual(base["config"], 42)

    def test_get_simple_key(self):
        """Test get with simple key."""
        manager = ConfigManager()
        manager.config = {"test_key": "test_value"}

        result = manager.get("test_key")
        self.assertEqual(result, "test_value")

    def test_get_nested_key(self):
        """Test get with dot-separated nested key."""
        manager = ConfigManager()
        manager.config = {
            "github": {"default_token": "test_token"},
            "display": {"context_lines": 5}
        }

        result = manager.get("github.default_token")
        self.assertEqual(result, "test_token")

        result = manager.get("display.context_lines")
        self.assertEqual(result, 5)

    def test_get_nonexistent_key(self):
        """Test get with nonexistent key."""
        manager = ConfigManager()

        result = manager.get("nonexistent")
        self.assertIsNone(result)

        result = manager.get("nonexistent.nested")
        self.assertIsNone(result)

    def test_get_with_default(self):
        """Test get with default value."""
        manager = ConfigManager()

        result = manager.get("nonexistent", "default_value")
        self.assertEqual(result, "default_value")

        result = manager.get("nonexistent.nested", 42)
        self.assertEqual(result, 42)

    def test_get_partial_path_exists(self):
        """Test get when partial path exists but not full path."""
        manager = ConfigManager()
        manager.config = {"github": {"token": "test"}}

        result = manager.get("github.nonexistent", "default")
        self.assertEqual(result, "default")

    def test_set_simple_key(self):
        """Test set with simple key."""
        manager = ConfigManager()

        manager.set("test_key", "test_value")
        self.assertEqual(manager.config["test_key"], "test_value")

    def test_set_nested_key(self):
        """Test set with dot-separated nested key."""
        manager = ConfigManager()

        manager.set("github.default_token", "new_token")
        self.assertEqual(manager.config["github"]["default_token"], "new_token")

        manager.set("new.nested.key", "value")
        self.assertEqual(manager.config["new"]["nested"]["key"], "value")

    def test_set_override_existing(self):
        """Test set overriding existing value."""
        manager = ConfigManager()
        manager.config = {"github": {"token": "old"}}

        manager.set("github.token", "new")
        self.assertEqual(manager.config["github"]["token"], "new")

    def test_save_success(self):
        """Test successful save operation."""
        config_path = self.temp_dir / "save_test.toml"

        manager = ConfigManager()
        manager.config = {"test": {"value": "saved"}}

        with patch('gh_pr.utils.config._validate_config_path', return_value=True):
            result = manager.save(str(config_path))

            self.assertTrue(result)
            self.assertTrue(config_path.exists())

            # Verify saved content
            with open(config_path, "rb") as f:
                saved_config = tomllib.load(f)
            self.assertEqual(saved_config["test"]["value"], "saved")

    def test_save_with_config_path(self):
        """Test save using manager's config_path."""
        config_path = self.temp_dir / "manager_config.toml"

        manager = ConfigManager()
        manager.config_path = config_path
        manager.config = {"saved": True}

        with patch('gh_pr.utils.config._validate_config_path', return_value=True):
            result = manager.save()

            self.assertTrue(result)
            self.assertTrue(config_path.exists())

    def test_save_default_location(self):
        """Test save to default location when no path specified."""
        manager = ConfigManager()
        manager.config_path = None
        manager.config = {"default": "location"}

        default_path = Path.home() / ".config" / "gh-pr" / "config.toml"

        with patch('gh_pr.utils.config._validate_config_path', return_value=True):
            with patch('pathlib.Path.mkdir') as mock_mkdir:
                with patch('builtins.open', mock_open()) as mock_file:
                    with patch('tomli_w.dump') as mock_dump:
                        result = manager.save()

                        self.assertTrue(result)
                        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
                        mock_dump.assert_called_once()

    def test_save_invalid_path(self):
        """Test save with invalid path."""
        manager = ConfigManager()

        with patch('gh_pr.utils.config._validate_config_path', return_value=False):
            with patch('gh_pr.utils.config.logger') as mock_logger:
                result = manager.save("/invalid/path/config.toml")

                self.assertFalse(result)
                mock_logger.error.assert_called_once()

    def test_save_permission_error(self):
        """Test save with permission error."""
        readonly_dir = self.temp_dir / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        config_path = readonly_dir / "config.toml"

        manager = ConfigManager()

        try:
            with patch('gh_pr.utils.config._validate_config_path', return_value=True):
                with patch('gh_pr.utils.config.logger') as mock_logger:
                    result = manager.save(str(config_path))

                    self.assertFalse(result)
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)

    def test_save_type_error(self):
        """Test save with type error (unserializable config)."""
        manager = ConfigManager()
        # Create config with unserializable object
        manager.config = {"func": lambda x: x}

        config_path = self.temp_dir / "type_error.toml"

        with patch('gh_pr.utils.config._validate_config_path', return_value=True):
            with patch('gh_pr.utils.config.logger') as mock_logger:
                result = manager.save(str(config_path))

                self.assertFalse(result)

    def test_default_config_structure(self):
        """Test that DEFAULT_CONFIG has expected structure."""
        config = ConfigManager.DEFAULT_CONFIG

        # Test top-level sections exist
        self.assertIn("github", config)
        self.assertIn("display", config)
        self.assertIn("cache", config)
        self.assertIn("clipboard", config)

        # Test github section
        self.assertIn("default_token", config["github"])
        self.assertIn("check_token_expiry", config["github"])

        # Test display section
        self.assertIn("default_filter", config["display"])
        self.assertIn("context_lines", config["display"])
        self.assertIn("show_code", config["display"])
        self.assertIn("color_theme", config["display"])

        # Test cache section
        self.assertIn("enabled", config["cache"])
        self.assertIn("ttl_minutes", config["cache"])
        self.assertIn("location", config["cache"])

        # Test clipboard section
        self.assertIn("auto_strip_ansi", config["clipboard"])

    def test_allowed_config_dirs_defined(self):
        """Test that ALLOWED_CONFIG_DIRS is properly defined."""
        self.assertIsInstance(ALLOWED_CONFIG_DIRS, list)
        self.assertGreater(len(ALLOWED_CONFIG_DIRS), 0)

        # Should include current directory and user config locations
        cwd_included = any(str(path) == str(Path.cwd()) for path in ALLOWED_CONFIG_DIRS)
        home_included = any(str(Path.home()) in str(path) for path in ALLOWED_CONFIG_DIRS)

        self.assertTrue(cwd_included or home_included)


if __name__ == '__main__':
    unittest.main()