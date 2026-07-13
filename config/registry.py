"""
Crypto Bot v4.4 — Config Registry
Immutable, versioned configuration management.
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import structlog
import yaml

from core.models import (
    ExecutionConfig, LearningConfig, MonitoringConfig,
    RegimeConfig, RiskConfig, StrategyConfig, StrategyType, SystemConfig,
)

logger = structlog.get_logger(__name__)

DEFAULT_CONFIG_DIR = Path(__file__).parent


class ConfigRegistry:
    """
    Immutable configuration registry.
    Each configuration has a unique version and hash.
    Configurations are NOT mutable during runtime.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self._current_version: Optional[str] = None
        self._current_config: Optional[SystemConfig] = None
        self._version_history: List[dict] = []

    def load(self, config_path: Optional[str] = None) -> SystemConfig:
        """
        Load configuration from a YAML file.
        If no path specified, loads the latest versioned config.
        """
        if config_path:
            path = Path(config_path)
        else:
            # Find latest config file
            config_files = sorted(self.config_dir.glob("config_v*.yaml"))
            if not config_files:
                raise FileNotFoundError(f"No config files found in {self.config_dir}")
            path = config_files[-1]

        with open(path) as f:
            raw = yaml.safe_load(f)

        config = self._parse_config(raw)
        self._current_config = config
        self._current_version = raw.get("config_version", raw.get("system_version", "unknown"))

        # Compute hash
        config_hash = self._compute_hash(raw)
        raw["hash"] = config_hash
        config.hash = config_hash

        # Record in history
        self._version_history.append({
            "version": self._current_version,
            "hash": config_hash,
            "loaded_at": datetime.utcnow().isoformat(),
            "path": str(path),
        })

        logger.info("config_loaded", version=self._current_version, hash=config_hash)
        return config

    def _parse_config(self, raw: dict) -> SystemConfig:
        """Parse raw YAML dict into SystemConfig dataclass."""
        config = SystemConfig()

        config.version = raw.get("config_version", raw.get("system_version", "4.4.0"))
        config.created_at = raw.get("created_at", datetime.utcnow())

        # Data
        config.pairs = raw.get("data", {}).get("pairs", config.pairs)
        config.timeframes = raw.get("data", {}).get("timeframes", config.timeframes)
        config.lookback_days = raw.get("data", {}).get("lookback_days", config.lookback_days)

        # Strategy configs
        if "strategy" in raw:
            s = raw["strategy"]
            config.strategy = {}
            for st_name, st_key in [("sweep", StrategyType.SWEEP), ("bounce", StrategyType.BOUNCE), ("breakout", StrategyType.BREAKOUT)]:
                if st_name in s:
                    cfg = s[st_name]
                    config.strategy[st_key] = StrategyConfig(
                        enabled=cfg.get("enabled", True),
                        wick_ratio=cfg.get("wick_ratio", 1.8),
                        volume_multiplier=cfg.get("volume_multiplier", 1.25),
                        tolerance=cfg.get("tolerance", 0.0018),
                        min_rr=cfg.get("min_rr", 2.0),
                        sl_atr_mult=cfg.get("sl_atr_mult", 1.5),
                        tp_min=cfg.get("tp_min", 0.02),
                        tp_max=cfg.get("tp_max", 0.04),
                    )

        # Risk config
        if "risk" in raw:
            r = raw["risk"]
            config.risk = RiskConfig(
                max_risk_per_trade=r.get("max_risk_per_trade", 0.015),
                max_positions=r.get("max_positions", 3),
                max_correlation=r.get("max_correlation", 0.7),
                max_exposure=r.get("max_exposure", 3.0),
                stop_multipliers=r.get("stop_multiplier", config.risk.stop_multipliers),
                drawdown_limits=r.get("drawdown_limits", config.risk.drawdown_limits),
                recovery_threshold=r.get("recovery", {}).get("threshold", 8.0),
                recovery_exit_threshold=r.get("recovery", {}).get("exit_threshold", 5.0),
                recovery_min_wins=r.get("recovery", {}).get("min_wins", 3),
            )

        # Regime config
        if "regime" in raw:
            config.regime = RegimeConfig(
                adx_threshold=raw["regime"].get("adx_threshold", 25.0),
                atr_percentiles=raw["regime"].get("atr_percentiles", [20.0, 80.0]),
            )

        # Execution config
        if "execution" in raw:
            e = raw["execution"]
            config.execution = ExecutionConfig(
                max_slippage=e.get("max_slippage", 0.0005),
                limit_timeout=e.get("limit_timeout", 60),
                max_price_move=e.get("max_price_move", 0.002),
                partial_fill_action=e.get("partial_fill_action", "adjust"),
            )

        # Learning config
        if "learning" in raw:
            l = raw["learning"]
            config.learning = LearningConfig(
                min_trades=l.get("min_trades", 100),
                min_windows=l.get("min_windows", 3),
                train_period=l.get("train_period", 6),
                test_period=l.get("test_period", 1),
                step=l.get("step", 1),
                score_weights=l.get("score_weights", config.learning.score_weights),
            )

        # Monitoring config
        if "monitoring" in raw:
            m = raw["monitoring"]
            config.monitoring = MonitoringConfig(
                data_latency_threshold=m.get("data_latency_threshold", 500),
                api_errors_threshold=m.get("api_errors_threshold", 5),
                cpu_threshold=m.get("cpu_threshold", 80.0),
                memory_threshold=m.get("memory_threshold", 2048),
            )

        return config

    def save_version(self, config: SystemConfig, path: Optional[str] = None) -> str:
        """Save a new versioned config to YAML."""
        if path is None:
            version = config.version
            path = str(self.config_dir / f"config_v{version}.yaml")

        raw = self._config_to_dict(config)
        with open(path, "w") as f:
            yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

        logger.info("config_saved", path=path)
        return path

    def _config_to_dict(self, config: SystemConfig) -> dict:
        """Serialize SystemConfig to a YAML-friendly dict."""
        return {
            "system_version": config.version,
            "created_at": config.created_at.isoformat() if isinstance(config.created_at, datetime) else str(config.created_at),
            "hash": config.hash,
            "data": {
                "pairs": config.pairs,
                "timeframes": config.timeframes,
                "lookback_days": config.lookback_days,
            },
            "strategy": {
                st.value: {
                    "enabled": c.enabled,
                    "wick_ratio": c.wick_ratio,
                    "volume_multiplier": c.volume_multiplier,
                    "tolerance": c.tolerance,
                    "min_rr": c.min_rr,
                    "sl_atr_mult": c.sl_atr_mult,
                    "tp_min": c.tp_min,
                    "tp_max": c.tp_max,
                }
                for st, c in config.strategy.items()
            } if config.strategy else {},
            "risk": {
                "max_risk_per_trade": config.risk.max_risk_per_trade,
                "max_positions": config.risk.max_positions,
                "max_correlation": config.risk.max_correlation,
                "max_exposure": config.risk.max_exposure,
                "stop_multiplier": config.risk.stop_multipliers,
                "drawdown_limits": config.risk.drawdown_limits,
                "recovery": {
                    "threshold": config.risk.recovery_threshold,
                    "exit_threshold": config.risk.recovery_exit_threshold,
                    "min_wins": config.risk.recovery_min_wins,
                },
            },
            "execution": {
                "max_slippage": config.execution.max_slippage,
                "limit_timeout": config.execution.limit_timeout,
                "max_price_move": config.execution.max_price_move,
                "partial_fill_action": config.execution.partial_fill_action,
            },
            "learning": {
                "min_trades": config.learning.min_trades,
                "min_windows": config.learning.min_windows,
                "train_period": config.learning.train_period,
                "test_period": config.learning.test_period,
                "step": config.learning.step,
                "score_weights": config.learning.score_weights,
            },
            "monitoring": {
                "data_latency_threshold": config.monitoring.data_latency_threshold,
                "api_errors_threshold": config.monitoring.api_errors_threshold,
                "cpu_threshold": config.monitoring.cpu_threshold,
                "memory_threshold": config.monitoring.memory_threshold,
            },
        }

    @staticmethod
    def _compute_hash(data: dict) -> str:
        """Compute SHA-256 hash of config data for integrity."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:12]

    @property
    def current_config(self) -> Optional[SystemConfig]:
        return self._current_config

    @property
    def current_version(self) -> Optional[str]:
        return self._current_version

    def get_version_history(self) -> List[dict]:
        return list(self._version_history)
