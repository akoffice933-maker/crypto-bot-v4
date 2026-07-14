"""
Auto-discovery plugin loader for strategies.

Scans plugins/ directory and registers all BaseStrategy subclasses.
"""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, List, Type

import structlog

from services.strategy_engine.plugins.base import BaseStrategy

logger = structlog.get_logger(__name__)

_STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def discover_plugins(package_path: str = "services.strategy_engine.plugins") -> Dict[str, Type[BaseStrategy]]:
    """
    Auto-discover all BaseStrategy subclasses in the plugins package.

    Returns:
        Dict mapping strategy name → strategy class.

    Usage:
        registry = discover_plugins()
        strategy = registry["sweep"](wick_ratio=2.0)  # instantiate with overrides
    """
    global _STRATEGY_REGISTRY
    if _STRATEGY_REGISTRY:
        return _STRATEGY_REGISTRY

    try:
        package = importlib.import_module(package_path)
    except ImportError:
        logger.warning("plugin_package_not_found", path=package_path)
        return {}

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_") or module_name in ("base", "loader"):
            continue
        try:
            full_name = f"{package_path}.{module_name}"
            module = importlib.import_module(full_name)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseStrategy)
                    and obj is not BaseStrategy
                    and obj.name
                ):
                    _STRATEGY_REGISTRY[obj.name] = obj
                    logger.info("plugin_registered", name=obj.name, module=full_name)

        except Exception as e:
            logger.warning("plugin_load_failed", module=module_name, error=str(e))

    return _STRATEGY_REGISTRY


def list_plugins() -> List[dict]:
    """List all registered plugins with metadata."""
    registry = discover_plugins()
    return [
        {
            "name": name,
            "strategy_type": cls.strategy_type.value,
            "config": {
                k: v for k, v in cls.config.__dict__.items()
                if not k.startswith("_")
            },
        }
        for name, cls in registry.items()
    ]


def get_plugin(name: str) -> Type[BaseStrategy]:
    """Get a plugin class by name."""
    registry = discover_plugins()
    if name not in registry:
        raise KeyError(f"Strategy plugin '{name}' not found. Available: {list(registry.keys())}")
    return registry[name]
