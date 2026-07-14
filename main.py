"""
Crypto Bot v4.4 — Main Orchestrator
Coordinates all services in the trading pipeline.

Step decomposition (post-review refactor):
  _fetch_and_validate → _compute_features → _generate_signals
  → _evaluate_and_execute → _health_check
"""

import asyncio
import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import structlog

from config.registry import ConfigRegistry
from core.database.db_manager import DatabaseManager
from core.events.event_store import EventStore
from core.exchange.adapter import create_exchange
from core.models import (
    Features, HealthStatus, OHLCV, Regime, ServiceMode, Signal,
)
from services.analytics_service.service import AnalyticsService
from services.data_service.service import DataService
from services.data_service.websocket import WebSocketManager
from services.data_validator.validator import DataValidator
from services.execution_engine.engine import ExecutionEngine
from services.feature_service.calculator import FeatureCalculator
from services.health_monitor.monitor import HealthMonitor
from services.learning_service.service import LearningService
from services.portfolio_engine.engine import PortfolioEngine
from services.regime_detector.detector import RegimeDetector
from services.risk_engine.engine import RiskEngine
from services.strategy_engine.engine import StrategyEngine

logger = structlog.get_logger(__name__)


class CryptoBot:
    """
    Main orchestrator for Crypto Bot v4.4.
    Coordinates all services in the trading pipeline:

    Data → Validator → Features → Regime → Strategy → Risk → Execution → Portfolio
                                                                  ↓
                                                            Analytics
    """

    def __init__(self, config_path: Optional[str] = None):
        # --- Config ---
        self.config_registry = ConfigRegistry()
        self.config = self.config_registry.load(config_path)

        # --- Core infrastructure ---
        self.event_store = EventStore()
        self.db_manager = DatabaseManager()
        self.health_monitor = HealthMonitor()

        # --- Exchange Adapter (CCXT) ---
        exchange_id = os.getenv("EXCHANGE_ID", "binance")
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        self.exchange_adapter = create_exchange(
            exchange_id=exchange_id, api_key=api_key,
            api_secret=api_secret, testnet=testnet,
        )
        logger.info("exchange_configured", exchange=exchange_id, testnet=testnet)

        # --- Services ---
        self.data_service = DataService(
            db_manager=self.db_manager, pairs=self.config.pairs,
            timeframes=self.config.timeframes, exchange_adapter=self.exchange_adapter,
        )
        self.ws_manager = WebSocketManager(
            exchange_id=exchange_id, api_key=api_key,
            api_secret=api_secret, testnet=testnet,
        )
        self.data_validator = DataValidator()
        self.feature_calculator = FeatureCalculator(
            pairs=self.config.pairs, timeframes=self.config.timeframes,
        )
        self.regime_detector = RegimeDetector(
            adx_threshold=self.config.regime.adx_threshold,
            atr_percentiles=tuple(self.config.regime.atr_percentiles),
        )
        self.strategy_engine = StrategyEngine()
        self.risk_engine = RiskEngine(balance=10000.0, event_store=self.event_store)
        self.execution_engine = ExecutionEngine(exchange_adapter=self.exchange_adapter)
        self.portfolio_engine = PortfolioEngine(event_store=self.event_store)
        self.analytics_service = AnalyticsService()
        self.learning_service = LearningService(config=self.config.learning)

        # --- State ---
        self._mode = ServiceMode.ONLINE
        self._running = False

    # ═══════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self):
        """Initialize database, warm up data, start WebSocket streams."""
        logger.info("bot_initializing", version=self.config.version)
        self.db_manager.connect()
        self.db_manager.create_all()

        # Fetch account balance
        try:
            balances = await self.execution_engine.fetch_account_balance()
            usdt = balances.get("USDT", {})
            balance = usdt.get("total", 10000.0)
            if balance > 0:
                self.risk_engine.update_balance(balance)
                logger.info("account_balance_loaded", balance=balance)
        except Exception as e:
            logger.warning("balance_fetch_skipped", error=str(e))

        # Historical data warmup
        await self.data_service.warmup_data()

        # Start WebSocket streams (non-blocking, background tasks)
        ws_enabled = os.getenv("ENABLE_WEBSOCKET", "true").lower() == "true"
        if ws_enabled:
            await self.ws_manager.start(
                pairs=self.config.pairs, timeframes=self.config.timeframes,
            )
            logger.info("websocket_streams_initialized")

        logger.info("bot_initialized")

    async def shutdown(self):
        await self.ws_manager.stop()
        await self.data_service.close()
        self.db_manager.close()
        logger.info("bot_shutdown")

    # ═══════════════════════════════════════════════════════════
    # Pipeline Steps (post-review decomposition)
    # ═══════════════════════════════════════════════════════════

    async def _step_fetch_and_validate(
        self,
    ) -> Optional[Dict[str, Dict[str, List[OHLCV]]]]:
        """Step 1+2: fetch latest candles and validate data quality."""
        candles_by_pair: Dict[str, Dict[str, List[OHLCV]]] = {}
        for pair in self.config.pairs:
            candles_by_pair[pair] = {}
            for tf in self.config.timeframes:
                candles = await self.data_service.get_latest_candles(pair, tf, n=100)
                candles_by_pair[pair][tf] = candles

        # Merge WebSocket-delivered latest candle if available
        for pair in self.config.pairs:
            for tf in self.config.timeframes:
                ws_candle = self.ws_manager.get_latest_ohlcv(pair, tf)
                if ws_candle and candles_by_pair[pair][tf]:
                    last_rest = candles_by_pair[pair][tf][-1]
                    if ws_candle.timestamp > last_rest.timestamp:
                        candles_by_pair[pair][tf].append(ws_candle)

        all_candles = []
        for pair_candles in candles_by_pair.values():
            for tf_candles in pair_candles.values():
                all_candles.extend(tf_candles)

        is_healthy, critical, non_critical = self.data_validator.validate_candles(
            all_candles, "1h"
        )
        if not is_healthy:
            logger.error("data_validation_failed_stopping")
            return None

        return candles_by_pair

    async def _step_compute_features(
        self, candles_by_pair: Dict[str, Dict[str, List[OHLCV]]],
    ) -> Dict[str, Features]:
        """Step 3: compute features for all pairs/timeframes."""
        return self.feature_calculator.compute_for_all(candles_by_pair)

    async def _step_generate_signals(
        self,
        candles_by_pair: Dict[str, Dict[str, List[OHLCV]]],
        features_by_pair_tf: Dict[str, Features],
    ) -> Tuple[List[Signal], Dict[str, float]]:
        """Step 4: detect regimes and generate signals."""
        all_signals: List[Signal] = []
        current_prices: Dict[str, float] = {}

        # Prefer WebSocket prices for live data
        ws_prices = self.ws_manager.get_current_prices()

        for pair in self.config.pairs:
            pair_features = None
            for tf in ["1h", "4h", "15m"]:
                key = f"{pair}:{tf}"
                if key in features_by_pair_tf:
                    pair_features = features_by_pair_tf[key]
                    break
            if pair_features is None:
                continue

            regime = self.regime_detector.detect(pair_features)

            # Current price: WebSocket → REST 15m → REST 1h fallback
            current_price = ws_prices.get(pair, 0.0)
            if current_price <= 0:
                candles_15m = candles_by_pair[pair].get("15m", [])
                current_price = candles_15m[-1].close if candles_15m and candles_15m[-1].close > 0 else 0.0
            if current_price <= 0:
                candles_1h_pos = candles_by_pair[pair].get("1h", [])
                current_price = candles_1h_pos[-1].close if candles_1h_pos and candles_1h_pos[-1].close > 0 else 0.0
            current_prices[pair] = current_price
            if current_price <= 0:
                continue

            for tf in self.config.timeframes:
                key = f"{pair}:{tf}"
                if key not in features_by_pair_tf:
                    continue
                tf_candles = candles_by_pair[pair].get(tf, [])
                if not tf_candles:
                    continue
                tf_signals = self.strategy_engine.generate_signals(
                    features_by_pair_tf[key], regime, tf_candles, pair
                )
                all_signals.extend(tf_signals)

        return all_signals, current_prices

    async def _step_evaluate_and_execute(
        self, signals: List[Signal], current_prices: Dict[str, float],
    ):
        """Step 5+6: evaluate signals through risk engine and execute."""
        portfolio_state = self.risk_engine.get_portfolio_state()
        approved: List[tuple] = []
        pending = 0
        max_pos = self.config.risk.max_positions

        for signal in sorted(signals, key=lambda s: s.confidence, reverse=True):
            if signal.regime in ("trend_high_vol", "range_high_vol", "breakout"):
                vol_regime = "volatile"
            elif signal.regime in ("trend_low_vol", "range_low_vol"):
                vol_regime = "quiet"
            else:
                vol_regime = "normal"

            temp_state = (
                replace(portfolio_state, open_positions=portfolio_state.open_positions + pending)
                if pending > 0 else portfolio_state
            )

            decision = self.risk_engine.evaluate_signal(
                signal, temp_state, current_volatility=vol_regime
            )
            if decision.approved:
                approved.append((signal, decision))
                pending += 1
            if portfolio_state.open_positions + pending >= max_pos:
                break

        for signal, risk_decision in approved:
            exec_record = await self.execution_engine.place_entry_limit(
                signal, risk_decision
            )
            if exec_record and not exec_record.cancelled:
                self.portfolio_engine.open_position(
                    pair=signal.pair,
                    direction=signal.direction,
                    entry_price=exec_record.actual_price,
                    size=risk_decision.position_size,
                    stop_loss=risk_decision.stop_loss,
                    tp1=signal.tp1,
                    tp2=signal.tp2,
                    strategy=signal.strategy.value,
                )
                pos = self.portfolio_engine.get_position(signal.pair)
                if pos:
                    await self.execution_engine.place_stop_loss(pos)
                    await self.execution_engine.place_take_profit_limit(
                        pos, signal.tp1, risk_decision.position_size / 2,
                    )
                    await self.execution_engine.place_take_profit_limit(
                        pos, signal.tp2, risk_decision.position_size / 2,
                    )
                logger.info("trade_opened", pair=signal.pair,
                           direction=signal.direction.value,
                           confidence=signal.confidence, rr=risk_decision.rr_ratio)

        self.portfolio_engine.update_pnl(current_prices)

    async def _step_health_check(self) -> bool:
        """Step 8: health check. Returns False if trading should stop."""
        health = self.health_monitor.check()
        if health.status == HealthStatus.CRITICAL:
            logger.critical("health_critical_stopping")
            return False
        return True

    # ═══════════════════════════════════════════════════════════
    # Main Loop
    # ═══════════════════════════════════════════════════════════

    async def run_once(self):
        """Run one full cycle of the trading pipeline (decomposed steps)."""
        cycle_start = time.perf_counter()

        try:
            candles = await self._step_fetch_and_validate()
            if candles is None:
                return

            features = await self._step_compute_features(candles)

            self.health_monitor.record_data_latency(
                (time.perf_counter() - cycle_start) * 1000
            )
            self.health_monitor.record_feature_calc_time(
                (time.perf_counter() - cycle_start) * 1000
            )

            signals, current_prices = await self._step_generate_signals(candles, features)

            await self._step_evaluate_and_execute(signals, current_prices)

            if not await self._step_health_check():
                self._running = False

        except Exception as e:
            logger.error("cycle_error", error=str(e))
            self.health_monitor.record_api_call(success=False)

        cycle_time = (time.perf_counter() - cycle_start) * 1000
        logger.debug("cycle_complete", time_ms=round(cycle_time, 2))

    async def run(self, interval_sec: float = 15.0):
        await self.initialize()
        self._running = True
        logger.info("bot_running", mode=self._mode.value, interval=interval_sec)
        while self._running:
            await self.run_once()
            await asyncio.sleep(interval_sec)

    def get_status_report(self) -> dict:
        portfolio = self.risk_engine.get_portfolio_state()
        health = self.health_monitor.get_status()
        execution_quality = self.execution_engine.get_execution_quality()
        analytics = self.analytics_service.get_metrics()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": self.config.version,
            "mode": self._mode.value,
            "websocket": self.ws_manager.is_connected,
            "portfolio": {
                "balance": portfolio.balance,
                "equity": portfolio.equity,
                "open_positions": portfolio.open_positions,
                "daily_pnl": portfolio.daily_pnl,
                "total_drawdown": portfolio.total_drawdown,
                "recovery_mode": portfolio.recovery_mode,
            },
            "health": health,
            "execution": execution_quality,
            "analytics": analytics,
        }


async def main():
    bot = CryptoBot()
    try:
        await bot.run(interval_sec=15.0)
    except KeyboardInterrupt:
        await bot.shutdown()
    except Exception as e:
        logger.critical("fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
