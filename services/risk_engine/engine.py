"""
Crypto Bot v4.4 — Risk Engine
Evaluates signals, determines position size, enforces risk limits,
manages Recovery Mode, and controls drawdown.
"""

import math
import copy
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog

from core.models import (
    Direction, PortfolioState, Position, RiskDecision, Signal,
    StrategyType,
)
from core.events.event_store import Event, EventStore, EventType

logger = structlog.get_logger(__name__)


class RiskEngine:
    """
    Evaluates trade signals against risk parameters and makes
    position-sizing decisions. Manages Recovery Mode and drawdown limits.
    """

    # Risk per trade by deposit tier
    RISK_PER_TRADE = {
        (0, 1000): 0.015,
        (1000, 5000): 0.015,
        (5000, 10000): 0.015,
        (10000, float("inf")): 0.015,
    }

    MAX_RISK_SMALL = 0.02   # 2% for deposits < $1000

    # Stop-loss multiplier by volatility regime (class defaults, copied per instance)
    _STOP_MULTIPLIER_DEFAULTS = {
        "ultra_quiet": 0.8,
        "quiet": 1.0,
        "normal": 1.2,
        "volatile": 1.5,
    }

    # Drawdown limits (class defaults; key "total" matches PortfolioState.total_drawdown)
    _DRAWDOWN_LIMITS_DEFAULTS = {
        "daily": 2.0,
        "weekly": 5.0,
        "monthly": 10.0,
        "total": 15.0,
    }

    # Recovery mode
    RECOVERY_THRESHOLD = 8.0    # % drawdown to enter
    RECOVERY_EXIT = 5.0         # % drawdown to exit
    RECOVERY_MIN_WINS = 3       # consecutive wins to exit

    def __init__(
        self,
        balance: float,
        event_store: Optional[EventStore] = None,
        config: Optional[dict] = None,
    ):
        self.balance = balance
        self.peak_balance = balance
        self.event_store = event_store or EventStore()
        self._recovery_mode = False
        self._consecutive_wins = 0
        self._open_positions: Dict[str, Position] = {}
        self._daily_pnl: Dict[str, float] = {}    # date -> pnl
        self._weekly_pnl: Dict[str, float] = {}    # iso-week -> pnl
        self._monthly_pnl: Dict[str, float] = {}   # YYYY-MM -> pnl
        self._closed_trades: List[dict] = []

        # Per-instance copies to prevent class-level mutation
        self.stop_multiplier = dict(self._STOP_MULTIPLIER_DEFAULTS)
        self.drawdown_limits = dict(self._DRAWDOWN_LIMITS_DEFAULTS)

        # Apply config overrides
        if config:
            if "stop_multiplier" in config:
                self.stop_multiplier.update(config["stop_multiplier"])
            if "drawdown_limits" in config:
                self.drawdown_limits.update(config["drawdown_limits"])
            if "recovery_threshold" in config:
                self.RECOVERY_THRESHOLD = config["recovery_threshold"]
            if "recovery_exit_threshold" in config:
                self.RECOVERY_EXIT = config["recovery_exit_threshold"]
            if "recovery_min_wins" in config:
                self.RECOVERY_MIN_WINS = config["recovery_min_wins"]

    def evaluate_signal(
        self,
        signal: Signal,
        portfolio: PortfolioState,
        current_volatility: str = "normal",
    ) -> RiskDecision:
        """
        Evaluate a trading signal and return a risk decision.

        Args:
            signal: The trading signal to evaluate
            portfolio: Current portfolio state
            current_volatility: Volatility regime ('ultra_quiet', 'quiet', 'normal', 'volatile')

        Returns:
            RiskDecision with approved/denied, position size, stop, RR
        """
        reasons = []

        # ---- Check Recovery Mode ----
        if self._recovery_mode:
            reasons.append("Recovery mode active — halved risk")

        # ---- Check open positions limit ----
        if portfolio.open_positions >= 3:  # max 3 positions
            return RiskDecision(
                approved=False,
                position_size=0,
                stop_loss=signal.stop_loss,
                stop_multiplier=self.stop_multiplier.get(current_volatility, 1.0),
                rr_ratio=0,
                reason="Max positions (3) reached",
                recovery_mode=self._recovery_mode,
            )

        # ---- Check total exposure ----
        if abs(portfolio.total_exposure) >= 3.0:
            return RiskDecision(
                approved=False,
                position_size=0,
                stop_loss=signal.stop_loss,
                stop_multiplier=self.stop_multiplier.get(current_volatility, 1.0),
                rr_ratio=0,
                reason=f"Total exposure {portfolio.total_exposure} exceeds limit 3.0",
                recovery_mode=self._recovery_mode,
            )

        # ---- Check drawdown limits ----
        for limit_name, limit_val in self.drawdown_limits.items():
            current_dd = getattr(portfolio, f"{limit_name}_drawdown", 0)
            if current_dd >= limit_val:
                return RiskDecision(
                    approved=False,
                    position_size=0,
                    stop_loss=signal.stop_loss,
                    stop_multiplier=self.stop_multiplier.get(current_volatility, 1.0),
                    rr_ratio=0,
                    reason=f"{limit_name} drawdown {current_dd:.1f}% exceeds limit {limit_val}%",
                    recovery_mode=self._recovery_mode,
                )

        # ---- Position sizing ----
        base_risk = self._get_risk_per_trade()
        if self._recovery_mode:
            base_risk /= 2.0  # Halved risk in recovery

        # Adaptive stop-loss multiplier — applied to DISTANCE, not raw price
        stop_mult = self.stop_multiplier.get(current_volatility, 1.0)

        # Compute risk distance correctly: multiplier scales the distance
        risk_distance = abs(signal.entry_market - signal.stop_loss)
        adjusted_distance = risk_distance * stop_mult

        if signal.direction == Direction.LONG:
            adjusted_stop = signal.entry_market - adjusted_distance
        else:
            adjusted_stop = signal.entry_market + adjusted_distance

        price_diff = abs(signal.entry_market - adjusted_stop)

        if price_diff <= 0:
            return RiskDecision(
                approved=False,
                position_size=0,
                stop_loss=adjusted_stop,
                stop_multiplier=stop_mult,
                rr_ratio=0,
                reason="Stop distance is zero or negative",
                recovery_mode=self._recovery_mode,
            )

        account_risk_amount = self.balance * base_risk
        position_size = account_risk_amount / price_diff

        # Cap position size at reasonable limits
        max_position = self.balance * 0.95 / signal.entry_market  # Don't use >95% of account
        position_size = min(position_size, max_position)

        # ---- Adaptive RR ----
        level_distance = abs(signal.entry_market - adjusted_stop) / signal.entry_market * 100
        if level_distance < 0.3:
            target_rr = 1.5 + 0.5 * (level_distance / 0.3)
        elif level_distance < 0.8:
            target_rr = 2.0 + 1.0 * ((level_distance - 0.3) / 0.5)
        else:
            target_rr = 3.0 + 2.0 * min(1.0, (level_distance - 0.8) / 1.0)

        # Confidence filter
        if signal.confidence < 0.5:
            reasons.append(f"Low confidence: {signal.confidence:.2f}")

        if reasons:
            logger.info("risk_warning", signal=str(signal.strategy.value), reasons=reasons)

        return RiskDecision(
            approved=True,
            position_size=round(position_size, 6),
            stop_loss=round(adjusted_stop, 2),
            stop_multiplier=stop_mult,
            rr_ratio=round(target_rr, 2),
            reason="; ".join(reasons) if reasons else "Approved",
            recovery_mode=self._recovery_mode,
        )

    def _get_risk_per_trade(self) -> float:
        """Get risk per trade based on deposit amount."""
        if self.balance < 1000:
            return self.MAX_RISK_SMALL
        for (low, high), risk in self.RISK_PER_TRADE.items():
            if low <= self.balance < high:
                return risk
        return 0.015  # default

    def update_balance(self, new_balance: float):
        """Update account balance and track drawdown."""
        self.balance = new_balance
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance

    def record_trade_result(self, pnl: float, is_win: bool):
        """
        Record a closed trade result.
        Updates recovery mode state.
        """
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        week = now.strftime("%G-W%V")
        month = now.strftime("%Y-%m")

        self._daily_pnl[today] = self._daily_pnl.get(today, 0) + pnl
        self._weekly_pnl[week] = self._weekly_pnl.get(week, 0) + pnl
        self._monthly_pnl[month] = self._monthly_pnl.get(month, 0) + pnl

        self._closed_trades.append({
            "pnl": pnl, "is_win": is_win, "date": today,
            "timestamp": now,
        })

        # Update recovery mode
        current_drawdown = self._calculate_drawdown()

        if not self._recovery_mode and current_drawdown > self.RECOVERY_THRESHOLD:
            self._enter_recovery()
        elif self._recovery_mode:
            if is_win:
                self._consecutive_wins += 1
            else:
                self._consecutive_wins = 0

            if current_drawdown < self.RECOVERY_EXIT and self._consecutive_wins >= self.RECOVERY_MIN_WINS:
                self._exit_recovery()

    def _enter_recovery(self):
        """Enter recovery mode."""
        self._recovery_mode = True
        self._consecutive_wins = 0
        if self.event_store:
            self.event_store.append(EventType.RECOVERY_ENTERED, {
                "drawdown": self._calculate_drawdown(),
                "balance": self.balance,
            })
        logger.warning("recovery_mode_entered", drawdown=self._calculate_drawdown())

    def _exit_recovery(self):
        """Exit recovery mode."""
        self._recovery_mode = False
        if self.event_store:
            self.event_store.append(EventType.RECOVERY_EXITED, {
                "drawdown": self._calculate_drawdown(),
                "balance": self.balance,
            })
        logger.info("recovery_mode_exited", drawdown=self._calculate_drawdown())

    def _calculate_drawdown(self) -> float:
        """Calculate current drawdown percentage."""
        if self.peak_balance <= 0:
            return 0.0
        return (1 - self.balance / self.peak_balance) * 100

    @property
    def recovery_mode(self) -> bool:
        return self._recovery_mode

    def get_daily_pnl(self) -> float:
        """Get today's PnL."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._daily_pnl.get(today, 0.0)

    def get_portfolio_state(self) -> PortfolioState:
        """Build current portfolio state snapshot."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        week = now.strftime("%G-W%V")
        month = now.strftime("%Y-%m")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        daily_pnl = self._daily_pnl.get(today, 0.0)
        weekly_pnl = sum(
            pnl for dt, pnl in self._daily_pnl.items() if dt >= week_ago
        )
        monthly_pnl = sum(
            pnl for dt, pnl in self._daily_pnl.items() if dt >= month_ago
        )
        current_dd = self._calculate_drawdown()

        return PortfolioState(
            balance=self.balance,
            equity=self.balance + sum(p.current_pnl for p in self._open_positions.values()),
            open_positions=len(self._open_positions),
            total_exposure=sum(p.size * p.entry_price for p in self._open_positions.values()) / self.balance * 100 if self.balance > 0 else 0,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            monthly_pnl=monthly_pnl,
            daily_drawdown=current_dd,
            weekly_drawdown=current_dd,
            monthly_drawdown=current_dd,
            total_drawdown=current_dd,
            recovery_mode=self._recovery_mode,
        )
