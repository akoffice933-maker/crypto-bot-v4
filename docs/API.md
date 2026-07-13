# Crypto Bot v4.4 — API Reference (FastAPI Monitoring)

## Health Check

```
GET /health
```
Returns system health status.

```
GET /health/status
```
Returns detailed health metrics.

## Portfolio

```
GET /portfolio
```
Returns current portfolio state:
- balance, equity, open positions, PnL, drawdown

## Analytics

```
GET /analytics/metrics
```
Full trading metrics.

```
GET /analytics/daily
```
Daily report.

## Config

```
GET /config/current
```
Current active configuration.

```
GET /config/versions
```
Version history.

## Learning

```
GET /learning/status
```
Current learning metrics — Bayesian winrates, EWMA expected return.

## Execution

```
GET /execution/quality
```
Execution quality metrics — slippage, latency, fill rate.

## Prometheus Metrics

```
GET /metrics
```
Prometheus-compatible metrics endpoint.
