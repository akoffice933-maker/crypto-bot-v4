"""
Crypto Bot v4.4 — Main Orchestrator
Coordinates all services in the trading pipeline.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog

from config.registry import ConfigRegistry
from core.database.db_manager import DatabaseManager
from core.events.event_store import EventStore
from core.exchange.adapter import create_exchange
from core.models import (
    HealthStatus, OHLCV, ServiceMode, Signal,
)
from services.analytics_service.service import AnalyticsService
from services.data_service.service import DataService
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
            exchange_id=exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )
        logger.info("exchange_configured", exchange=exchange_id, testnet=testnet)

        # --- Initialize services ---
        self.data_service = DataService(
            db_manager=self.db_manager,
            pairs=self.config.pairs,
            timeframes=self.config.timeframes,
            exchange_adapter=self.exchange_adapter,
        )
        self.data_validator = DataValidator()
        self.feature_calculator = FeatureCalculator(
            pairs=self.config.pairs,
            timeframes=self.config.timeframes,
        )
        self.regime_detector = RegimeDetector(
            adx_threshold=self.config.regime.adx_threshold,
            atr_percentiles=tuple(self.config.regime.atr_percentiles),
        )
        self.strategy_engine = StrategyEngine()
        self.risk_engine = RiskEngine(
            balance=10000.0,  # Default; updated from exchange on connect
            event_store=self.event_store,
        )
        self.execution_engine = ExecutionEngine(
            exchange_adapter=self.exchange_adapter,
        )
        self.portfolio_engine = PortfolioEngine(event_store=self.event_store)
        self.analytics_service = AnalyticsService()
        self.learning_service = LearningService(config=self.config.learning)

        # --- State ---
        self._mode = ServiceMode.ONLINE
        self._running = False

    async def initialize(self):
        """Initialize database and warm up data."""
        logger.info("bot_initializing", version=self.config.version)
        self.db_manager.connect()
        self.db_manager.create_all()

        # Fetch account balance from exchange to seed risk engine
        try:
            balances = await self.execution_engine.fetch_account_balance()
            usdt = balances.get("USDT", {})
            balance = usdt.get("total", 10000.0)
            if balance > 0:
                self.risk_engine.update_balance(balance)
                logger.info("account_balance_loaded", balance=balance)
        except Exception as e:
            logger.warning("balance_fetch_skipped", error=str(e))

        # Warm up: fetch minimum required historical data
        await self.data_service.warmup_data()
        logger.info("bot_initialized")

    async def run_once(self):
        """
        Run one full cycle of the trading pipeline.
        Designed to be called every N seconds (typically 15s).
        """
        cycle_start = time.perf_counter()

        try:
            # 1. Fetch latest candles
            candles_by_pair: Dict[str, Dict[str, List[OHLCV]]] = {}
            for pair in self.config.pairs:
                candles_by_pair[pair] = {}
                for tf in self.config.timeframes:
                    candles = await self.data_service.get_latest_candles(pair, tf, n=100)
                    candles_by_pair[pair][tf] = candles

            # 2. Validate data
            all_candles = []
            for pair_candles in candles_by_pair.values():
                for tf_candles in pair_candles.values():
                    all_candles.extend(tf_candles)

            is_healthy, critical, non_critical = self.data_validator.validate_candles(
                all_candles, "1h"
            )
            self.health_monitor.record_data_latency((time.perf_counter() - cycle_start) * 1000)

            if not is_healthy:
                logger.error("data_validation_failed_stopping")
                return

            # 3. Compute features
            features_by_pair_tf = self.feature_calculator.compute_for_all(candles_by_pair)
            self.health_monitor.record_feature_calc_time(
                (time.perf_counter() - cycle_start) * 1000
            )

            # 4. Detect regime & generate signals
            all_signals: List[Signal] = []
            current_prices: Dict[str, float] = {}

            for pair in self.config.pairs:
                # Use 1h features for regime detection (priority order fallback)
                pair_features = None
                for tf in ["1h", "4h", "15m"]:
                    key = f"{pair}:{tf}"
                    if key in features_by_pair_tf:
                        pair_features = features_by_pair_tf[key]
                        break

                if pair_features is None:
                    continue

                regime = self.regime_detector.detect(pair_features)

                # Current price: prefer ticker, fallback to latest 15m close, fallback to 0
                candles_15m = candles_by_pair[pair].get("15m", [])
                current_price = candles_15m[-1].close if candles_15m and candles_15m[-1].close > 0 else 0
                if current_price <= 0:
                    candles_1h = candles_by_pair[pair].get("1h", [])
                    current_price = candles_1h[-1].close if candles_1h and candles_1h[-1].close > 0 else 0
                current_prices[pair] = current_price

                if current_price <= 0:
                    continue  # skip pair if no valid price data

                # Generate signals for each timeframe
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

            # 5. Evaluate signals through risk engine
            # Use a snapshot + pending counter to avoid mutating live state
            portfolio_state = self.risk_engine.get_portfolio_state()
            approved_signals: List[tuple] = []
            pending_count = 0

            sorted_signals = sorted(all_signals, key=lambda s: s.confidence, reverse=True)
            max_positions = self.config.risk.max_positions

            for signal in sorted_signals:
                # Determine volatility regime from signal regime
                if signal.regime in ("trend_high_vol", "range_high_vol", "breakout"):
                    vol_regime = "volatile"
                elif signal.regime in ("trend_low_vol", "range_low_vol"):
                    vol_regime = "quiet"
                else:
                    vol_regime = "normal"

                # Account for pending positions in this cycle
                temp_state = portfolio_state
                if pending_count > 0:
                    # Use a lightweight copy to simulate pending positions
                    from dataclasses import replace
                    temp_state = replace(portfolio_state, open_positions=portfolio_state.open_positions + pending_count)

                risk_decision = self.risk_engine.evaluate_signal(
                    signal, temp_state, current_volatility=vol_regime
                )

                if risk_decision.approved:
                    approved_signals.append((signal, risk_decision))
                    pending_count += 1

                if portfolio_state.open_positions + pending_count >= max_positions:
                    break

            # 6. Execute approved signals
            for signal, risk_decision in approved_signals:
                exec_start = time.perf_counter()
                exec_record = await self.execution_engine.place_entry_limit(
                    signal, risk_decision
                )
                exec_time = (time.perf_counter() - exec_start) * 1000
                self.health_monitor.record_order_placement(exec_time)

                if exec_record and not exec_record.cancelled:
                    # Open position in portfolio
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

                    # Place stop-loss and take-profits on exchange
                    pos = self.portfolio_engine.get_position(signal.pair)
                    if pos:
                        await self.execution_engine.place_stop_loss(pos)
                        await self.execution_engine.place_take_profit_limit(pos, signal.tp1, risk_decision.position_size / 2)
                        await self.execution_engine.place_take_profit_limit(pos, signal.tp2, risk_decision.position_size / 2)

                    logger.info("trade_opened",
                               pair=signal.pair, direction=signal.direction.value,
                               confidence=signal.confidence, rr=risk_decision.rr_ratio)

            # 7. Update portfolio PnL
            self.portfolio_engine.update_pnl(current_prices)

            # 8. Health check
            health = self.health_monitor.check()
            if health.status == HealthStatus.CRITICAL:
                logger.critical("health_critical_stopping")
                self._running = False

        except Exception as e:
            logger.error("cycle_error", error=str(e))
            self.health_monitor.record_api_call(success=False)

        cycle_time = (time.perf_counter() - cycle_start) * 1000
        logger.debug("cycle_complete", time_ms=round(cycle_time, 2))

    async def run(self, interval_sec: float = 15.0):
        """Main trading loop."""
        await self.initialize()
        self._running = True

        logger.info("bot_running", mode=self._mode.value, interval=interval_sec)

        while self._running:
            await self.run_once()
            await asyncio.sleep(interval_sec)

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("bot_shutting_down")
        self._running = False
        await self.data_service.close()
        self.db_manager.close()

    # ------- Analytics & Reporting -------
    def get_status_report(self) -> dict:
        """Generate a comprehensive status report."""
        portfolio = self.risk_engine.get_portfolio_state()
        health = self.health_monitor.get_status()
        execution_quality = self.execution_engine.get_execution_quality()
        analytics = self.analytics_service.get_metrics()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": self.config.version,
            "mode": self._mode.value,
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
    """Entry point."""
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
