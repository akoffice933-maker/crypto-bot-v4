"""
Crypto Bot v4.4 — Data Service WebSocket Extension
Real-time market data via CCXT WebSocket streams (watch_ohlcv, watch_ticker).
Falls back to REST polling when WebSocket is unavailable.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import structlog

from core.models import OHLCV

logger = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Manages CCXT WebSocket connections for real-time market data.

    Uses CCXT's built-in watch_* methods which handle:
      - Auto-reconnection on disconnect
      - Ping/pong keepalive
      - Message deduplication
      - Exchange-specific subscription handling
    """

    def __init__(self, exchange_adapter, pairs: List[str], timeframes: List[str]):
        self.exchange = exchange_adapter
        self.pairs = pairs
        self.timeframes = timeframes
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._ohlcv_callbacks: Dict[str, List[Callable]] = {}   # "PAIR:TF" → [callbacks]
        self._ticker_callbacks: Dict[str, List[Callable]] = {}  # "PAIR" → [callbacks]
        self._latest_ohlcv: Dict[str, OHLCV] = {}               # "PAIR:TF" → latest candle
        self._latest_tickers: Dict[str, dict] = {}               # "PAIR" → latest ticker
        self._connected = False

    # ═══════════════════════════════════════════════════════════
    # Subscription Management
    # ═══════════════════════════════════════════════════════════

    def on_ohlcv(self, pair: str, timeframe: str, callback: Callable):
        """Register a callback for OHLCV updates. callback(OHLCV)."""
        key = f"{pair}:{timeframe}"
        if key not in self._ohlcv_callbacks:
            self._ohlcv_callbacks[key] = []
        self._ohlcv_callbacks[key].append(callback)

    def on_ticker(self, pair: str, callback: Callable):
        """Register a callback for ticker updates. callback(dict)."""
        if pair not in self._ticker_callbacks:
            self._ticker_callbacks[pair] = []
        self._ticker_callbacks[pair].append(callback)

    # ═══════════════════════════════════════════════════════════
    # WebSocket Streams
    # ═══════════════════════════════════════════════════════════

    async def _watch_ohlcv_stream(self, pair: str, timeframe: str):
        """Watch OHLCV candles for a single pair/timeframe via CCXT WebSocket."""
        ccxt_symbol = self.exchange.normalize_symbol(pair, self.exchange.exchange_id)
        ccxt_tf = self.exchange.tf_to_ccxt(timeframe)
        key = f"{pair}:{timeframe}"

        # If exchange doesn't support watchOHLCV, we skip silently
        if not self.exchange.exchange or not self.exchange.is_connected:
            return

        while self._running:
            try:
                candles = await self.exchange._safe_call(
                    "watch_ohlcv", ccxt_symbol, ccxt_tf
                )
                if candles and len(candles) > 0:
                    latest = candles[-1]
                    ohlcv = OHLCV(
                        timestamp=datetime.fromtimestamp(latest[0] / 1000, tz=timezone.utc),
                        pair=pair,
                        timeframe=timeframe,
                        open=float(latest[1]),
                        high=float(latest[2]),
                        low=float(latest[3]),
                        close=float(latest[4]),
                        volume=float(latest[5]),
                    )
                    self._latest_ohlcv[key] = ohlcv

                    # Notify callbacks
                    for cb in self._ohlcv_callbacks.get(key, []):
                        try:
                            cb(ohlcv)
                        except Exception:
                            logger.warning("ws_ohlcv_callback_failed", pair=pair, tf=timeframe,
                                          exc_info=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("ws_ohlcv_error", pair=pair, tf=timeframe, error=str(e))
                await asyncio.sleep(5)  # Wait before retry

    async def _watch_ticker_stream(self, pair: str):
        """Watch ticker for a single pair via CCXT WebSocket."""
        ccxt_symbol = self.exchange.normalize_symbol(pair, self.exchange.exchange_id)

        if not self.exchange.exchange or not self.exchange.is_connected:
            return

        while self._running:
            try:
                ticker = await self.exchange._safe_call(
                    "watch_ticker", ccxt_symbol
                )
                if ticker:
                    self._latest_tickers[pair] = ticker

                    for cb in self._ticker_callbacks.get(pair, []):
                        try:
                            cb(ticker)
                        except Exception:
                            logger.warning("ws_ticker_callback_failed", pair=pair,
                                          exc_info=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("ws_ticker_error", pair=pair, error=str(e))
                await asyncio.sleep(5)

    # ═══════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def start(self):
        """Start all WebSocket watchers."""
        if self._running:
            return

        if not self.exchange.is_connected:
            try:
                self.exchange.connect()
            except Exception as e:
                logger.warning("ws_cannot_connect_exchange", error=str(e))
                return

        self._running = True

        # OHLCV streams for all pairs × timeframes
        for pair in self.pairs:
            for tf in self.timeframes:
                task = asyncio.create_task(
                    self._watch_ohlcv_stream(pair, tf),
                    name=f"ws_ohlcv_{pair}_{tf}",
                )
                self._tasks.append(task)

        # Ticker streams for all pairs
        for pair in self.pairs:
            task = asyncio.create_task(
                self._watch_ticker_stream(pair),
                name=f"ws_ticker_{pair}",
            )
            self._tasks.append(task)

        self._connected = True
        logger.info("websocket_streams_started",
                    pairs=len(self.pairs),
                    ohlcv_streams=len(self.pairs) * len(self.timeframes),
                    ticker_streams=len(self.pairs))

    async def stop(self):
        """Stop all WebSocket watchers gracefully."""
        self._running = False
        self._connected = False

        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("websocket_streams_stopped")

    # ═══════════════════════════════════════════════════════════
    # Read API
    # ═══════════════════════════════════════════════════════════

    def get_latest_ohlcv(self, pair: str, timeframe: str) -> Optional[OHLCV]:
        """Get the latest WebSocket-delivered OHLCV candle."""
        return self._latest_ohlcv.get(f"{pair}:{timeframe}")

    def get_latest_ticker(self, pair: str) -> Optional[dict]:
        """Get the latest WebSocket-delivered ticker."""
        return self._latest_tickers.get(pair)

    def get_current_prices_from_ws(self) -> Dict[str, float]:
        """Extract current prices from latest tickers."""
        prices = {}
        for pair, ticker in self._latest_tickers.items():
            price = ticker.get("last") or ticker.get("close") or ticker.get("bid")
            if price and price > 0:
                prices[pair] = price
        return prices

    @property
    def is_connected(self) -> bool:
        return self._connected and self._running
