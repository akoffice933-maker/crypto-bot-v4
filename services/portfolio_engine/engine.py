"""
Crypto Bot v4.4 — Portfolio Engine
Manages positions, tracks PnL, auto-updates stops, event sourcing.
"""

from datetime import datetime, timezone, timezone
from typing import Dict, List, Optional

import structlog

from core.models import Direction, Position, Trade
from core.events.event_store import EventStore, EventType

logger = structlog.get_logger(__name__)


class PortfolioEngine:
    """
    Tracks all open positions, calculates PnL, and manages position lifecycle.
    Uses Event Sourcing for state reconstruction.
    """

    MAX_POSITIONS = 3
    MAX_CORRELATION = 0.7

    def __init__(self, event_store: Optional[EventStore] = None):
        self._positions: Dict[str, Position] = {}  # pair -> Position
        self._trade_history: List[Trade] = []
        self.event_store = event_store or EventStore()

        # Subscribe to events
        self.event_store.subscribe(EventType.POSITION_CREATED, self._on_position_created)
        self.event_store.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)
        self.event_store.subscribe(EventType.STOP_MOVED, self._on_stop_moved)

    # ------- Event Handlers -------
    def _on_position_created(self, event):
        data = event.data
        pos = Position(
            pair=data["pair"],
            direction=Direction(data["direction"]),
            entry_price=data["entry_price"],
            size=data["size"],
            stop_loss=data["stop_loss"],
            tp1=data["tp1"],
            tp2=data["tp2"],
            strategy=data.get("strategy", "sweep"),
            opened_at=event.timestamp,
        )
        self._positions[data["pair"]] = pos
        logger.info("position_created", pair=data["pair"], direction=data["direction"])

    def _on_position_closed(self, event):
        data = event.data
        pair = data["pair"]
        if pair in self._positions:
            del self._positions[pair]
        logger.info("position_closed", pair=pair)

    def _on_stop_moved(self, event):
        data = event.data
        pair = data["pair"]
        if pair in self._positions:
            self._positions[pair].stop_loss = data["new_stop"]
            logger.info("stop_moved", pair=pair, new_stop=data["new_stop"])

    # ------- Position Management -------
    def open_position(
        self,
        pair: str,
        direction: Direction,
        entry_price: float,
        size: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        strategy: str = "sweep",
    ) -> Position:
        """Open a new position and emit event."""
        if len(self._positions) >= self.MAX_POSITIONS:
            raise ValueError(f"Maximum {self.MAX_POSITIONS} positions already open")

        position = Position(
            pair=pair,
            direction=direction,
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            strategy=strategy,
            opened_at=datetime.now(timezone.utc),
        )
        self._positions[pair] = position

        self.event_store.append(EventType.POSITION_CREATED, {
            "pair": pair,
            "direction": direction.value,
            "entry_price": entry_price,
            "size": size,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "strategy": strategy,
        })

        return position

    def close_position(self, pair: str, exit_price: float, pnl: float) -> Optional[Position]:
        """Close a position and emit event. Returns the closed position."""
        if pair not in self._positions:
            logger.warning("close_nonexistent_position", pair=pair)
            return None

        position = self._positions.pop(pair)
        self.event_store.append(EventType.POSITION_CLOSED, {
            "pair": pair,
            "exit_price": exit_price,
            "pnl": pnl,
            "entry_price": position.entry_price,
            "size": position.size,
        })

        return position

    def update_stop_loss(self, pair: str, new_stop: float) -> bool:
        """Move stop-loss (e.g., to breakeven or trailing)."""
        if pair not in self._positions:
            return False

        old_stop = self._positions[pair].stop_loss
        self._positions[pair].stop_loss = new_stop

        self.event_store.append(EventType.STOP_MOVED, {
            "pair": pair,
            "old_stop": old_stop,
            "new_stop": new_stop,
        })

        return True

    def update_pnl(self, current_prices: Dict[str, float]):
        """Update unrealized PnL for all open positions."""
        for pair, position in self._positions.items():
            if pair not in current_prices:
                continue
            price = current_prices[pair]
            if position.direction == Direction.LONG:
                position.current_pnl = (price - position.entry_price) * position.size
            else:
                position.current_pnl = (position.entry_price - price) * position.size

    def get_position(self, pair: str) -> Optional[Position]:
        return self._positions.get(pair)

    @property
    def open_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    @property
    def position_count(self) -> int:
        return len(self._positions)

    def get_total_unrealized_pnl(self) -> float:
        return sum(p.current_pnl for p in self._positions.values())

    def get_directional_exposure(self) -> float:
        """Calculate net directional exposure (long - short)."""
        long_val = sum(
            p.size * p.entry_price for p in self._positions.values()
            if p.direction == Direction.LONG
        )
        short_val = sum(
            p.size * p.entry_price for p in self._positions.values()
            if p.direction == Direction.SHORT
        )
        return long_val - short_val

    def check_correlation(self, candidate_pair: str) -> float:
        """
        Approximate correlation between candidate and existing positions.
        Simplified: returns 0 for different pairs, 0.5 for similar caps.
        In production, use rolling correlation of returns.
        """
        # Very simplified — in production, compute actual correlation
        large_caps = {"BTCUSDT", "ETHUSDT"}
        alt_coins = {"SOLUSDT", "BNBUSDT"}

        max_corr = 0.0
        for pair in self._positions:
            if pair == candidate_pair:
                return 1.0
            if pair in large_caps and candidate_pair in large_caps:
                max_corr = max(max_corr, 0.6)
            elif pair in alt_coins and candidate_pair in alt_coins:
                max_corr = max(max_corr, 0.5)
            elif (pair in large_caps and candidate_pair in alt_coins) or (pair in alt_coins and candidate_pair in large_caps):
                max_corr = max(max_corr, 0.4)
            else:
                max_corr = max(max_corr, 0.3)
        return max_corr

    def reconstruct_state(self) -> Dict:
        """Reconstruct full portfolio state from event log (Event Sourcing)."""
        events = self.event_store.replay()
        positions = {}
        trade_history = []

        for event in events:
            if event.type == EventType.POSITION_CREATED:
                d = event.data
                positions[d["pair"]] = {
                    "pair": d["pair"],
                    "direction": d["direction"],
                    "entry_price": d["entry_price"],
                    "size": d["size"],
                    "stop_loss": d["stop_loss"],
                }
            elif event.type == EventType.STOP_MOVED and event.data["pair"] in positions:
                positions[event.data["pair"]]["stop_loss"] = event.data["new_stop"]
            elif event.type == EventType.POSITION_CLOSED:
                if event.data["pair"] in positions:
                    trade_history.append({
                        "pair": event.data["pair"],
                        "pnl": event.data["pnl"],
                    })
                    del positions[event.data["pair"]]

        return {"positions": positions, "trade_history": trade_history}
