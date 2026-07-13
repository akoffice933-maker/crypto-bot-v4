"""
Crypto Bot v4.4 — Unit Tests
Covers all core services.
"""

import math
from datetime import datetime, timedelta

import pytest

from core.models import (
    Direction, Features, MarketRegime, OHLCV, Regime,
    RiskDecision, Signal, StrategyType,
)
from services.data_validator.validator import DataValidator
from services.feature_service.calculator import FeatureCalculator
from services.regime_detector.detector import RegimeDetector, gaussian, sigmoid
from services.strategy_engine.engine import StrategyEngine
from services.risk_engine.engine import RiskEngine
from services.analytics_service.service import AnalyticsService
from services.learning_service.service import (
    ExpectedReturnEWMA, LearningService, StrategyBayesian,
)


# ═══════════════════════════════════════════════════════════════
# Data Validator Tests
# ═══════════════════════════════════════════════════════════════

class TestDataValidator:
    def test_valid_candles_pass(self):
        dv = DataValidator()
        candles = _make_candles(100)
        healthy, critical, non_critical = dv.validate_candles(candles, "1h")
        assert healthy is True
        assert len(critical) == 0

    def test_negative_price_fails(self):
        dv = DataValidator()
        candles = _make_candles(10)
        candles[5].open = -100
        healthy, critical, _ = dv.validate_candles(candles, "1h")
        assert not healthy
        assert any("negative_price" in c["type"] for c in critical)

    def test_duplicate_detection(self):
        dv = DataValidator()
        candles = _make_candles(10)
        candles.append(candles[0])  # duplicate
        _, critical, non_critical = dv.validate_candles(candles, "1h")
        assert any("duplicate" in nc["type"] for nc in non_critical)

    def test_excessive_gaps_fails(self):
        dv = DataValidator()
        candles = _make_candles(5)
        # Create >5% gaps
        candles[0].timestamp = datetime(2026, 1, 1, 0, 0)
        candles[1].timestamp = datetime(2026, 1, 1, 1, 0)
        candles[2].timestamp = datetime(2026, 1, 1, 3, 0)  # skip hour 2
        candles[3].timestamp = datetime(2026, 1, 1, 4, 0)
        candles[4].timestamp = datetime(2026, 1, 1, 5, 0)
        healthy, critical, _ = dv.validate_candles(candles, "1h")
        # ~20% gap → critical
        assert not healthy


# ═══════════════════════════════════════════════════════════════
# Feature Calculator Tests
# ═══════════════════════════════════════════════════════════════

class TestFeatureCalculator:
    def test_compute_all_features(self):
        fc = FeatureCalculator(["BTCUSDT"], ["1h"])
        candles = _make_price_candles(100, base=65000)
        features = fc.compute_all_features(candles, "BTCUSDT", "1h")

        assert features.pair == "BTCUSDT"
        assert features.timeframe == "1h"
        assert features.adx_14 >= 0
        assert features.atr_pct_14 >= 0
        assert features.bb_upper > features.bb_lower
        assert features.volume_ratio > 0

    def test_wick_ratio(self):
        fc = FeatureCalculator(["BTCUSDT"], ["1h"])
        ratio = fc.compute_wick_ratio(100, 110, 90, 105)
        # Upper wick: 110-105=5, body: 5, ratio=1.0
        assert ratio > 0

    def test_liquidity_levels(self):
        fc = FeatureCalculator(["BTCUSDT"], ["1h"])
        highs = [100 + i * 0.5 + 5 * math.sin(i/3) for i in range(60)]
        lows = [98 + i * 0.5 - 3 * math.cos(i/4) for i in range(60)]
        import numpy as np
        resistance, support = fc.find_liquidity_levels(
            np.array(highs), np.array(lows), lookback=50
        )
        assert isinstance(resistance, list)
        assert isinstance(support, list)


# ═══════════════════════════════════════════════════════════════
# Regime Detector Tests
# ═══════════════════════════════════════════════════════════════

