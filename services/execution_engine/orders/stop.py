"""
Stop-loss and take-profit order execution.
"""

import structlog

from core.exchange.adapter import ExchangeAdapter
from core.models import Direction, Position

logger = structlog.get_logger(__name__)


class StopOrderExecutor:
    """Executes stop-loss (stop-market) and take-profit (limit) orders."""

    def __init__(self, exchange: ExchangeAdapter):
        self._exchange = exchange

    def place_stop_loss(self, position: Position) -> bool:
        """Place a stop-market order for stop-loss."""
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                position.pair, self._exchange.exchange_id
            )
            side = "sell" if position.direction == Direction.LONG else "buy"
            self._exchange.create_stop_market_order(
                symbol=ccxt_symbol,
                side=side,
                amount=round(position.size, 6),
                stop_price=round(position.stop_loss, 2),
            )
            logger.info("sl_placed", pair=position.pair, stop=position.stop_loss)
            return True
        except Exception as e:
            logger.error("sl_failed", pair=position.pair, error=str(e))
            return False

    def place_take_profit(
        self, position: Position, tp_price: float, quantity: float
    ) -> bool:
        """Place a limit take-profit order."""
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                position.pair, self._exchange.exchange_id
            )
            side = "sell" if position.direction == Direction.LONG else "buy"
            self._exchange.create_limit_order(
                symbol=ccxt_symbol,
                side=side,
                amount=round(quantity, 6),
                price=round(tp_price, 2),
            )
            logger.info("tp_placed", pair=position.pair, tp=tp_price)
            return True
        except Exception as e:
            logger.error("tp_failed", pair=position.pair, error=str(e))
            return False
