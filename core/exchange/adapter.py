"""
Crypto Bot v4.4 — Exchange Adapter
Unified exchange interface via CCXT.
Supports Binance Futures as primary exchange; CCXT enables
easy migration to 100+ other exchanges with the same API.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Enums & Data Classes
# ═══════════════════════════════════════════════════════════════

class ExchangeID(str, Enum):
    """CCXT exchange identifiers supported by the bot."""
    BINANCE = "binance"
    BINANCE_FUTURES = "binance"
    BINANCE_TESTNET = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    KRAKEN_FUTURES = "krakenfutures"


class OrderSideCCXT(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderTypeCCXT(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderStatusCCXT(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class ExchangeBalance:
    """Account balance info."""
    free: float = 0.0
    used: float = 0.0
    total: float = 0.0
    currency: str = "USDT"


@dataclass
class ExchangeOrder:
    """Order returned by the exchange."""
    id: str = ""
    symbol: str = ""
    side: str = ""
    type: str = ""
    status: str = ""
    price: float = 0.0
    amount: float = 0.0
    filled: float = 0.0
    remaining: float = 0.0
    cost: float = 0.0
    fee: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw: dict = field(default_factory=dict)


@dataclass
class ExchangePosition:
    """Open position on the exchange."""
    symbol: str = ""
    side: str = ""            # long / short
    contracts: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0
    leverage: float = 1.0
    raw: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """Protects against cascading API failures."""

    def __init__(self, max_failures: int = 5, reset_sec: float = 60.0):
        self.max_failures = max_failures
        self.reset_sec = reset_sec
        self.failures: int = 0
        self.last_failure: float = 0.0
        self._open: bool = False

    def fail(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.max_failures:
            self._open = True
            logger.critical("circuit_breaker_open", failures=self.failures)

    def success(self):
        self.failures = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        if not self._open:
            return False
        if time.time() - self.last_failure > self.reset_sec:
            self._open = False
            self.failures = 0
            logger.info("circuit_breaker_reset")
            return False
        return True

    @property
    def can_proceed(self) -> bool:
        return not self.is_open


# ═══════════════════════════════════════════════════════════════
# Rate Limiter
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """Token-bucket rate limiter for exchange API calls."""

    def __init__(self, max_calls_per_second: float = 10.0):
        self.rate = max_calls_per_second
        self.tokens = max_calls_per_second
        self.last_refill = time.monotonic()

    async def acquire(self):
        """Wait until a token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return

            wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(wait)


# ═══════════════════════════════════════════════════════════════
# Main Exchange Adapter
# ═══════════════════════════════════════════════════════════════

