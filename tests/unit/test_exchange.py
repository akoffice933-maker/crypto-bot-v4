"""
Crypto Bot v4.4 — Exchange Adapter Tests (CCXT)
"""

from datetime import datetime

import pytest

from core.exchange.adapter import (
    CircuitBreaker, ExchangeAdapter, ExchangeBalance,
    ExchangeOrder, ExchangePosition, RateLimiter, create_exchange,
)


class TestCircuitBreaker:
    def test_initial_state(self):
        cb = CircuitBreaker(max_failures=3, reset_sec=60)
        assert cb.is_open is False
        assert cb.can_proceed is True

    def test_opens_after_max_failures(self):
        cb = CircuitBreaker(max_failures=3, reset_sec=60)
        cb.fail()
        cb.fail()
        assert cb.is_open is False
        cb.fail()
        assert cb.is_open is True
        assert cb.can_proceed is False

    def test_reset_on_success(self):
        cb = CircuitBreaker(max_failures=3, reset_sec=60)
        cb.fail()
        cb.fail()
        cb.success()
        assert cb.is_open is False
        assert cb.failures == 0

    def test_reset_after_timeout(self, monkeypatch):
        import time as time_module
        cb = CircuitBreaker(max_failures=2, reset_sec=0.1)
        cb.fail()
        cb.fail()
        assert cb.is_open is True

        # Simulate time passing
        monkeypatch.setattr(time_module, 'time', lambda: cb.last_failure + 0.2)
        assert cb.can_proceed is True
        assert cb.is_open is False


class TestSymbolNormalization:
    def test_normalize_usdt_pair(self):
        assert ExchangeAdapter.normalize_symbol("BTCUSDT") == "BTC/USDT"

    def test_normalize_busd_pair(self):
        assert ExchangeAdapter.normalize_symbol("ETHBUSD") == "ETH/BUSD"

    def test_denormalize(self):
        assert ExchangeAdapter.denormalize_symbol("BTC/USDT") == "BTCUSDT"
        assert ExchangeAdapter.denormalize_symbol("ETH/USDT:USDT") == "ETHUSDTUSDT"

    def test_roundtrip(self):
        pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        for pair in pairs:
            normed = ExchangeAdapter.normalize_symbol(pair)
            back = ExchangeAdapter.denormalize_symbol(normed.replace(":USDT", ""))
            assert pair in back or back in pair

    def test_tf_to_ccxt(self):
        assert ExchangeAdapter.tf_to_ccxt("1h") == "1h"
        assert ExchangeAdapter.tf_to_ccxt("4h") == "4h"
        assert ExchangeAdapter.tf_to_ccxt("15m") == "15m"
        assert ExchangeAdapter.tf_to_ccxt("1d") == "1d"


class TestExchangeAdapterInit:
    def test_create_without_keys(self):
        ex = create_exchange("binance", testnet=True)
        assert ex.exchange_id == "binance"
        assert ex.testnet is True
        assert not ex.is_connected

    def test_create_bybit(self):
        ex = create_exchange("bybit", testnet=True)
        assert ex.exchange_id == "bybit"
        assert ex.testnet is True

    def test_create_okx(self):
        ex = create_exchange("okx", testnet=True)
        assert ex.exchange_id == "okx"
        assert ex.testnet is True


class TestExchangeDataClasses:
    def test_exchange_balance(self):
        b = ExchangeBalance(free=100.0, used=50.0, total=150.0, currency="USDT")
        assert b.free == 100.0
        assert b.used == 50.0
        assert b.total == 150.0

    def test_exchange_order(self):
        o = ExchangeOrder(
            id="12345", symbol="BTC/USDT", side="buy",
            type="limit", status="closed",
            price=65000.0, amount=0.1, filled=0.1,
        )
        assert o.id == "12345"
        assert o.side == "buy"

    def test_exchange_position(self):
        p = ExchangePosition(
            symbol="BTC/USDT", side="long",
            contracts=1.0, entry_price=65000.0,
            mark_price=66000.0, unrealized_pnl=1000.0,
        )
        assert p.unrealized_pnl == 1000.0
        assert p.side == "long"


class TestRateLimiter:
    async def test_acquire_doesnt_block_initially(self):
        rl = RateLimiter(max_calls_per_second=100.0)
        import time as time_module
        start = time_module.monotonic()
        await rl.acquire()
        elapsed = time_module.monotonic() - start
        assert elapsed < 0.5  # Should be nearly instant with high rate
