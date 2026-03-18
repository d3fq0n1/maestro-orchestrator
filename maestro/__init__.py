# maestro/__init__.py

# This file marks the directory as a Python package.

__version__ = "7.4.0"

from maestro.plugins.manager import ModManager

__all__ = ["ModManager", "__version__"]