class ExchangeAdapter:
    """
    Unified exchange interface powered by CCXT.

    Features:
      - Single API for 100+ exchanges (Binance, Bybit, OKX, Kraken, …)
      - Built-in rate limiting and circuit breaker
      - Async-compatible with sync fallback
      - Automatic sandbox/testnet detection
      - Position and balance tracking
      - Order lifecycle management
    """

    # CCXT exchange class mapping
    EXCHANGE_CLASSES = {
        "binance": "binance",
        "bybit": "bybit",
        "okx": "okx",
        "krakenfutures": "krakenfutures",
    }

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        password: str = "",
        testnet: bool = True,
        timeout: int = 30000,
        enable_rate_limit: bool = True,
    ):
        """
        Initialize exchange adapter.

        Args:
            exchange_id: CCXT exchange id (binance, bybit, okx, …)
            api_key: Exchange API key
            api_secret: Exchange API secret
            password: Exchange password (required for some exchanges like Coinbase Pro)
            testnet: Use sandbox/testnet
            timeout: Request timeout in ms
            enable_rate_limit: Enable built-in CCXT rate limiting
        """
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.password = password
        self.testnet = testnet
        self.timeout = timeout
        self.enable_rate_limit = enable_rate_limit

        self._exchange: Optional[Any] = None
        self._circuit_breaker = CircuitBreaker()
        self._rate_limiter = RateLimiter(max_calls_per_second=10.0)
        self._initialized = False

    # ------- Initialization -------

    def _build_config(self) -> dict:
        """Build the CCXT exchange configuration dictionary."""
        config: dict = {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "password": self.password,
            "timeout": self.timeout,
            "enableRateLimit": self.enable_rate_limit,
        }

        # Testnet / sandbox
        if self.testnet:
            if self.exchange_id in ("binance", "binanceusdm"):
                config["urls"] = {
                    "api": {
                        "public": "https://testnet.binancefuture.com/fapi/v1",
                        "private": "https://testnet.binancefuture.com/fapi/v1",
                    },
                }
                config["options"] = {"defaultType": "future"}
            elif self.exchange_id == "bybit":
                config["urls"] = {
                    "api": {"public": "https://api-testnet.bybit.com",
                            "private": "https://api-testnet.bybit.com"}
                }
                config["options"] = {"defaultType": "swap"}
            elif self.exchange_id == "okx":
                config["options"] = {"sandbox": True, "defaultType": "swap"}
        else:
            # Production futures
            if self.exchange_id in ("binance", "binanceusdm"):
                config["options"] = {"defaultType": "future"}
            elif self.exchange_id in ("bybit", "okx"):
                config["options"] = {"defaultType": "swap"}

        return config

    def connect(self):
        """Initialize the CCXT exchange instance."""
        if self._initialized:
            return

        try:
            import ccxt
        except ImportError:
            raise ImportError(
                "ccxt is required. Install with: pip install ccxt"
            )

        exchange_class = getattr(ccxt, self.exchange_id, None)
        if exchange_class is None:
            # Try binanceusdm for Binance Futures specifically
            if self.exchange_id == "binance":
                exchange_class = getattr(ccxt, "binanceusdm", ccxt.binance)
            else:
                raise ValueError(f"Unsupported exchange: {self.exchange_id}")

        config = self._build_config()
        self._exchange = exchange_class(config)

        # Load markets to validate connection
        self._exchange.load_markets()
        self._initialized = True

        logger.info(
            "exchange_connected",
            exchange=self.exchange_id,
            testnet=self.testnet,
            markets_loaded=len(self._exchange.markets),
        )

    @property
    def exchange(self) -> Any:
        """Get the underlying CCXT exchange object."""
        if not self._initialized:
            self.connect()
        return self._exchange

    @property
    def is_connected(self) -> bool:
        return self._initialized and self._exchange is not None

    # ------- Safety wrappers -------

    async def _safe_call(self, method_name: str, *args, **kwargs):
        """
        Wrap an exchange API call with circuit breaker, rate limit,
        retries, and error handling.
        """
        if self._circuit_breaker.is_open:
            raise RuntimeError("Circuit breaker open — trading halted")

        await self._rate_limiter.acquire()

        method = getattr(self.exchange, method_name, None)
        if method is None:
            raise AttributeError(f"Exchange has no method '{method_name}'")

        for attempt in range(3):
            try:
                result = method(*args, **kwargs)
                self._circuit_breaker.success()
                return result
            except Exception as e:
                logger.warning(
                    "exchange_call_failed",
                    method=method_name,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    self._circuit_breaker.fail()
                    raise

    def _safe_call_sync(self, method_name: str, *args, **kwargs):
        """Synchronous version of _safe_call."""
        if self._circuit_breaker.is_open:
            raise RuntimeError("Circuit breaker open — trading halted")

        method = getattr(self.exchange, method_name, None)
        if method is None:
            raise AttributeError(f"Exchange has no method '{method_name}'")

        for attempt in range(3):
            try:
                result = method(*args, **kwargs)
                self._circuit_breaker.success()
                return result
            except Exception as e:
                logger.warning(
                    "exchange_call_failed",
                    method=method_name,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    self._circuit_breaker.fail()
                    raise

    # ═══════════════════════════════════════════════════════════
    # Market Data API
    # ═══════════════════════════════════════════════════════════

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[List[float]]:
        """
        Fetch OHLCV candles from the exchange.

        Args:
            symbol: Trading pair (e.g. 'BTC/USDT')
            timeframe: CCXT timeframe ('1m','5m','15m','1h','4h','1d')
            since: Start datetime (None = earliest available)
            limit: Max candles to fetch

        Returns:
            List of [timestamp_ms, open, high, low, close, volume]
        """
        since_ms = int(since.timestamp() * 1000) if since else None
        return self._safe_call_sync(
            "fetch_ohlcv", symbol, timeframe, since_ms, limit
        )

    def fetch_ohlcv_range(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[List[float]]:
        """
        Fetch OHLCV candles over a date range with automatic pagination.
        """
        since_ms = int(since.timestamp() * 1000) if since else None
        until_ms = int(until.timestamp() * 1000) if until else None
        all_candles = []
        current_since = since_ms

        while True:
            candles = self._safe_call_sync(
                "fetch_ohlcv", symbol, timeframe, current_since, limit
            )
            if not candles:
                break

            # Filter by until
            if until_ms:
                candles = [c for c in candles if c[0] <= until_ms]

            all_candles.extend(candles)

            if len(candles) < limit:
                break
            if until_ms and candles[-1][0] >= until_ms:
                break

            current_since = candles[-1][0] + 1
            time.sleep(0.05)

        return all_candles

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch current ticker for a symbol."""
        return self._safe_call_sync("fetch_ticker", symbol)

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch order book (bids + asks)."""
        return self._safe_call_sync("fetch_order_book", symbol, limit)

    def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest for a futures symbol."""
        return self._safe_call_sync("fetch_open_interest", symbol)

    def fetch_funding_rate(self, symbol: str) -> dict:
        """Fetch current funding rate."""
        return self._safe_call_sync("fetch_funding_rate", symbol)

    # ═══════════════════════════════════════════════════════════
    # Trading API
    # ═══════════════════════════════════════════════════════════

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ) -> ExchangeOrder:
        """
        Place a limit order.

        Args:
            symbol: Trading pair (e.g. 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Quantity in base currency
            price: Limit price

        Returns:
            ExchangeOrder with order details
        """
        raw = self._safe_call_sync(
            "create_order", symbol, "limit", side, amount, price
        )
        return self._parse_order(raw)

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
    ) -> ExchangeOrder:
        """Place a market order."""
        raw = self._safe_call_sync(
            "create_order", symbol, "market", side, amount
        )
        return self._parse_order(raw)

    def create_stop_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
    ) -> ExchangeOrder:
        """Place a stop-market order (stop-loss)."""
        params = {"stopPrice": stop_price}
        raw = self._safe_call_sync(
            "create_order", symbol, "stop_market", side, amount, None, params
        )
        return self._parse_order(raw)

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        result = self._safe_call_sync("cancel_order", order_id, symbol)
        return result is not None

    def fetch_order(self, order_id: str, symbol: str) -> ExchangeOrder:
        """Fetch order status by ID."""
        raw = self._safe_call_sync("fetch_order", order_id, symbol)
        return self._parse_order(raw)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrder]:
        """Fetch all open orders."""
        raw = self._safe_call_sync("fetch_open_orders", symbol)
        return [self._parse_order(o) for o in raw]

    # ═══════════════════════════════════════════════════════════
    # Account API
    # ═══════════════════════════════════════════════════════════

    def fetch_balance(self) -> Dict[str, ExchangeBalance]:
        """Fetch account balances."""
        raw = self._safe_call_sync("fetch_balance")
        balances = {}
        for currency, data in raw.items():
            if isinstance(data, dict) and ("free" in data or "total" in data):
                balances[currency] = ExchangeBalance(
                    free=data.get("free", 0) or 0,
                    used=data.get("used", 0) or 0,
                    total=data.get("total", 0) or 0,
                    currency=currency,
                )
        return balances

    def fetch_positions(
        self, symbols: Optional[List[str]] = None
    ) -> List[ExchangePosition]:
        """Fetch open positions (futures)."""
        raw = self._safe_call_sync("fetch_positions", symbols)
        positions = []
        for p in raw:
            if p.get("contracts", 0) != 0:
                positions.append(ExchangePosition(
                    symbol=p.get("symbol", ""),
                    side=p.get("side", ""),
                    contracts=p.get("contracts", 0) or 0,
                    entry_price=p.get("entryPrice", 0) or 0,
                    mark_price=p.get("markPrice", 0) or 0,
                    unrealized_pnl=p.get("unrealizedPnl", 0) or 0,
                    liquidation_price=p.get("liquidationPrice", 0) or 0,
                    leverage=p.get("leverage", 1) or 1,
                    raw=p,
                ))
        return positions

    def set_leverage(self, symbol: str, leverage: float):
        """Set leverage for a futures symbol."""
        return self._safe_call_sync("set_leverage", leverage, symbol)

    def set_margin_mode(self, symbol: str, mode: str = "isolated"):
        """Set margin mode (isolated / cross)."""
        params = {"symbol": symbol, "marginMode": mode}
        return self._safe_call_sync("set_margin_mode", mode, symbol)

    # ═══════════════════════════════════════════════════════════
    # Utility
    # ═══════════════════════════════════════════════════════════

    def _parse_order(self, raw: dict) -> ExchangeOrder:
        """Parse CCXT raw order into ExchangeOrder."""
        return ExchangeOrder(
            id=str(raw.get("id", "")),
            symbol=raw.get("symbol", ""),
            side=raw.get("side", ""),
            type=raw.get("type", ""),
            status=raw.get("status", ""),
            price=raw.get("price", 0) or 0,
            amount=raw.get("amount", 0) or 0,
            filled=raw.get("filled", 0) or 0,
            remaining=raw.get("remaining", 0) or 0,
            cost=raw.get("cost", 0) or 0,
            fee=(raw.get("fee", {}) or {}).get("cost", 0) or 0,
            timestamp=datetime.utcfromtimestamp(
                raw.get("timestamp", 0) / 1000
            ) if raw.get("timestamp") else datetime.utcnow(),
            raw=raw,
        )

    @staticmethod
    def normalize_symbol(pair: str, exchange_id: str = "binance") -> str:
        """
        Convert a pair like 'BTCUSDT' to CCXT format 'BTC/USDT'.
        Handles edge cases like USDC, BUSD, etc.
        """
        # Common quote currencies
        quote_currencies = ["USDT", "USDC", "BUSD", "USD", "BTC", "ETH", "BNB"]

        # Handle USDT-margined futures on Binance (BTC/USDT:USDT)
        for quote in quote_currencies:
            if pair.endswith(quote) and pair != quote:
                base = pair[:-len(quote)]
                return f"{base}/{quote}"

        # Fallback: insert '/' in the middle-ish
        mid = len(pair) // 2
        return f"{pair[:mid]}/{pair[mid:]}"

    @staticmethod
    def denormalize_symbol(ccxt_symbol: str) -> str:
        """Convert 'BTC/USDT' back to 'BTCUSDT'."""
        return ccxt_symbol.replace("/", "").replace(":", "")

    @staticmethod
    def tf_to_ccxt(tf: str) -> str:
        """
        Convert bot timeframe format to CCXT format.

        Bot: '15m', '1h', '4h', '1d'
        CCXT: '15m', '1h', '4h', '1d'  (mostly identical)
        """
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "2h": "2h",
            "4h": "4h",
            "6h": "6h",
            "12h": "12h",
            "1d": "1d",
            "1w": "1w",
        }
        return mapping.get(tf, tf)

    def get_markets(self) -> dict:
        """Get all available markets from the exchange."""
        return self.exchange.markets

    def get_supported_timeframes(self) -> List[str]:
        """Get timeframes supported by the exchange."""
        return list(self.exchange.timeframes.keys()) if self.exchange.timeframes else []

    def close(self):
        """Clean up exchange resources."""
        self._initialized = False
        self._exchange = None
        logger.info("exchange_disconnected", exchange=self.exchange_id)


# ═══════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════

def create_exchange(
    exchange_id: str = "binance",
    api_key: str = "",
    api_secret: str = "",
    password: str = "",
    testnet: bool = True,
) -> ExchangeAdapter:
    """
    Factory function to create an ExchangeAdapter.

    Usage:
        ex = create_exchange("binance", api_key="...", api_secret="...")
        ex.connect()
        candles = ex.fetch_ohlcv("BTC/USDT", "1h")

    Supported exchanges via CCXT:
        - binance     (Binance Futures)
        - bybit       (Bybit USDT Perpetual)
        - okx         (OKX Swap)
        - krakenfutures
        - … 100+ more via CCXT
    """
    return ExchangeAdapter(
        exchange_id=exchange_id,
        api_key=api_key,
        api_secret=api_secret,
        password=password,
        testnet=testnet,
    )
