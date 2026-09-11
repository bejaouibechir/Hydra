"""
Sous-package internal.engines.

Expose un registry minimal pour récupérer/instancier des engines.
"""

from hydra_etl.internal.engines.registry import EngineRegistry, registry

__all__ = ["EngineRegistry", "registry"]
