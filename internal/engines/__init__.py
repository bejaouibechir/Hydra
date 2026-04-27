"""
Sous-package internal.engines.

Expose un registry minimal pour récupérer/instancier des engines.
"""

from internal.engines.registry import EngineRegistry, registry

__all__ = ["EngineRegistry", "registry"]