class TestRegimeDetector:
    def test_trend_high_vol(self):
        rd = RegimeDetector()
        features = Features(
            timestamp=datetime.utcnow(), pair="BTCUSDT", timeframe="1h",
            adx_14=35, atr_percentile=90,
        )
        result = rd.detect(features)
        assert result.regime == Regime.TREND_HIGH_VOL

    def test_range_low_vol(self):
        rd = RegimeDetector()
        features = Features(
            timestamp=datetime.utcnow(), pair="BTCUSDT", timeframe="1h",
            adx_14=15, atr_percentile=10,
        )
        result = rd.detect(features)
        assert result.regime == Regime.RANGE_LOW_VOL

    def test_breakout_squeeze(self):
        rd = RegimeDetector()
        features = Features(
            timestamp=datetime.utcnow(), pair="BTCUSDT", timeframe="1h",
            adx_14=20, atr_percentile=50, squeeze_active=True,
        )
        result = rd.detect(features)
        assert result.regime == Regime.BREAKOUT

    def test_sigmoid_bounds(self):
        assert 0 < sigmoid(0) < 1
        assert sigmoid(100) > 0.99
        assert sigmoid(-100) < 0.01

    def test_gaussian_peak(self):
        assert gaussian(30, mean=30, sigma=10) == 1.0
        assert gaussian(20, mean=30, sigma=10) < 1.0

    def test_strategy_weights_sum_near_one(self):
        rd = RegimeDetector()
        features = Features(
            timestamp=datetime.utcnow(), pair="BTCUSDT", timeframe="1h",
            adx_14=25, atr_percentile=50,
        )
        result = rd.detect(features)
        total = sum(result.strategy_weights.values())
        assert abs(total - 1.0) < 0.01

    def test_predict_interface(self):
        rd = RegimeDetector()
        result = rd.predict({"pair": "BTCUSDT", "timeframe": "1h", "adx": 35, "atr_percentile": 90, "squeeze_active": False})
        assert result in [r.value for r in Regime]


# ═══════════════════════════════════════════════════════════════
# Strategy Engine Tests
# ═══════════════════════════════════════════════════════════════

class TestStrategyEngine:
    def test_signal_structure(self):
        signal = Signal(
            pair="BTCUSDT", direction=Direction.LONG,
            entry_market=65000, entry_limit=64990,
            stop_loss=64500, tp1=66000, tp2=67000,
            strategy=StrategyType.SWEEP, confidence=0.8,
            regime="trend_high_vol", factors=[], timestamp=datetime.utcnow(),
        )
        assert signal.pair == "BTCUSDT"
        assert signal.direction == Direction.LONG
        assert 0 <= signal.confidence <= 1

    def test_confidence_calculation(self):
        engine = StrategyEngine()
        conf = engine._calculate_confidence(1.0, 1.0, 1.0, 1.0, 1.0)
        assert conf == 1.0

        conf = engine._calculate_confidence(0.5, 0.5, 0.5, 0.5, 0.5)
        assert conf == 0.5

    def test_generate_signals_empty_on_flat_market(self):
        engine = StrategyEngine()
        features = Features(
            timestamp=datetime.utcnow(), pair="BTCUSDT", timeframe="1h",
            adx_14=10, atr_percentile=5,
            liquidity_levels_above=[], liquidity_levels_below=[],
        )
        regime = MarketRegime(
            regime=Regime.RANGE_LOW_VOL, confidence=0.8,
            adx=10, atr_percentile=5,
            strategy_weights={st: 1.0/3 for st in StrategyType},
        )
        candles = _make_price_candles(5, base=65000)
        signals = engine.generate_signals(features, regime, candles, "BTCUSDT")
        # With no liquidity levels, no signals should be generated
        assert len(signals) == 0


# ═══════════════════════════════════════════════════════════════
# Risk Engine Tests
# ═══════════════════════════════════════════════════════════════

class TestRiskEngine:
    def test_signal_approval(self):
        re = RiskEngine(balance=10000)
        signal = Signal(
            pair="BTCUSDT", direction=Direction.LONG,
            entry_market=65000, entry_limit=64990,
            stop_loss=64500, tp1=66000, tp2=67000,
            strategy=StrategyType.SWEEP, confidence=0.8,
            regime="trend_high_vol", factors=[], timestamp=datetime.utcnow(),
        )
        portfolio = re.get_portfolio_state()
        decision = re.evaluate_signal(signal, portfolio)
        assert decision.approved
        assert decision.position_size > 0

    def test_max_positions_limit(self):
        re = RiskEngine(balance=10000)
        signal = Signal(
            pair="BTCUSDT", direction=Direction.LONG,
            entry_market=65000, entry_limit=64990,
            stop_loss=64500, tp1=66000, tp2=67000,
            strategy=StrategyType.SWEEP, confidence=0.8,
            regime="trend", factors=[], timestamp=datetime.utcnow(),
        )
        portfolio = re.get_portfolio_state()
        portfolio.open_positions = 3  # max reached
        decision = re.evaluate_signal(signal, portfolio)
        assert not decision.approved
        assert "Max positions" in decision.reason

    def test_recovery_mode_halves_risk(self):
        re = RiskEngine(balance=10000)
        re._recovery_mode = True
        signal = Signal(
            pair="BTCUSDT", direction=Direction.LONG,
            entry_market=65000, entry_limit=64990,
            stop_loss=64500, tp1=66000, tp2=67000,
            strategy=StrategyType.SWEEP, confidence=0.8,
            regime="trend", factors=[], timestamp=datetime.utcnow(),
        )
        portfolio = re.get_portfolio_state()
        decision = re.evaluate_signal(signal, portfolio)
        assert decision.approved
        assert decision.recovery_mode

    def test_drawdown_limit_blocks_trade(self):
        re = RiskEngine(balance=10000)
        re.DRAWDOWN_LIMITS["daily"] = 1.0  # 1% daily limit
        signal = Signal(
            pair="BTCUSDT", direction=Direction.LONG,
            entry_market=65000, entry_limit=64990,
            stop_loss=64500, tp1=66000, tp2=67000,
            strategy=StrategyType.SWEEP, confidence=0.8,
            regime="trend", factors=[], timestamp=datetime.utcnow(),
        )
        portfolio = re.get_portfolio_state()
        portfolio.daily_drawdown = 2.0  # Already at 2%
        decision = re.evaluate_signal(signal, portfolio)
        assert not decision.approved


