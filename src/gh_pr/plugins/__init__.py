"""
Plugin system for extending gh-pr functionality.

Provides a flexible plugin architecture for adding custom
features and integrations.
"""

from .manager import PluginManager
from .base import Plugin, PluginMetadata, PluginContext
from .loader import PluginLoader

__all__ = [
    'PluginManager',
    'Plugin',
    'PluginMetadata',
    'PluginContext',
    'PluginLoader',
]