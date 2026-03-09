# maestro/plugins/__init__.py

from .base import (
    MaestroPlugin,
    PluginManifest,
    PluginContext,
    PluginState,
    PluginCategory,
)
from .manager import ModManager, WeightStateSnapshot
