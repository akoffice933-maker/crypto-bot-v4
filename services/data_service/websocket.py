"""
Crypto Bot v4.5 — Real-time WebSocket Streams

CCXT Pro async exchange for live tick data.
Creates a separate async exchange instance for WebSocket streams
(independent from the sync adapter used for REST orders).

Streams:
  - watch_ohlcv()  → live candles per pair/timeframe
  - watch_ticker() → real-time price updates per pair

The bot uses these real-time prices and candles in the main loop
so it never waits 15 seconds for a price update — signals react
immediately when a level is touched.
"""

import asyncio
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import structlog

from core.models import OHLCV

logger = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Real-time market data via CCXT Pro (async exchange) WebSocket streams.

    Creates a dedicated `ccxt.pro.binance` (or bybit/okx) instance for
    watching live data. This is separate from the sync ExchangeAdapter
    used for REST order placement — they don't interfere.

    Usage in main.py:

        ws = WebSocketManager(exchange_id="binance", testnet=True)
        await ws.start(pairs=["BTCUSDT"], timeframes=["1h"])
        ...
        price = ws.get_latest_price("BTCUSDT")    # real-time
        candle = ws.get_latest_ohlcv("BTCUSDT", "1h")  # real-time
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
    ):
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._exchange = None          # ccxt.pro async exchange
        self._running = False
        self._tasks: List[asyncio.Task] = []

        # Callback registries
        self._ohlcv_callbacks: Dict[str, List[Callable]] = {}
        self._ticker_callbacks: Dict[str, List[Callable]] = {}

        # Latest data
        self._latest_ohlcv: Dict[str, OHLCV] = {}     # "PAIR:TF" → latest candle
        self._latest_tickers: Dict[str, dict] = {}      # "PAIR" → latest ticker

    # ═══════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════

    def on_ohlcv(self, pair: str, timeframe: str, callback: Callable[[OHLCV], None]):
        """Register callback: callback(OHLCV) on each new candle."""
        key = f"{pair}:{timeframe}"
        self._ohlcv_callbacks.setdefault(key, []).append(callback)

    def on_ticker(self, pair: str, callback: Callable[[dict], None]):
        """Register callback: callback(ticker_dict) on each price update."""
        self._ticker_callbacks.setdefault(pair, []).append(callback)

    def get_latest_ohlcv(self, pair: str, timeframe: str) -> Optional[OHLCV]:
        return self._latest_ohlcv.get(f"{pair}:{timeframe}")

    def get_latest_price(self, pair: str) -> float:
        """Get real-time price from WebSocket, or 0 if not available."""
        ticker = self._latest_tickers.get(pair, {})
        return ticker.get("last", 0) or ticker.get("close", 0) or 0

    def get_current_prices(self) -> Dict[str, float]:
        """Get all real-time prices from WebSocket tickers."""
        prices = {}
        for pair, ticker in self._latest_tickers.items():
            price = ticker.get("last") or ticker.get("close") or ticker.get("bid")
            if price and price > 0:
                prices[pair] = price
        return prices

    @property
    def is_connected(self) -> bool:
        return self._running and self._exchange is not None

    # ═══════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def start(self, pairs: List[str], timeframes: List[str]):
        """Create async exchange, connect, start all watch streams."""
        if self._running:
            return

        # ── Build ccxt.pro async exchange ─────────────────
        try:
            import ccxt.pro as ccxtpro
        except ImportError:
            logger.error("ccxt.pro_not_installed")
            return

        ExchangeClass = getattr(ccxtpro, self._exchange_id, None)
        if ExchangeClass is None and self._exchange_id == "binance":
            ExchangeClass = getattr(ccxtpro, "binanceusdm", ccxtpro.binance)

        if ExchangeClass is None:
            logger.error("ws_exchange_not_found", id=self._exchange_id)
            return

        config = {
            "apiKey": self._api_key,
            "secret": self._api_secret,
        }
        if self._exchange_id == "binance":
            config["options"] = {"defaultType": "future"}
            if self._testnet:
                config["urls"] = {
                    "api": {
                        "public": "https://testnet.binancefuture.com/fapi/v1",
                        "private": "https://testnet.binancefuture.com/fapi/v1",
                    }
                }

        self._exchange = ExchangeClass(config)
        await self._exchange.load_markets()
        self._running = True

        logger.info("ws_exchange_connected", exchange=self._exchange_id,
                    pairs=len(pairs), timeframes=len(timeframes))

        # ── Start watch streams ──────────────────────────
        for pair in pairs:
            ccxt_symbol = f"{pair[:3]}/{pair[3:]}:{pair[3:]}" if self._exchange_id == "binance" else f"{pair[:3]}/{pair[3:]}"

            # OHLCV streams
            for tf in timeframes:
                task = asyncio.create_task(
                    self._run_ohlcv_watch(pair, ccxt_symbol, tf),
                    name=f"ws_ohlcv_{pair}_{tf}",
                )
                self._tasks.append(task)

            # Ticker stream
            task = asyncio.create_task(
                self._run_ticker_watch(pair, ccxt_symbol),
                name=f"ws_ticker_{pair}",
            )
            self._tasks.append(task)

        logger.info("ws_streams_started", ohlcv=len(pairs)*len(timeframes), ticker=len(pairs))

    async def stop(self):
        """Stop all watch streams and close exchange."""
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception:
                pass
            self._exchange = None
        logger.info("ws_streams_stopped")

    # ═══════════════════════════════════════════════════════════
    # Internal: watch loops
    # ═══════════════════════════════════════════════════════════

    async def _run_ohlcv_watch(self, pair: str, ccxt_symbol: str, timeframe: str):
        """Continuously watch OHLCV candles for one pair/timeframe."""
        ccxt_tf = timeframe  # CCXT uses same format: "1m", "1h", "4h", "1d"
        key = f"{pair}:{timeframe}"

        while self._running:
            try:
                candles = await self._exchange.watch_ohlcv(ccxt_symbol, ccxt_tf)
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

                    for cb in self._ohlcv_callbacks.get(key, []):
                        try:
                            cb(ohlcv)
                        except Exception:
                            logger.debug("ws_ohlcv_cb_error", pair=pair, tf=timeframe, exc_info=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("ws_ohlcv_error", pair=pair, tf=timeframe, error=str(e))
                await asyncio.sleep(3)

    async def _run_ticker_watch(self, pair: str, ccxt_symbol: str):
        """Continuously watch ticker for one pair."""
        while self._running:
            try:
                ticker = await self._exchange.watch_ticker(ccxt_symbol)
                if ticker:
                    self._latest_tickers[pair] = ticker
                    for cb in self._ticker_callbacks.get(pair, []):
                        try:
                            cb(ticker)
                        except Exception:
                            logger.debug("ws_ticker_cb_error", pair=pair, exc_info=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("ws_ticker_error", pair=pair, error=str(e))
                await asyncio.sleep(3)
