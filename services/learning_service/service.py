"""
Crypto Bot v4.4 — Learning Service
Offline learning and optimization: Walk Forward analysis,
Bayesian strategy evaluation, EWMA expected return,
multi-criteria scoring, and config candidate generation.
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from core.models import LearningConfig

logger = structlog.get_logger(__name__)


class StrategyBayesian:
    """
    Bayesian update for estimating strategy winrate probability.
    Uses Beta distribution with alpha (wins), beta (losses).
    """

    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        self.alpha = alpha
        self.beta = beta

    def update(self, is_win: bool):
        """Update posterior distribution with new trade result."""
        if is_win:
            self.alpha += 1
        else:
            self.beta += 1

    def expected_winrate(self) -> float:
        """Expected (mean) winrate from Beta(alpha, beta)."""
        return self.alpha / (self.alpha + self.beta)

    def variance(self) -> float:
        """Variance of the posterior."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))

    def std(self) -> float:
        return math.sqrt(self.variance())

    def credible_interval(self, prob: float = 0.95) -> Tuple[float, float]:
        """
        Approximate credible interval using normal approximation.
        Accurate for reasonable alpha, beta values.
        """
        mean = self.expected_winrate()
        std = self.std()
        z = 1.96 if prob == 0.95 else 2.576  # 95% or 99%
        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)
        return lower, upper


class ExpectedReturnEWMA:
    """
    Exponentially Weighted Moving Average of trade returns.
    Tracks expected return adaptively.
    """

    def __init__(self, lambda_: float = 0.05):
        self.lambda_ = lambda_
        self.ewma_return = 0.0
        self._n = 0

    def update(self, rr: float):
        """Update EWMA with a new return value (risk/reward realized)."""
        self.ewma_return = self.lambda_ * rr + (1 - self.lambda_) * self.ewma_return
        self._n += 1

    @property
    def expected(self) -> float:
        return self.ewma_return

    @property
    def n_updates(self) -> int:
        return self._n


class WalkForwardResult:
    """Result of a single Walk Forward window."""

    def __init__(self, window_index: int, train_start: datetime, train_end: datetime,
                 test_start: datetime, test_end: datetime, metrics: dict):
        self.window_index = window_index
        self.train_start = train_start
        self.train_end = train_end
        self.test_start = test_start
        self.test_end = test_end
        self.metrics = metrics


