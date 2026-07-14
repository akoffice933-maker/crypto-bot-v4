import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import { MetricCard } from "../components/ui/MetricCard";
import { EquityChart } from "../components/charts/EquityChart";
import type { PortfolioState, HealthStatus } from "../types/api";

export default function DashboardPage() {
  const [timeframe, setTimeframe] = useState<"1d" | "1w" | "1m">("1d");

  const { data: portfolio, isLoading } = useQuery<PortfolioState>({
    queryKey: ["portfolio"],
    queryFn: () => fetchJSON("/portfolio"),
    refetchInterval: 5000,
  });

  const { data: health } = useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: () => fetchJSON("/health"),
    refetchInterval: 10000,
  });

  if (isLoading) return <Skeleton />;

  const statusColor =
    health?.status === "healthy" ? "green" : health?.status === "warning" ? "yellow" : "red";

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-${statusColor}-500/10 text-${statusColor}-400`}
          >
            <span className={`w-1.5 h-1.5 rounded-full bg-${statusColor}-400`} />
            {health?.status ?? "unknown"}
          </span>
          {["1d", "1w", "1m"].map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf as "1d" | "1w" | "1m")}
              className={`px-2 py-1 text-xs rounded ${
                timeframe === tf ? "bg-blue-600 text-white" : "bg-white/5 text-gray-400 hover:text-gray-200"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Balance" value={`$${(portfolio?.balance ?? 0).toLocaleString()}`} color="blue" />
        <MetricCard label="Equity" value={`$${(portfolio?.equity ?? 0).toLocaleString()}`} color="green" />
        <MetricCard
          label="Day PnL"
          value={`$${Math.abs(portfolio?.daily_pnl ?? 0).toLocaleString()}`}
          change={portfolio?.balance ? (portfolio.daily_pnl / portfolio.balance) * 100 : 0}
          color={(portfolio?.daily_pnl ?? 0) >= 0 ? "green" : "red"}
        />
        <MetricCard
          label="Positions"
          value={portfolio?.open_positions_count ?? 0}
          color="blue"
        />
        <MetricCard
          label="Drawdown"
          value={`${(portfolio?.total_drawdown_pct ?? 0).toFixed(1)}%`}
          color={(portfolio?.total_drawdown_pct ?? 0) > 5 ? "red" : "yellow"}
        />
        <MetricCard
          label="Recovery"
          value={portfolio?.recovery_mode ? "ACTIVE" : "Normal"}
          color={portfolio?.recovery_mode ? "red" : "green"}
        />
        <MetricCard
          label="CPU"
          value={`${(health?.cpu_pct ?? 0).toFixed(0)}%`}
          color={(health?.cpu_pct ?? 0) > 80 ? "red" : (health?.cpu_pct ?? 0) > 50 ? "yellow" : "green"}
        />
        <MetricCard
          label="Memory"
          value={`${((health?.memory_mb ?? 0) / 1024).toFixed(1)} GB`}
          color={(health?.memory_mb ?? 0) > 1536 ? "red" : "gray"}
        />
      </div>

      {/* Equity Chart */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Equity Curve</h2>
        <EquityChart />
      </div>

      {/* Open Positions Mini-Table */}
      <PositionsMini positions={portfolio?.positions ?? {}} />
    </div>
  );
}

function PositionsMini({ positions }: { positions: Record<string, PortfolioState["positions"][string]> }) {
  const entries = Object.entries(positions);
  if (entries.length === 0) {
    return (
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4 text-center text-gray-500">
        No open positions
      </div>
    );
  }

  return (
    <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
      <h2 className="text-sm font-medium text-gray-400 mb-3">Open Positions</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 text-left border-b border-[#1e1e2e]">
            <th className="pb-2 font-normal">Pair</th>
            <th className="pb-2 font-normal">Side</th>
            <th className="pb-2 font-normal">Entry</th>
            <th className="pb-2 font-normal">SL</th>
            <th className="pb-2 font-normal">TP</th>
            <th className="pb-2 font-normal">P&L</th>
            <th className="pb-2 font-normal">Strategy</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([pair, pos]) => (
            <tr key={pair} className="border-b border-[#1e1e2e]/50 hover:bg-white/5">
              <td className="py-2 font-medium">{pair}</td>
              <td className={`py-2 ${pos.direction === "LONG" ? "text-green-400" : "text-red-400"}`}>
                {pos.direction}
              </td>
              <td className="py-2">${pos.entry_price.toLocaleString()}</td>
              <td className="py-2">${pos.stop_loss.toLocaleString()}</td>
              <td className="py-2">${pos.tp1.toLocaleString()}</td>
              <td className={`py-2 ${pos.current_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                ${pos.current_pnl.toLocaleString()}
              </td>
              <td className="py-2 text-gray-500">{pos.strategy}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-6 animate-pulse-slow">
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-24 bg-[#12121a] rounded-xl" />
        ))}
      </div>
      <div className="h-64 bg-[#12121a] rounded-xl" />
    </div>
  );
}
