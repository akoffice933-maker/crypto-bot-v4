import { BarChart3, TrendingUp, DollarSign, Percent } from "lucide-react";
import { PnLChart } from "../components/charts/EquityChart";

const mockMetrics = {
  total_trades: 716, wins: 387, losses: 329,
  winrate: 0.541, profit_factor: 1.47, expectancy: 12.4,
  avg_win: 145.2, avg_loss: -98.7, total_pnl: 4820,
  total_fees: 358, sharpe_ratio: 1.32, calmar_ratio: 2.15,
  recovery_factor: 3.4, max_drawdown: 8.2,
  strategy_breakdown: {
    sweep: { count: 342, winrate: 0.54, total_pnl: 2340, profit_factor: 1.65 },
    bounce: { count: 218, winrate: 0.51, total_pnl: 890, profit_factor: 1.32 },
    breakout: { count: 156, winrate: 0.38, total_pnl: -340, profit_factor: 0.72 },
  },
};

export default function AnalyticsPage() {
  const m = mockMetrics;
  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Analytics</h1>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {[
          { label: "Winrate", value: `${(m.winrate * 100).toFixed(1)}%`, icon: Percent, color: "text-green-400" },
          { label: "Profit Factor", value: m.profit_factor.toFixed(2), icon: TrendingUp, color: "text-blue-400" },
          { label: "Total P&L", value: `$${m.total_pnl.toLocaleString()}`, icon: DollarSign, color: "text-green-400" },
          { label: "Sharpe", value: m.sharpe_ratio.toFixed(2), icon: BarChart3, color: "text-blue-400" },
          { label: "Calmar", value: m.calmar_ratio.toFixed(2), icon: BarChart3, color: "text-blue-400" },
          { label: "Max DD", value: `${m.max_drawdown.toFixed(1)}%`, icon: TrendingUp, color: "text-red-400" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-3">
            <div className="flex items-center gap-2 mb-1">
              <Icon className={`w-4 h-4 ${color}`} />
              <span className="text-xs text-gray-500">{label}</span>
            </div>
            <div className={`text-lg font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Per-Strategy */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Strategy Breakdown</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-left border-b border-[#1e1e2e]">
              <th className="pb-2 font-normal">Strategy</th>
              <th className="pb-2 font-normal">Trades</th>
              <th className="pb-2 font-normal">Winrate</th>
              <th className="pb-2 font-normal">P&L</th>
              <th className="pb-2 font-normal">PF</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(m.strategy_breakdown).map(([name, s]) => (
              <tr key={name} className="border-b border-[#1e1e2e]/50">
                <td className="py-2 font-medium capitalize">{name}</td>
                <td className="py-2">{s.count}</td>
                <td className={`py-2 ${s.winrate >= 0.5 ? "text-green-400" : "text-red-400"}`}>
                  {(s.winrate * 100).toFixed(1)}%
                </td>
                <td className={`py-2 ${s.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                  ${s.total_pnl.toLocaleString()}
                </td>
                <td className="py-2">{typeof s.profit_factor === "number" ? s.profit_factor.toFixed(2) : s.profit_factor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* PnL Chart */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Daily P&L</h2>
        <PnLChart />
      </div>
    </div>
  );
}