class LearningService:
    """
    Offline learning service.
    Runs Walk Forward analysis periodically and produces candidate configs.
    Online mode only collects statistics; parameters are NOT changed live.
    """

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self._bayesians: Dict[str, StrategyBayesian] = {}
        self._ewma = ExpectedReturnEWMA(lambda_=0.05)
        self._walk_forward_results: List[WalkForwardResult] = []
        self._trade_count = 0

    def record_trade(self, strategy: str, is_win: bool, rr_realized: float):
        """Record a trade outcome for online learning (statistics only)."""
        self._trade_count += 1

        # Update Bayesian
        if strategy not in self._bayesians:
            self._bayesians[strategy] = StrategyBayesian()
        self._bayesians[strategy].update(is_win)

        # Update EWMA
        self._ewma.update(rr_realized)

    def get_strategy_winrate(self, strategy: str) -> Optional[dict]:
        """Get Bayesian winrate estimate for a strategy."""
        if strategy not in self._bayesians:
            return None
        b = self._bayesians[strategy]
        lower, upper = b.credible_interval(0.95)
        return {
            "expected_winrate": round(b.expected_winrate(), 4),
            "std": round(b.std(), 4),
            "ci_lower": round(lower, 4),
            "ci_upper": round(upper, 4),
        }

    def get_expected_return(self) -> float:
        return self._ewma.expected

    def run_walk_forward(
        self,
        all_trades: List[dict],
        start_date: datetime,
        end_date: datetime,
    ) -> List[WalkForwardResult]:
        """
        Run Walk Forward analysis on historical trade data.

        Args:
            all_trades: List of trade dicts with 'timestamp' and 'pnl'
            start_date: Overall start of analysis
            end_date: Overall end of analysis

        Returns:
            List of WalkForwardResult for each window.

        Parameters:
          - Train window: 6 months
          - Test window: 1 month
          - Step: 1 month
          - Min stable windows: 3
        """
        train_months = self.config.train_period
        test_months = self.config.test_period
        step_months = self.config.step

        results = []
        current_start = start_date
        window_idx = 0

        while current_start + timedelta(days=(train_months + test_months) * 30) <= end_date:
            train_start = current_start
            train_end = train_start + timedelta(days=train_months * 30)
            test_start = train_end
            test_end = test_start + timedelta(days=test_months * 30)

            # Filter trades
            train_trades = [t for t in all_trades
                          if train_start <= t["timestamp"] < train_end]
            test_trades = [t for t in all_trades
                          if test_start <= t["timestamp"] < test_end]

            if len(train_trades) >= self.config.min_trades:
                # Compute metrics on test set
                test_metrics = self._compute_window_metrics(test_trades)
                result = WalkForwardResult(
                    window_index=window_idx,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    metrics=test_metrics,
                )
                results.append(result)

            current_start += timedelta(days=step_months * 30)
            window_idx += 1

        self._walk_forward_results = results
        logger.info("walk_forward_complete", windows=len(results))
        return results

    def _compute_window_metrics(self, trades: List[dict]) -> dict:
        """Compute metrics for a single Walk Forward window."""
        if not trades:
            return {"sharpe": 0, "profit_factor": 0, "drawdown": 0, "stability": 0, "trades": 0}

        profitable = [t for t in trades if t.get("pnl", 0) > 0]
        losing = [t for t in trades if t.get("pnl", 0) <= 0]

        total_profit = sum(t["pnl"] for t in profitable)
        total_loss = abs(sum(t["pnl"] for t in losing))

        # Sharpe (simplified)
        returns = [t["pnl"] for t in trades]
        mean_ret = np.mean(returns) if returns else 0
        std_ret = np.std(returns) if len(returns) > 1 else 1
        sharpe = mean_ret / std_ret if std_ret > 0 else 0

        # Profit Factor
        pf = total_profit / total_loss if total_loss > 0 else float("inf")

        # Drawdown
        cumulative = np.cumsum(returns)
        peak = np.maximum.accumulate(cumulative)
        dd = np.max(peak - cumulative) if len(cumulative) > 0 else 0

        return {
            "sharpe": round(float(sharpe), 4),
            "profit_factor": round(float(pf), 4) if pf != float("inf") else 100.0,
            "drawdown": round(float(dd), 4),
            "stability": 0.0,  # Computed across windows
            "trades": len(trades),
        }

    def multi_criteria_score(self, metrics: dict) -> float:
        """
        Compute composite score using the configured weights.

        score = 0.35*sharpe_norm + 0.25*pf_norm + 0.20*dd_norm + 0.20*stability_norm
        """
        w = self.config.score_weights

        # Normalize (simple min-max style, assume reasonable ranges)
        sharpe_norm = min(1.0, max(0.0, metrics.get("sharpe", 0) / 3.0))
        pf_norm = min(1.0, max(0.0, metrics.get("profit_factor", 0) / 2.0))
        dd_norm = 1.0 - min(1.0, max(0.0, metrics.get("drawdown", 0) / 0.2))
        stability_norm = metrics.get("stability", 0.0)

        score = (
            w["sharpe"] * sharpe_norm +
            w["profit_factor"] * pf_norm +
            w["drawdown"] * dd_norm +
            w["stability"] * stability_norm
        )
        return round(score, 4)

    def is_stable(self, min_windows: int = 3) -> bool:
        """
        Check if Walk Forward results show stability.
        Requires `min_windows` consecutive windows without significant degradation.
        """
        if len(self._walk_forward_results) < min_windows:
            return False

        # Check last N windows for stability
        recent = self._walk_forward_results[-min_windows:]
        scores = [self.multi_criteria_score(r.metrics) for r in recent]

        # Stability: no window has a score drop > 30% from the average
        avg_score = sum(scores) / len(scores) if scores else 0
        for s in scores:
            if avg_score > 0 and (avg_score - s) / avg_score > 0.30:
                return False

        return True

    def generate_candidate_config(
        self, base_config: dict, results: List[WalkForwardResult]
    ) -> dict:
        """
        Generate a candidate configuration based on Walk Forward results.
        Only during OFFLINE mode — not called during live trading.
        """
        if not results:
            return base_config

        # Find best-performing window parameters
        best_result = max(results, key=lambda r: self.multi_criteria_score(r.metrics))
        best_score = self.multi_criteria_score(best_result.metrics)

        # Check stability requirement
        stable = self.is_stable(self.config.min_windows)

        candidate = {
            **base_config,
            "candidate": {
                "score": best_score,
                "stable": stable,
                "best_window": best_result.window_index,
                "train_period": f"{best_result.train_start.date()} to {best_result.train_end.date()}",
                "test_period": f"{best_result.test_start.date()} to {best_result.test_end.date()}",
                "metrics": best_result.metrics,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

        return candidate