# ═══════════════════════════════════════════════════════════════
# Learning Service Tests
# ═══════════════════════════════════════════════════════════════

class TestBayesian:
    def test_initial_winrate(self):
        sb = StrategyBayesian(alpha=1, beta=1)
        assert sb.expected_winrate() == 0.5

    def test_update_win(self):
        sb = StrategyBayesian(alpha=1, beta=1)
        sb.update(True)
        assert sb.expected_winrate() == 2 / 3

    def test_multiple_updates(self):
        sb = StrategyBayesian(alpha=1, beta=1)
        for _ in range(7):
            sb.update(True)
        for _ in range(3):
            sb.update(False)
        assert sb.expected_winrate() == 8 / 12  # alpha=8, beta=4
        lower, upper = sb.credible_interval(0.95)
        assert 0 <= lower <= upper <= 1

class TestEWMA:
    def test_ewma_convergence(self):
        ewma = ExpectedReturnEWMA(lambda_=0.1)
        ewma.update(1.0)
        assert ewma.expected == 0.1
        for _ in range(100):
            ewma.update(1.0)
        assert abs(ewma.expected - 1.0) < 0.001

class TestLearningService:
    def test_record_trade(self):
        ls = LearningService()
        ls.record_trade("sweep", True, 2.0)
        ls.record_trade("sweep", False, -1.0)
        winrate = ls.get_strategy_winrate("sweep")
        assert winrate is not None
        assert 0 <= winrate["expected_winrate"] <= 1

    def test_multi_criteria_score(self):
        ls = LearningService()
        score = ls.multi_criteria_score({
            "sharpe": 1.5, "profit_factor": 1.8, "drawdown": 0.05, "stability": 0.8,
        })
        assert 0 <= score <= 1


# ═══════════════════════════════════════════════════════════════
# Analytics Tests
# ═══════════════════════════════════════════════════════════════

class TestAnalytics:
    def test_empty_metrics(self):
        srv = AnalyticsService()
        metrics = srv.get_metrics()
        assert metrics["total_trades"] == 0
        assert metrics["winrate"] == 0

    def test_basic_metrics(self):
        srv = AnalyticsService()
        srv.add_trade({
            "entry_price": 65000, "exit_price": 66000, "size": 0.1,
            "pnl": 100, "fees": 5, "is_win": True,
            "timestamp": datetime.utcnow(), "strategy": "sweep", "pair": "BTCUSDT",
        })
        srv.add_trade({
            "entry_price": 65000, "exit_price": 64500, "size": 0.1,
            "pnl": -50, "fees": 5, "is_win": False,
            "timestamp": datetime.utcnow(), "strategy": "sweep", "pair": "BTCUSDT",
        })
        metrics = srv.get_metrics()
        assert metrics["total_trades"] == 2
        assert metrics["winrate"] == 0.5
        assert metrics["profit_factor"] == 2.0


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _make_candles(n: int, base_price: float = 65000) -> list:
    """Generate n OHLCV candles at 1-hour intervals."""
    candles = []
    start = datetime(2026, 1, 1, 0, 0)
    for i in range(n):
        candles.append(OHLCV(
            timestamp=start + timedelta(hours=i),
            pair="BTCUSDT",
            timeframe="1h",
            open=base_price + i * 10,
            high=base_price + i * 10 + 50,
            low=base_price + i * 10 - 50,
            close=base_price + i * 10 + 20,
            volume=100 + i % 10,
        ))
    return candles


def _make_price_candles(n: int, base: float = 65000) -> list:
    """Generate candles with more realistic price variation."""
    import random
    random.seed(42)
    candles = []
    start = datetime(2026, 1, 1, 0, 0)
    price = base
    for i in range(n):
        change = random.gauss(0, base * 0.005)
        o = price
        c = price + change
        h = max(o, c) * (1 + random.uniform(0, 0.003))
        l = min(o, c) * (1 - random.uniform(0, 0.003))
        v = random.uniform(100, 1000)
        candles.append(OHLCV(
            timestamp=start + timedelta(hours=i),
            pair="BTCUSDT", timeframe="1h",
            open=o, high=h, low=l, close=c, volume=v,
        ))
        price = c
    return candles
