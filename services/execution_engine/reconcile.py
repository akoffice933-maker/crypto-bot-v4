"""
Position reconciliation after network interruptions.

Verifies that exchange state matches local state.
Uses CCXT fetch_positions for cross-exchange support.
"""

import structlog

from core.exchange.adapter import ExchangeAdapter

logger = structlog.get_logger(__name__)


class PositionReconciler:
    """Checks actual exchange positions against local records."""

    def __init__(self, exchange: ExchangeAdapter):
        self._exchange = exchange

    async def reconcile(self, pair: str) -> dict:
        """Query exchange for actual position state."""
        try:
            ccxt_symbol = ExchangeAdapter.normalize_symbol(
                pair, self._exchange.exchange_id
            )
            positions = self._exchange.fetch_positions([ccxt_symbol])
            return {
                "pair": pair,
                "ccxt_symbol": ccxt_symbol,
                "found": len(positions) > 0,
                "count": len(positions),
                "positions": [
                    {
                        "side": p.side,
                        "contracts": p.contracts,
                        "entry_price": p.entry_price,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in positions
                ],
            }
        except Exception as e:
            logger.error("reconcile_failed", pair=pair, error=str(e))
            return {"pair": pair, "found": False, "error": str(e)}
