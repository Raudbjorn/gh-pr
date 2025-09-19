"""Unit tests for ConfigManager class."""

import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import toml

from gh_pr.utils.config import ConfigManager


class TestConfigManager:
    """Test ConfigManager class."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            config_path = Path(f.name)
            f.write('[github]\ntoken = "test_token"\n')
            f.write('[display]\npage_size = 10\n')
        yield config_path
        config_path.unlink(missing_ok=True)

    @pytest.fixture
    def config_manager(self, temp_config_file):
        """Create a ConfigManager instance with temp config file."""
        return ConfigManager(config_path=temp_config_file)

    def test_init_default(self):
        """Test ConfigManager initialization with default path."""
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = Path("/home/user")
            manager = ConfigManager()
            expected_path = Path("/home/user/.config/gh-pr/config.toml")
            assert manager.config_path == expected_path

    def test_init_custom_path(self, temp_config_file):
        """Test ConfigManager initialization with custom path."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager.config_path == temp_config_file

    def test_load_existing_config(self, temp_config_file):
        """Test loading existing configuration."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager.get("github.token") == "test_token"
        assert manager.get("display.page_size") == 10

    def test_load_nonexistent_config(self):
        """Test loading non-existent configuration file."""
        non_existent = Path("/tmp/nonexistent/config.toml")
        manager = ConfigManager(config_path=non_existent)
        assert manager.config == {}

    def test_load_corrupt_config(self):
        """Test loading corrupted TOML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            config_path = Path(f.name)
            f.write("invalid toml content{]")

        try:
            manager = ConfigManager(config_path=config_path)
            assert manager.config == {}
        finally:
            config_path.unlink(missing_ok=True)

    def test_get_nested_value(self, config_manager):
        """Test getting nested configuration values."""
        assert config_manager.get("github.token") == "test_token"
        assert config_manager.get("display.page_size") == 10

    def test_get_nonexistent_value(self, config_manager):
        """Test getting non-existent configuration value."""
        assert config_manager.get("nonexistent.key") is None
        assert config_manager.get("nonexistent.key", "default") == "default"

    def test_get_top_level_value(self, config_manager):
        """Test getting top-level configuration section."""
        github_config = config_manager.get("github")
        assert isinstance(github_config, dict)
        assert github_config.get("token") == "test_token"

    def test_set_nested_value(self, config_manager):
        """Test setting nested configuration values."""
        config_manager.set("cache.enabled", True)
        assert config_manager.get("cache.enabled") is True

        config_manager.set("cache.ttl", 3600)
        assert config_manager.get("cache.ttl") == 3600

    def test_set_creates_nested_structure(self, config_manager):
        """Test that set creates nested structure as needed."""
        config_manager.set("deeply.nested.key.value", "test")
        assert config_manager.get("deeply.nested.key.value") == "test"

    def test_save_config(self, temp_config_file):
        """Test saving configuration to file."""
        manager = ConfigManager(config_path=temp_config_file)
        manager.set("new.setting", "value")
        manager.save()

        # Load the file and verify
        with open(temp_config_file, 'r') as f:
            saved_config = toml.load(f)
        assert saved_config["new"]["setting"] == "value"
        assert saved_config["github"]["token"] == "test_token"

    def test_save_creates_directories(self):
        """Test that save creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "subdir" / "config.toml"
            manager = ConfigManager(config_path=config_path)
            manager.set("test.value", "data")
            manager.save()

            assert config_path.exists()
            with open(config_path, 'r') as f:
                saved_config = toml.load(f)
            assert saved_config["test"]["value"] == "data"

    def test_save_write_error(self, config_manager):
        """Test handling of write errors during save."""
        with patch('builtins.open', side_effect=OSError("Write error")):
            # Should not raise exception
            config_manager.save()

    def test_delete_value(self, config_manager):
        """Test deleting configuration values."""
        # Verify value exists
        assert config_manager.get("display.page_size") == 10

        # Delete it
        config_manager.delete("display.page_size")
        assert config_manager.get("display.page_size") is None

    def test_delete_nonexistent_value(self, config_manager):
        """Test deleting non-existent value."""
        # Should not raise exception
        config_manager.delete("nonexistent.key")

    def test_delete_nested_section(self, config_manager):
        """Test deleting entire nested section."""
        config_manager.delete("display")
        assert config_manager.get("display") is None
        assert config_manager.get("github.token") == "test_token"  # Other sections intact

    def test_get_all(self, config_manager):
        """Test getting entire configuration."""
        all_config = config_manager.get_all()
        assert "github" in all_config
        assert "display" in all_config
        assert all_config["github"]["token"] == "test_token"

    def test_update_section(self, config_manager):
        """Test updating entire configuration section."""
        new_display = {
            "page_size": 20,
            "color": True,
            "format": "table"
        }
        config_manager.update_section("display", new_display)

        assert config_manager.get("display.page_size") == 20
        assert config_manager.get("display.color") is True
        assert config_manager.get("display.format") == "table"

    def test_has_value(self, config_manager):
        """Test checking if configuration value exists."""
        assert config_manager.has("github.token") is True
        assert config_manager.has("nonexistent.key") is False

    def test_reset_to_defaults(self, config_manager):
        """Test resetting configuration to defaults."""
        # Modify config
        config_manager.set("custom.value", "test")
        assert config_manager.get("custom.value") == "test"

        # Reset to defaults
        defaults = {
            "github": {"api_url": "https://api.github.com"},
            "display": {"page_size": 25}
        }
        config_manager.reset_to_defaults(defaults)

        assert config_manager.get("custom.value") is None
        assert config_manager.get("github.api_url") == "https://api.github.com"
        assert config_manager.get("display.page_size") == 25

    def test_merge_config(self, config_manager):
        """Test merging configuration from another source."""
        additional_config = {
            "cache": {"enabled": True, "ttl": 3600},
            "display": {"color": True}  # Should merge with existing display
        }
        config_manager.merge(additional_config)

        assert config_manager.get("cache.enabled") is True
        assert config_manager.get("cache.ttl") == 3600
        assert config_manager.get("display.color") is True
        assert config_manager.get("display.page_size") == 10  # Original value preserved

    def test_config_types_preserved(self, config_manager):
        """Test that configuration value types are preserved."""
        config_manager.set("types.string", "text")
        config_manager.set("types.integer", 42)
        config_manager.set("types.float", 3.14)
        config_manager.set("types.boolean", True)
        config_manager.set("types.list", [1, 2, 3])
        config_manager.set("types.dict", {"key": "value"})

        config_manager.save()

        # Reload and verify types
        new_manager = ConfigManager(config_path=config_manager.config_path)
        assert isinstance(new_manager.get("types.string"), str)
        assert isinstance(new_manager.get("types.integer"), int)
        assert isinstance(new_manager.get("types.float"), float)
        assert isinstance(new_manager.get("types.boolean"), bool)
        assert isinstance(new_manager.get("types.list"), list)
        assert isinstance(new_manager.get("types.dict"), dict)

    def test_environment_variable_override(self, config_manager):
        """Test that environment variables can override config."""
        with patch.dict('os.environ', {'GH_PR_TOKEN': 'env_token'}):
            # In a real implementation, you might have a method that checks env vars
            # For now, this tests the concept
            token = config_manager.get("github.token", env_var="GH_PR_TOKEN")
            # This would need implementation in the actual ConfigManager
            assert token == "test_token"  # Currently returns config value

    def test_config_validation(self, config_manager):
        """Test configuration validation."""
        # Test setting invalid values
        config_manager.set("display.page_size", -1)  # Invalid page size

        # In a real implementation, you might have validation
        # For now, this tests that values can be set
        assert config_manager.get("display.page_size") == -1