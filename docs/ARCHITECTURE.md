# Crypto Bot v4.4 — Architecture

## Overview

Crypto Bot v4.4 is an algorithmic trading platform for Binance Futures built on a service-oriented architecture. Trading and learning are strictly separated (Online/Offline), and all configurations are versioned and immutable at runtime.

## Services

| Service | Purpose |
|---------|---------|
| **Data Service** | Fetch/store OHLCV, OI, funding rates from Binance |
| **Data Validator** | Validate data quality before trading |
| **Feature Service** | Compute ADX, ATR%, BB, volume, CVD, liquidity levels |
| **Regime Detector** | Classify market regime (trend/range × vol + breakout) |
| **Strategy Engine** | Generate Sweep/Bounce/Breakout signals |
| **Risk Engine** | Position sizing, drawdown limits, Recovery Mode |
| **Execution Engine** | Order placement, retry logic, circuit breaker |
| **Portfolio Engine** | Position tracking, PnL, event sourcing |
| **Analytics Service** | Winrate, Sharpe, Calmar, Profit Factor |
| **Learning Service** | Walk Forward, Bayesian update, multi-criteria scoring |
| **Config Registry** | Immutable, versioned configuration |
| **Health Monitor** | System health, engineering metrics |

## Data Flow

```
Binance API → Data Service → Data Validator → Market DB
                                              ↓
                    Feature Service ← Market DB
                         ↓
                    Regime Detector
                         ↓
                    Strategy Engine → Signals
                         ↓
                    Risk Engine → Decision
                         ↓
                    Execution Engine → Binance
                         ↓
                    Portfolio Engine

Learning (Offline):
  Market DB → Walk Forward → Multi-criteria Score → Candidate Config
```

## Online vs Offline

- **Online**: Trade execution, statistics collection only. Parameters are NEVER changed.
- **Offline**: Walk Forward analysis, config candidate generation, validation.

## Technology Stack

| Layer | Tech |
|-------|------|
| Runtime | Python 3.10+ |
| DB | SQLite (dev) / PostgreSQL (prod) |
| Cache | Redis |
| Orchestration | Docker Compose |
| Monitoring | Prometheus + Grafana |
| API | FastAPI |
