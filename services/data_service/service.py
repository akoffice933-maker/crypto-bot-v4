"""
Crypto Bot v4.4 — Data Service
Fetches and stores market data from exchanges via CCXT.
Unified interface for 100+ exchanges (Binance, Bybit, OKX, Kraken, …).
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Tuple

import structlog

from core.database.db_manager import DatabaseManager
from core.exchange.adapter import ExchangeAdapter, create_exchange
from core.models import OHLCV

logger = structlog.get_logger(__name__)


class DataService:
    """
    Service responsible for fetching OHLCV, Open Interest, and Funding Rate
    data from exchanges via CCXT and storing it in the database.

    Sources (via CCXT unified API):
      - REST API:    OHLCV 1m, 5m, 15m, 1H, 4H, 1D
      - WebSocket:   Real-time tick/volume (via exchange adapter)
      - Open Interest API: 1H
      - Funding Rate API: periodic

    Supported exchanges:
      - Binance Futures (primary)
      - Bybit USDT Perpetual
      - OKX Swap
      - Kraken Futures
      - … 100+ via CCXT
    """

    # CCXT ↔ bot timeframe mapping
    TIMEFRAME_MAP = {
        "1m": "1m",   "5m": "5m",   "15m": "15m",
        "30m": "30m", "1h": "1h",   "2h": "2h",
        "4h": "4h",   "6h": "6h",   "12h": "12h",
        "1d": "1d",   "1w": "1w",
    }

    # Minimum data requirements per timeframe
    MIN_HISTORY: Dict[str, timedelta] = {
        "15m": timedelta(days=180),   # 6 months
        "1h":  timedelta(days=730),   # 2 years
        "4h":  timedelta(days=730),   # 2 years
        "1d":  timedelta(days=1825),  # 5 years
    }

    def __init__(
        self,
        db_manager: DatabaseManager,
        pairs: List[str],
        timeframes: List[str],
        exchange_adapter: Optional[ExchangeAdapter] = None,
        exchange_id: str = "binance",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        use_testnet: bool = True,
    ):
        """
        Initialize Data Service.

        Args:
            db_manager: Database manager instance
            pairs: Trading pairs in 'BTCUSDT' format
            timeframes: List of timeframes
            exchange_adapter: Pre-configured ExchangeAdapter (preferred)
            exchange_id: CCXT exchange id (used if adapter is None)
            api_key: Exchange API key
            api_secret: Exchange API secret
            use_testnet: Use testnet/sandbox
        """
        self.db = db_manager
        self.pairs = pairs
        self.timeframes = timeframes

        # Exchange adapter — injected or created
        if exchange_adapter:
            self.exchange = exchange_adapter
        else:
            self.exchange = create_exchange(
                exchange_id=exchange_id,
                api_key=api_key or "",
                api_secret=api_secret or "",
                testnet=use_testnet,
            )

        self._cache: Dict[str, List[OHLCV]] = {}    # key: "PAIR:TF" → candles
        self._running = False
        self._mock_mode = False

    def _get_cache_key(self, pair: str, timeframe: str) -> str:
        return f"{pair}:{timeframe}"

    def _ensure_connected(self):
        """Lazy-connect to exchange if not already connected."""
        if not self.exchange.is_connected:
            try:
                self.exchange.connect()
                self._mock_mode = False
            except Exception as e:
                logger.warning("exchange_unavailable_using_mock", error=str(e))
                self._mock_mode = True

    # ═══════════════════════════════════════════════════════════
    # CCXT-based data fetching
    # ═══════════════════════════════════════════════════════════

    async def fetch_historical_klines(
        self,
        pair: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[OHLCV]:
        """
        Fetch historical klines via CCXT.

        Args:
            pair: Trading pair in 'BTCUSDT' format
            timeframe: Bot timeframe ('1h', '4h', …)
            start: Start datetime
            end: Optional end datetime
            limit: Max candles per request

        Returns:
            List[OHLCV]
        """
        self._ensure_connected()
        candles: List[OHLCV] = []

        if self._mock_mode:
            logger.info("mock_fetch", pair=pair, tf=timeframe)
            return self._generate_mock_klines(pair, timeframe, start, end)

        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(pair, self.exchange.exchange_id)
            ccxt_tf = ExchangeAdapter.tf_to_ccxt(timeframe)

            raw_candles = self.exchange.fetch_ohlcv_range(
                symbol=ccxt_symbol,
                timeframe=ccxt_tf,
                since=start,
                until=end,
                limit=limit,
            )

            for row in raw_candles:
                ts = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
                candles.append(OHLCV(
                    timestamp=ts,
                    pair=pair,
                    timeframe=timeframe,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                ))

            logger.info(
                "fetch_klines_done",
                pair=pair, tf=timeframe, count=len(candles),
                source=self.exchange.exchange_id,
            )
        except Exception as e:
            logger.error("fetch_klines_error", pair=pair, tf=timeframe, error=str(e))
            # Fallback to mock
            candles = self._generate_mock_klines(pair, timeframe, start, end)

        return candles

    async def fetch_open_interest(self, pair: str) -> Optional[float]:
        """Fetch current Open Interest for a pair."""
        self._ensure_connected()
        if self._mock_mode:
            return None
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(pair, self.exchange.exchange_id)
            return self.exchange.fetch_open_interest(ccxt_symbol)
        except Exception as e:
            logger.warning("fetch_oi_failed", pair=pair, error=str(e))
            return None

    async def fetch_funding_rate(self, pair: str) -> Optional[float]:
        """Fetch current Funding Rate for a pair."""
        self._ensure_connected()
        if self._mock_mode:
            return None
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(pair, self.exchange.exchange_id)
            result = self.exchange.fetch_funding_rate(ccxt_symbol)
            return result.get("fundingRate", 0) if isinstance(result, dict) else None
        except Exception as e:
            logger.warning("fetch_funding_rate_failed", pair=pair, error=str(e))
            return None

    async def fetch_ticker(self, pair: str) -> Optional[dict]:
        """Fetch current ticker."""
        self._ensure_connected()
        if self._mock_mode:
            return {"last": 0, "bid": 0, "ask": 0}
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(pair, self.exchange.exchange_id)
            return self.exchange.fetch_ticker(ccxt_symbol)
        except Exception as e:
            logger.warning("fetch_ticker_failed", pair=pair, error=str(e))
            return None

    # ═══════════════════════════════════════════════════════════
    # Mock data generation (for development/testing)
    # ═══════════════════════════════════════════════════════════

    def _generate_mock_klines(
        self,
        pair: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        """Generate realistic mock OHLCV data for development and testing."""
        import random
        random.seed(hash(pair + timeframe) % (2 ** 31))

        if end is None:
            end = datetime.now(timezone.utc)

        tf_deltas = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "2h": timedelta(hours=2),
            "4h": timedelta(hours=4),
            "6h": timedelta(hours=6),
            "12h": timedelta(hours=12),
            "1d": timedelta(days=1),
            "1w": timedelta(weeks=1),
        }
        delta = tf_deltas.get(timeframe, timedelta(hours=1))

        base_price = {
            "BTCUSDT": 65000.0, "ETHUSDT": 3400.0,
            "SOLUSDT": 140.0,   "BNBUSDT": 580.0,
        }.get(pair, 100.0)

        candles = []
        current = start
        price = base_price

        while current <= end:
            change_pct = random.gauss(0, 0.005)
            open_p = price
            close_p = price * (1 + change_pct)
            high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.003))
            low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.003))
            vol = random.uniform(50, 500)

            candles.append(OHLCV(
                timestamp=current,
                pair=pair,
                timeframe=timeframe,
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                volume=round(vol, 4),
            ))
            price = close_p
            current += delta

        return candles

    # ═══════════════════════════════════════════════════════════
    # Storage & Caching
    # ═══════════════════════════════════════════════════════════

    async def store_klines(self, candles: List[OHLCV]):
        """Store fetched candles in the database and update cache."""
        if not candles:
            return
        records = [c.to_dict() for c in candles]
        session = self.db.get_session()
        try:
            self.db.insert_market_data_batch(records, session=session)
            for c in candles:
                key = self._get_cache_key(c.pair, c.timeframe)
                if key not in self._cache:
                    self._cache[key] = []
                # Merge into sorted cache
                existing = self._cache[key]
                existing.append(c)
                self._cache[key] = sorted(existing, key=lambda x: x.timestamp)
        except Exception as e:
            logger.error("store_klines_error", error=str(e))
            raise
        finally:
            session.close()

    async def fetch_and_store(
        self, pair: str, timeframe: str,
        start: datetime, end: Optional[datetime] = None,
    ) -> int:
        """Fetch klines and store them in one operation. Returns count."""
        candles = await self.fetch_historical_klines(pair, timeframe, start, end)
        if candles:
            await self.store_klines(candles)
        return len(candles)

    async def warmup_data(self) -> Dict[str, int]:
        """
        Fetch and store minimum required historical data for all pairs/timeframes.
        Runs in parallel with semaphore for rate limiting.
        Returns counts per pair:tf.
        """
        now = datetime.now(timezone.utc)
        semaphore = asyncio.Semaphore(4)  # Max 4 concurrent API calls

        async def _fetch_one(pair: str, tf: str) -> Tuple[str, str, int]:
            async with semaphore:
                min_hist = self.MIN_HISTORY.get(tf, timedelta(days=730))
                start = now - min_hist
                try:
                    count = await self.fetch_and_store(pair, tf, start, now)
                    logger.info("warmup_done", pair=pair, tf=tf, candles=count)
                    return pair, tf, count
                except Exception as e:
                    logger.error("warmup_failed", pair=pair, tf=tf, error=str(e))
                    return pair, tf, 0

        tasks = []
        for pair in self.pairs:
            for tf in self.timeframes:
                tasks.append(_fetch_one(pair, tf))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: Dict[str, int] = {}
        for item in results_list:
            if isinstance(item, Exception):
                logger.error("warmup_task_failed", error=str(item))
                continue
            pair, tf, count = item
            results[f"{pair}:{tf}"] = count

        return results

    # ═══════════════════════════════════════════════════════════
    # Read API
    # ═══════════════════════════════════════════════════════════

    async def get_latest_candles(
        self, pair: str, timeframe: str, n: int = 100,
    ) -> List[OHLCV]:
        """Get the N most recent candles (cache-first, DB fallback)."""
        key = self._get_cache_key(pair, timeframe)
        if key in self._cache and len(self._cache[key]) >= n:
            return sorted(self._cache[key], key=lambda c: c.timestamp)[-n:]

        # Fallback to DB
        start = datetime.now(timezone.utc) - timedelta(days=30)
        records = self.db.query_market_data(pair, timeframe, start)
        candles = [OHLCV(**r) for r in records]
        self._cache[key] = sorted(candles, key=lambda c: c.timestamp)
        return self._cache[key][-n:] if len(self._cache[key]) >= n else self._cache[key]

    def get_cached_candles(self, pair: str, timeframe: str) -> List[OHLCV]:
        """Get all cached candles for a pair/timeframe."""
        key = self._get_cache_key(pair, timeframe)
        return self._cache.get(key, [])

    async def get_current_prices(self) -> Dict[str, float]:
        """
        Get current prices for all configured pairs.
        Uses ticker when connected, falls back to latest cached close.
        """
        prices: Dict[str, float] = {}
        self._ensure_connected()

        for pair in self.pairs:
            try:
                if not self._mock_mode:
                    ticker = await self.fetch_ticker(pair)
                    if ticker and ticker.get("last", 0) > 0:
                        prices[pair] = ticker["last"]
                        continue
            except Exception:
                pass

            # Fallback to cache
            candles = await self.get_latest_candles(pair, "15m", n=1)
            if candles:
                prices[pair] = candles[0].close

        return prices

    # ═══════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════

    @property
    def is_connected(self) -> bool:
        return self.exchange.is_connected

    def get_exchange_info(self) -> dict:
        """Get exchange metadata."""
        return {
            "exchange_id": self.exchange.exchange_id,
            "testnet": self.exchange.testnet,
            "connected": self.exchange.is_connected,
            "mock_mode": self._mock_mode,
            "timeframes_supported": (
                self.exchange.get_supported_timeframes()
                if self.exchange.is_connected else list(self.TIMEFRAME_MAP.keys())
            ),
        }

    async def close(self):
        """Clean up resources."""
        self._running = False
        self.exchange.close()
        logger.info("data_service_shutdown")
