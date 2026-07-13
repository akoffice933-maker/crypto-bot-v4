"""
Crypto Bot v4.4 — Analytics Service
Calculates trading metrics: Winrate, Profit Factor, Expectancy,
Sharpe Ratio, Calmar Ratio, Recovery Factor, MAE/MFE.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """
    Computes trading performance metrics from closed trade history.
    Supports real-time, hourly, daily, and weekly reporting.
    """

    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize analytics.

        Args:
            risk_free_rate: Annual risk-free rate (default 2% for crypto).
        """
        self.risk_free_rate = risk_free_rate
        self._trades: List[dict] = []
        self._hourly_snapshots: List[dict] = []

    def add_trade(self, trade: dict):
        """
        Add a closed trade to the analytics dataset.

        trade dict should have:
          - entry_price, exit_price, size
          - pnl, fees
          - is_win (bool)
          - timestamp (datetime)
          - strategy (str)
          - pair (str)
          - mae (float, optional) — Maximum Adverse Excursion
          - mfe (float, optional) — Maximum Favorable Excursion
        """
        self._trades.append(trade)

    def get_metrics(self, since: Optional[datetime] = None) -> dict:
        """
        Calculate all trading metrics, optionally filtered by time.

        Returns a dictionary of all metrics defined in the specification.
        """
        trades = self._trades
        if since:
            trades = [t for t in trades if t["timestamp"] >= since]

        if not trades:
            return self._empty_metrics()

        profitable = [t for t in trades if t.get("is_win", t.get("pnl", 0) > 0)]
        losing = [t for t in trades if not t.get("is_win", t.get("pnl", 0) > 0)]

        n_total = len(trades)
        n_wins = len(profitable)
        n_losses = len(losing)

        # Winrate
        winrate = n_wins / n_total if n_total > 0 else 0.0

        # Total PnL
        total_profit = sum(t["pnl"] for t in profitable)
        total_loss = abs(sum(t["pnl"] for t in losing))

        # Profit Factor
        profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        # Expectancy (average profit per trade)
        total_pnl = sum(t["pnl"] for t in trades)
        expectancy = total_pnl / n_total if n_total > 0 else 0.0

        # Average win / average loss
        avg_win = total_profit / n_wins if n_wins > 0 else 0.0
        avg_loss = total_loss / n_losses if n_losses > 0 else 0.0

        # Total fees
        total_fees = sum(t.get("fees", 0) for t in trades)

        # Returns series (for Sharpe, Calmar)
        returns = [t["pnl"] for t in trades]
        returns_pct = []  # percentage returns for each trade
        for t in trades:
            notional = t.get("entry_price", 0) * t.get("size", 0)
            if notional > 0:
                returns_pct.append(t["pnl"] / notional)

        # Sharpe Ratio (annualized)
        sharpe = self._calculate_sharpe(returns_pct)

        # Calmar Ratio (annualized return / max drawdown)
        calmar = self._calculate_calmar(returns_pct)

        # Recovery Factor
        recovery_factor = total_pnl / self._max_drawdown(returns_pct) if self._max_drawdown(returns_pct) > 0 else float("inf")

        # Average MAE/MFE
        maes = [t.get("mae", 0) for t in trades if "mae" in t]
        mfes = [t.get("mfe", 0) for t in trades if "mfe" in t]
        avg_mae = sum(maes) / len(maes) if maes else 0.0
        avg_mfe = sum(mfes) / len(mfes) if mfes else 0.0

        # Slippage
        slippages = [t.get("slippage", 0) for t in trades if "slippage" in t]
        avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0

        # Per-strategy breakdown
        strategy_metrics = {}
        strategies = set(t.get("strategy", "unknown") for t in trades)
        for strat in strategies:
            strat_trades = [t for t in trades if t.get("strategy") == strat]
            strat_profitable = [t for t in strat_trades if t.get("is_win", t.get("pnl", 0) > 0)]
            strat_losing = [t for t in strat_trades if not t.get("is_win", t.get("pnl", 0) > 0)]
            strat_total_pnl = sum(t["pnl"] for t in strat_trades)
            strategy_metrics[strat] = {
                "count": len(strat_trades),
                "winrate": len(strat_profitable) / len(strat_trades) if strat_trades else 0,
                "total_pnl": strat_total_pnl,
                "profit_factor": (
                    sum(t["pnl"] for t in strat_profitable) / abs(sum(t["pnl"] for t in strat_losing))
                    if strat_losing else float("inf")
                ),
            }

        return {
            "total_trades": n_total,
            "wins": n_wins,
            "losses": n_losses,
            "winrate": round(winrate, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
            "expectancy": round(expectancy, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "total_pnl": round(total_pnl, 4),
            "total_fees": round(total_fees, 4),
            "sharpe_ratio": round(sharpe, 4),
            "calmar_ratio": round(calmar, 4),
            "recovery_factor": round(recovery_factor, 4) if recovery_factor != float("inf") else "inf",
            "avg_mae": round(avg_mae, 4),
            "avg_mfe": round(avg_mfe, 4),
            "avg_slippage": round(avg_slippage, 8),
            "max_drawdown": round(self._max_drawdown(returns_pct), 4),
            "strategy_breakdown": strategy_metrics,
            "period_start": trades[0]["timestamp"].isoformat() if trades else None,
            "period_end": trades[-1]["timestamp"].isoformat() if trades else None,
        }

    def get_snapshot_metrics(self, hours_back: int = 1) -> dict:
        """Get metrics for the last N hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        return self.get_metrics(since=since)

    def get_daily_report(self) -> dict:
        """Get daily metrics report."""
        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_metrics(since=since)

    # ------- Calculation Helpers -------

    def _calculate_sharpe(self, returns_pct: List[float]) -> float:
        """Calculate annualized Sharpe Ratio."""
        if len(returns_pct) < 2:
            return 0.0

        mean_ret = sum(returns_pct) / len(returns_pct)
        if mean_ret == 0:
            return 0.0

        variance = sum((r - mean_ret) ** 2 for r in returns_pct) / (len(returns_pct) - 1)
        std_ret = math.sqrt(variance) if variance > 0 else 0

        if std_ret == 0:
            return 0.0

        # Annualize (assume ~365 trades per year)
        sharpe = (mean_ret - self.risk_free_rate / 365) / std_ret * math.sqrt(365)
        return sharpe

    def _calculate_calmar(self, returns_pct: List[float]) -> float:
        """Calculate Calmar Ratio."""
        if not returns_pct:
            return 0.0
        total_return = sum(returns_pct)
        max_dd = self._max_drawdown(returns_pct)
        if max_dd == 0:
            return 0.0
        return total_return / max_dd

    def _max_drawdown(self, returns_pct: List[float]) -> float:
        """Calculate maximum drawdown from a stream of percentage returns."""
        if not returns_pct:
            return 0.0
        cumulative = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in returns_pct:
            cumulative *= (1 + r)
            peak = max(peak, cumulative)
            dd = (peak - cumulative) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def _empty_metrics(self) -> dict:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "winrate": 0, "profit_factor": 0,
            "expectancy": 0, "avg_win": 0, "avg_loss": 0,
            "total_pnl": 0, "total_fees": 0,
            "sharpe_ratio": 0, "calmar_ratio": 0,
            "recovery_factor": 0,
            "avg_mae": 0, "avg_mfe": 0, "avg_slippage": 0,
            "max_drawdown": 0, "strategy_breakdown": {},
            "period_start": None, "period_end": None,
        }
