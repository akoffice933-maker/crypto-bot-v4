# Crypto Bot v5.0 — Web Panel

React 19 + TypeScript + Vite dashboard for the Crypto Bot trading platform.

## Quick Start

```bash
cd web
npm install
npm run dev       # dev server at http://localhost:5173
npm run build     # production build → dist/
```

The dev server proxies API requests to `localhost:8000` (the FastAPI backend).

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Metric cards, equity chart, positions |
| `/positions` | Positions | Full table, close actions |
| `/trades` | Trades | History with filters and summary |
| `/strategies` | Strategies | Sweep/Bounce/Breakout cards |
| `/risk` | Risk | Drawdown bars, stop multipliers |
| `/analytics` | Analytics | KPIs, strategy breakdown |
| `/tradingview` | TradingView | Webhook URL, PineScript templates, social |
| `/config` | Config | YAML editor, environments |
| `/monitor` | Monitor | System metrics, uptime |
| `/logs` | Logs | Real-time stream with filters |
| `/settings` | Settings | Bot control, exchange, notifications |

## Stack

- **UI**: React 19, Tailwind CSS, Lucide Icons
- **State**: Zustand
- **Data**: TanStack Query (REST), WebSocket hook
- **Charts**: Recharts
- **Routing**: React Router v7
- **Build**: Vite + TypeScript

## Architecture

```
src/
├── api/client.ts           # axios instance + fetch helpers
├── hooks/useWebSocket.ts    # WS auto-reconnect hook
├── store/appStore.ts        # Zustand global state
├── types/api.ts             # All API types
├── components/
│   ├── layout/              # Sidebar, Layout
│   ├── charts/              # EquityChart, PnLChart
│   └── ui/                  # MetricCard
├── pages/                   # 11 page components
└── lib/utils.ts             # cn(), formatters
```
