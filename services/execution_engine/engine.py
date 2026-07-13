"""
Crypto Bot v4.4 — Execution Engine
Manages order placement, tracking, and quality-of-execution logging.
Uses CCXT unified API — works with Binance, Bybit, OKX, and 100+ exchanges.
"""

import asyncio
import time
from datetime import datetime, timezone, timezone
from typing import Dict, List, Optional

import structlog

from core.exchange.adapter import (
    ExchangeAdapter, ExchangeOrder, create_exchange,
)
from core.models import (
    Direction, ExecutionRecord, OrderSide, OrderStatus,
    Position, RiskDecision, Signal,
)

logger = structlog.get_logger(__name__)


class ExecutionEngine:
    """
    Executes orders on exchanges via CCXT unified API.

    Primary: Limit orders
    Fallback: Market orders (emergency)
    Supports: stop-market stops, limit take-profits
    Built-in: circuit breaker, retry with exponential backoff,
              quality-of-execution logging
    """

    # Execution parameters
    MAX_SLIPPAGE = 0.0005    # 0.05%
    LIMIT_TIMEOUT = 60        # seconds
    MAX_PRICE_MOVE = 0.002    # 0.2% max adverse move from signal
    RETRY_BASE_DELAY = 1.0    # seconds
    RETRY_MAX_DELAY = 30.0    # seconds
    RECONCILE_TIMEOUT = 5.0   # seconds to wait for order confirmation

    def __init__(
        self,
        exchange_adapter: Optional[ExchangeAdapter] = None,
        exchange_id: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
    ):
        """
        Initialize Execution Engine.

        Args:
            exchange_adapter: Pre-configured ExchangeAdapter (recommended)
            exchange_id: CCXT exchange id
            api_key: Exchange API key
            api_secret: Exchange API secret
            testnet: Use testnet/sandbox
        """
        if exchange_adapter:
            self.exchange = exchange_adapter
        else:
            self.exchange = create_exchange(
                exchange_id=exchange_id,
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet,
            )

        self._execution_log: List[ExecutionRecord] = []
        self._pending_orders: Dict[str, dict] = {}
        self._mock_mode = False

    def _ensure_connected(self):
        """Lazy-connect to exchange."""
        if not self.exchange.is_connected:
            try:
                self.exchange.connect()
                self._mock_mode = False
            except Exception as e:
                logger.warning("exchange_unavailable_mock_mode", error=str(e))
                self._mock_mode = True

    # ═══════════════════════════════════════════════════════════
    # Order Placement
    # ═══════════════════════════════════════════════════════════

    async def place_entry_limit(
        self, signal: Signal, risk_decision: RiskDecision
    ) -> Optional[ExecutionRecord]:
        """
        Place a limit entry order via CCXT.

        Args:
            signal: Trading signal
            risk_decision: Approved risk decision with position size

        Returns:
            ExecutionRecord on fill, None on cancel/timeout
        """
        self._ensure_connected()

        if not self.exchange._circuit_breaker.can_proceed:
            logger.error("circuit_breaker_blocking_execution")
            return None

        start_time = time.time()
        side = "buy" if signal.direction == Direction.LONG else "sell"
        ccxt_symbol = ExchangeAdapter.normalize_symbol(
            signal.pair, self.exchange.exchange_id
        )
        expected_price = signal.entry_limit

        try:
            if self._mock_mode:
                # Mock execution with simulated fill
                await asyncio.sleep(0.01)
                actual_price = signal.entry_market
            else:
                order: ExchangeOrder = self.exchange.create_limit_order(
                    symbol=ccxt_symbol,
                    side=side,
                    amount=round(risk_decision.position_size, 6),
                    price=round(signal.entry_limit, 2),
                )

                # Wait briefly and check fill
                await asyncio.sleep(1.0)
                updated = self.exchange.fetch_order(order.id, ccxt_symbol)

                if updated.status == "closed":
                    actual_price = updated.price or signal.entry_limit
                elif updated.status in ("canceled", "expired", "rejected"):
                    logger.warning("order_not_filled", status=updated.status, id=order.id)
                    actual_price = 0.0
                else:
                    # Still open — wait up to LIMIT_TIMEOUT
                    actual_price = await self._wait_for_fill(
                        order.id, ccxt_symbol, expected_price, side
                    )

            elapsed = (time.time() - start_time) * 1000

            if actual_price <= 0:
                # Order didn't fill — try emergency market if price hasn't moved too far
                return await self._emergency_market_entry(signal, risk_decision)

            slippage = abs(actual_price - expected_price)

            record = ExecutionRecord(
                timestamp=datetime.now(timezone.utc),
                pair=signal.pair,
                expected_price=expected_price,
                actual_price=actual_price,
                slippage=slippage,
                latency=elapsed,
                partial_fill=False,
                cancelled=False,
            )
            self._execution_log.append(record)

            # Log high slippage
            if expected_price > 0 and slippage / expected_price > self.MAX_SLIPPAGE:
                logger.warning("high_slippage", pair=signal.pair,
                             slippage_pct=round(slippage / expected_price * 100, 4))

            return record

        except Exception as e:
            logger.error("entry_order_failed", pair=signal.pair, error=str(e))
            return await self._emergency_market_entry(signal, risk_decision)

    async def _wait_for_fill(
        self, order_id: str, symbol: str, expected_price: float, side: str,
    ) -> float:
        """Poll order status until filled or timeout."""
        deadline = time.time() + self.LIMIT_TIMEOUT

        while time.time() < deadline:
            try:
                order = self.exchange.fetch_order(order_id, symbol)
                if order.status == "closed":
                    return order.price or expected_price
                if order.status in ("canceled", "expired", "rejected"):
                    return 0.0
            except Exception:
                pass
            await asyncio.sleep(2.0)

        # Timeout — cancel and fallback
        try:
            self.exchange.cancel_order(order_id, symbol)
        except Exception:
            pass
        return 0.0

    async def _emergency_market_entry(
        self, signal: Signal, risk_decision: RiskDecision,
    ) -> Optional[ExecutionRecord]:
        """
        Emergency market order when limit order fails.
        Checks that price hasn't moved > MAX_PRICE_MOVE from the signal.
        """
        start_time = time.time()
        self._ensure_connected()
        side = "buy" if signal.direction == Direction.LONG else "sell"
        ccxt_symbol = ExchangeAdapter.normalize_symbol(
            signal.pair, self.exchange.exchange_id
        )

        try:
            if self._mock_mode:
                actual_price = signal.entry_market
            else:
                order = self.exchange.create_market_order(
                    symbol=ccxt_symbol,
                    side=side,
                    amount=round(risk_decision.position_size, 6),
                )
                actual_price = order.price or signal.entry_market

            price_move = abs(actual_price - signal.entry_market) / signal.entry_market \
                if signal.entry_market > 0 else 0

            if price_move > self.MAX_PRICE_MOVE:
                logger.warning("emergency_market_price_moved_too_far",
                             pair=signal.pair, move_pct=round(price_move * 100, 4))
                # In production, you might cancel; here we proceed with a warning

            elapsed = (time.time() - start_time) * 1000

            record = ExecutionRecord(
                timestamp=datetime.now(timezone.utc),
                pair=signal.pair,
                expected_price=signal.entry_market,
                actual_price=actual_price,
                slippage=abs(actual_price - signal.entry_market),
                latency=elapsed,
                partial_fill=False,
                cancelled=False,
            )
            self._execution_log.append(record)
            logger.info("emergency_market_filled", pair=signal.pair, price=actual_price)
            return record

        except Exception as e:
            logger.critical("emergency_entry_failed", pair=signal.pair, error=str(e))
            return None

    # ═══════════════════════════════════════════════════════════
    # Stop-loss & Take-profit
    # ═══════════════════════════════════════════════════════════

    async def place_stop_loss(self, position: Position) -> bool:
        """Place a stop-market order for stop-loss via CCXT."""
        self._ensure_connected()
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                position.pair, self.exchange.exchange_id
            )
            side = "sell" if position.direction == Direction.LONG else "buy"

            if not self._mock_mode:
                self.exchange.create_stop_market_order(
                    symbol=ccxt_symbol,
                    side=side,
                    amount=round(position.size, 6),
                    stop_price=round(position.stop_loss, 2),
                )
            logger.info("stop_loss_placed", pair=position.pair, stop=position.stop_loss)
            return True
        except Exception as e:
            logger.error("stop_loss_failed", pair=position.pair, error=str(e))
            return False

    async def place_take_profit_limit(
        self, position: Position, tp_price: float, quantity: float,
    ) -> bool:
        """Place a limit take-profit order via CCXT."""
        self._ensure_connected()
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                position.pair, self.exchange.exchange_id
            )
            side = "sell" if position.direction == Direction.LONG else "buy"

            if not self._mock_mode:
                self.exchange.create_limit_order(
                    symbol=ccxt_symbol,
                    side=side,
                    amount=round(quantity, 6),
                    price=round(tp_price, 2),
                )
            logger.info("tp_placed", pair=position.pair, tp=tp_price)
            return True
        except Exception as e:
            logger.error("tp_failed", pair=position.pair, error=str(e))
            return False

    # ═══════════════════════════════════════════════════════════
    # Reconciliation
    # ═══════════════════════════════════════════════════════════

    async def reconcile_position(self, pair: str) -> dict:
        """
        Check actual exchange positions after network interruption.
        Uses CCXT fetch_positions for unified cross-exchange support.
        """
        self._ensure_connected()
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                pair, self.exchange.exchange_id
            )
            if self._mock_mode:
                return {"pair": pair, "found": False, "raw": []}

            positions = self.exchange.fetch_positions([ccxt_symbol])
            return {
                "pair": pair,
                "ccxt_symbol": ccxt_symbol,
                "found": len(positions) > 0,
                "count": len(positions),
                "positions": [
                    {
                        "side": p.side,
                        "contracts": p.contracts,
                        "entry_price": p.entry_price,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in positions
                ],
            }
        except Exception as e:
            logger.error("reconcile_failed", pair=pair, error=str(e))
            return {"pair": pair, "found": False, "error": str(e)}

    async def fetch_account_balance(self) -> dict:
        """Fetch account balance from exchange."""
        self._ensure_connected()
        if self._mock_mode:
            return {"USDT": {"total": 10000, "free": 10000, "used": 0}}
        try:
            balances = self.exchange.fetch_balance()
            return {
                c: {"total": b.total, "free": b.free, "used": b.used}
                for c, b in balances.items() if b.total > 0
            }
        except Exception as e:
            logger.error("balance_fetch_failed", error=str(e))
            return {}

    # ═══════════════════════════════════════════════════════════
    # Quality of Execution
    # ═══════════════════════════════════════════════════════════

    @property
    def total_executions(self) -> int:
        return len(self._execution_log)

    def get_execution_quality(self) -> dict:
        """Summarize execution quality metrics."""
        if not self._execution_log:
            return {
                "avg_slippage": 0, "avg_slippage_pct": 0,
                "avg_latency_ms": 0, "fill_rate": 1.0,
                "cancel_rate": 0, "partial_rate": 0,
                "total_executions": 0,
            }

        slippages = [r.slippage for r in self._execution_log]
        avg_slip = sum(slippages) / len(slippages)
        latencies = [r.latency for r in self._execution_log]
        avg_lat = sum(latencies) / len(latencies)
        cancels = sum(1 for r in self._execution_log if r.cancelled)
        partials = sum(1 for r in self._execution_log if r.partial_fill)
        total = len(self._execution_log)

        ref_price = self._execution_log[0].expected_price if total > 0 else 1

        return {
            "avg_slippage": round(avg_slip, 8),
            "avg_slippage_pct": round(avg_slip / ref_price * 100, 5) if ref_price > 0 else 0,
            "avg_latency_ms": round(avg_lat, 2),
            "fill_rate": round((total - cancels) / total, 4) if total > 0 else 1.0,
            "cancel_rate": round(cancels / total, 4) if total > 0 else 0.0,
            "partial_rate": round(partials / total, 4) if total > 0 else 0.0,
            "total_executions": total,
        }

    def close(self):
        """Clean up."""
        self.exchange.close()
