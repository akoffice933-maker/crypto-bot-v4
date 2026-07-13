# Crypto Bot v4.4 — Deployment Guide

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (for production)
- Binance Futures API key (or testnet)

## Quick Start (Development)

```bash
# Clone and install
cd crypto_bot_v4
pip install -r requirements.txt

# Initialize database
python -c "from core.database.db_manager import DatabaseManager; db = DatabaseManager(); db.connect(); db.create_all()"

# Run bot
python main.py
```

## Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Check status
curl http://localhost:8000/health
```

## Configuration

1. Copy `config/config_v4.4.1.yaml` to customize
2. Set environment variables:
   - `BINANCE_API_KEY`
   - `BINANCE_API_SECRET`
   - `BINANCE_TESTNET=true` (for testnet)
   - `DATABASE_URL` (for PostgreSQL)

## PostgreSQL Setup (Production)

```bash
docker run -d --name pg-crypto \
  -e POSTGRES_USER=crypto \
  -e POSTGRES_PASSWORD=secure_password \
  -e POSTGRES_DB=crypto_bot \
  -p 5432:5432 \
  postgres:15

# Then set: DATABASE_URL=postgresql://crypto:secure_password@localhost:5432/crypto_bot
```

## Monitoring

Access Grafana at `http://localhost:3000` (default credentials: admin/admin).
Prometheus scrapes metrics at `http://localhost:9090`.
