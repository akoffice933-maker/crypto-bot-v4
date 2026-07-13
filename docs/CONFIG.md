# Crypto Bot v4.4 — Configuration Reference

## Config File Structure

See `config/config_v4.4.1.yaml` for the full example.

### Data Section

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pairs` | list | [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT] | Trading pairs |
| `timeframes` | list | [15m, 1h, 4h, 1d] | Timeframes to use |
| `lookback_days` | int | 90 | Days of historical data to keep |

### Strategy Section

#### Sweep
| Parameter | Default | Description |
|-----------|---------|-------------|
| `wick_ratio` | 1.8 | Minimum wick-to-body ratio |
| `volume_multiplier` | 1.25 | Volume confirmation threshold |
| `tolerance` | 0.0018 | Level proximity tolerance |
| `min_rr` | 2.0 | Minimum risk/reward ratio |

#### Bounce
| Parameter | Default | Description |
|-----------|---------|-------------|
| `wick_ratio` | 1.5 | Minimum wick-to-body ratio |
| `volume_multiplier` | 1.10 | Volume confirmation threshold |
| `tolerance` | 0.0018 | Level proximity tolerance |
| `min_rr` | 1.5 | Minimum risk/reward ratio |

#### Breakout
| Parameter | Default | Description |
|-----------|---------|-------------|
| `sl_atr_mult` | 1.5 | Stop-loss ATR multiplier |
| `tp_min` | 0.02 | Minimum take profit (2%) |
| `tp_max` | 0.04 | Maximum take profit (4%) |

### Risk Section

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_risk_per_trade` | 0.015 | 1.5% risk per trade |
| `max_positions` | 3 | Max concurrent positions |
| `max_correlation` | 0.7 | Max position correlation |
| `max_exposure` | 3.0 | Max total exposure % |
| `recovery.threshold` | 8.0 | % drawdown to enter recovery |
| `recovery.exit_threshold` | 5.0 | % drawdown to exit recovery |
| `recovery.min_wins` | 3 | Consecutive wins to exit |

### Stop Multipliers

| Regime | Multiplier |
|--------|-----------|
| `ultra_quiet` | 0.8 |
| `quiet` | 1.0 |
| `normal` | 1.2 |
| `volatile` | 1.5 |

### Drawdown Limits

| Limit | % |
|-------|---|
| `daily` | 2.0 |
| `weekly` | 5.0 |
| `monthly` | 10.0 |
| `max_total` | 15.0 |

### Learning Section

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_trades` | 100 | Minimum trades for Walk Forward |
| `min_windows` | 3 | Minimum stable windows |
| `train_period` | 6 | Training period (months) |
| `test_period` | 1 | Test period (months) |
| `step` | 1 | Step size (months) |
| `score_weights.sharpe` | 0.35 | Weight for Sharpe in scoring |
| `score_weights.profit_factor` | 0.25 | Weight for Profit Factor |
| `score_weights.drawdown` | 0.20 | Weight for Drawdown |
| `score_weights.stability` | 0.20 | Weight for Stability |
