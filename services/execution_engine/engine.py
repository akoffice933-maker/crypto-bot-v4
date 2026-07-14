"""
Crypto Bot v4.5 — Execution Engine (refactored)

Modular order execution via CCXT.
Components:
  - orders/limit.py     LimitOrderExecutor
  - orders/market.py    MarketOrderExecutor (emergency fallback)
  - orders/stop.py      StopOrderExecutor (SL + TP)
  - reconcile.py        PositionReconciler
  - retry.py            CircuitBreaker + RetryPolicy
  - quality/monitor.py  QualityMonitor

Orchestrates limit entry → market fallback → SL/TP placement.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog

from core.exchange.adapter import ExchangeAdapter, create_exchange
from core.models import Direction, ExecutionRecord, Position, RiskDecision, Signal
from services.execution_engine.orders.limit import LimitOrderExecutor
from services.execution_engine.orders.market import MarketOrderExecutor
from services.execution_engine.orders.stop import StopOrderExecutor
from services.execution_engine.reconcile import PositionReconciler
from services.execution_engine.retry import CircuitBreaker
from services.execution_engine.quality.monitor import QualityMonitor

logger = structlog.get_logger(__name__)


class ExecutionEngine:
    """
    Entry point for all order execution.

    Delegates to:
      - LimitOrderExecutor (primary)
      - MarketOrderExecutor (fallback)
      - StopOrderExecutor (SL/TP)
      - PositionReconciler (post-interruption check)
    Tracks quality via QualityMonitor.
    """

    def __init__(
        self,
        exchange_adapter: Optional[ExchangeAdapter] = None,
        exchange_id: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
    ):
        if exchange_adapter:
            self.exchange = exchange_adapter
        else:
            self.exchange = create_exchange(
                exchange_id=exchange_id, api_key=api_key,
                api_secret=api_secret, testnet=testnet,
            )

        self._circuit_breaker = CircuitBreaker()
        self._limit = LimitOrderExecutor(self.exchange)
        self._market = MarketOrderExecutor(self.exchange)
        self._stop = StopOrderExecutor(self.exchange)
        self._reconciler = PositionReconciler(self.exchange)
        self._quality = QualityMonitor()
        self._mock_mode = False

    def _ensure_connected(self):
        if not self.exchange.is_connected:
            try:
                self.exchange.connect()
                self._mock_mode = False
            except Exception as e:
                logger.warning("exchange_unavailable_mock", error=str(e))
                self._mock_mode = True

    # ── Entry ──────────────────────────────────────────────────

    async def place_entry_limit(
        self, signal: Signal, risk_decision: RiskDecision
    ) -> Optional[ExecutionRecord]:
        self._ensure_connected()
        if not self._circuit_breaker.can_proceed:
            logger.error("cb_blocking_execution")
            return None

        side = "buy" if signal.direction == Direction.LONG else "sell"
        ccxt_symbol = ExchangeAdapter.normalize_symbol(signal.pair, self.exchange.exchange_id)

        if self._mock_mode:
            await asyncio.sleep(0.01)
            record = ExecutionRecord(
                timestamp=datetime.now(timezone.utc),
                pair=signal.pair, expected_price=signal.entry_limit,
                actual_price=signal.entry_market,
                slippage=abs(signal.entry_market - signal.entry_limit),
                latency=10.0,
            )
            self._quality.record(record)
            return record

        record = await self._limit.place(signal, risk_decision, ccxt_symbol, side)
        if record is not None:
            self._quality.record(record)
            return record

        # Limit failed → emergency market
        record = await self._market.place(signal, risk_decision, ccxt_symbol, side)
        if record:
            self._quality.record(record)
        return record

    # ── Stop-loss / Take-profit ─────────────────────────────────

    async def place_stop_loss(self, position: Position) -> bool:
        self._ensure_connected()
        if self._mock_mode:
            return True
        return self._stop.place_stop_loss(position)

    async def place_take_profit_limit(self, position: Position, tp_price: float, quantity: float, tp_index: int = 1) -> bool:
        self._ensure_connected()
        if self._mock_mode:
            return True
        if not self._mock_mode:
            return self._stop.place_take_profit(position, tp_price, quantity, tp_index=tp_index)
        return True

    # ── Reconciliation ─────────────────────────────────────────

    async def reconcile_position(self, pair: str) -> dict:
        self._ensure_connected()
        if self._mock_mode:
            return {"pair": pair, "found": False}
        return await self._reconciler.reconcile(pair)

    async def fetch_account_balance(self) -> dict:
        self._ensure_connected()
        if self._mock_mode:
            return {"USDT": {"total": 10000, "free": 10000, "used": 0}}
        try:
            balances = self.exchange.fetch_balance()
            return {c: {"total": b.total, "free": b.free, "used": b.used}
                    for c, b in balances.items() if b.total > 0}
        except Exception as e:
            logger.error("balance_fetch_failed", error=str(e))
            return {}

    # ── Quality ─────────────────────────────────────────────────

    def get_execution_quality(self) -> dict:
        return self._quality.summary()

    def close(self):
        self.exchange.close()
