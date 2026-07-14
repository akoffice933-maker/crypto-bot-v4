"""
Stop-loss and take-profit order execution.

FIXED (v5.1.2): Cancels previous stop/take-profit orders before
placing new ones — prevents double-closing when SL is moved via UI.
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
        """Place a stop-market order. Cancels the old one first if present."""
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                position.pair, self._exchange.exchange_id
            )

            # Cancel old stop order on exchange BEFORE placing new
            if position.stop_order_id:
                try:
                    self._exchange.cancel_order(position.stop_order_id, ccxt_symbol)
                    logger.info("sl_cancelled", pair=position.pair, old_id=position.stop_order_id)
                except Exception:
                    logger.debug("sl_cancel_ignored", pair=position.pair, id=position.stop_order_id)

            side = "sell" if position.direction == Direction.LONG else "buy"
            order = self._exchange.create_stop_market_order(
                symbol=ccxt_symbol, side=side,
                amount=round(position.size, 6),
                stop_price=round(position.stop_loss, 2),
            )

            position.stop_order_id = str(order.id) if order and order.id else None
            logger.info("sl_placed", pair=position.pair, stop=position.stop_loss, id=position.stop_order_id)
            return True
        except Exception as e:
            logger.error("sl_failed", pair=position.pair, error=str(e))
            return False

    def place_take_profit(
        self, position: Position, tp_price: float, quantity: float, tp_index: int = 1
    ) -> bool:
        """Place a limit take-profit order. Cancels old one first."""
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                position.pair, self._exchange.exchange_id
            )

            old_tp_id = position.tp1_order_id if tp_index == 1 else position.tp2_order_id
            if old_tp_id:
                try:
                    self._exchange.cancel_order(old_tp_id, ccxt_symbol)
                    logger.info("tp_cancelled", pair=position.pair, old_id=old_tp_id, index=tp_index)
                except Exception:
                    logger.debug("tp_cancel_ignored", pair=position.pair, id=old_tp_id)

            side = "sell" if position.direction == Direction.LONG else "buy"
            order = self._exchange.create_limit_order(
                symbol=ccxt_symbol, side=side,
                amount=round(quantity, 6), price=round(tp_price, 2),
            )

            if tp_index == 1:
                position.tp1_order_id = str(order.id) if order and order.id else None
            else:
                position.tp2_order_id = str(order.id) if order and order.id else None

            logger.info("tp_placed", pair=position.pair, tp=tp_price, index=tp_index,
                       id=str(order.id) if order and order.id else None)
            return True
        except Exception as e:
            logger.error("tp_failed", pair=position.pair, error=str(e))
            return False
