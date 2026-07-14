import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import { BarChart3, TrendingUp, DollarSign, Percent } from "lucide-react";
import { PnLChart } from "../components/charts/EquityChart";
import type { AnalyticsMetrics } from "../types/api";

export default function AnalyticsPage() {
  const { data: m } = useQuery<AnalyticsMetrics>({ queryKey: ["analytics"], queryFn: () => fetchJSON("/analytics/metrics"), refetchInterval: 30000 });

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Analytics</h1>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          ["Winrate",`${((m?.winrate??0)*100).toFixed(1)}%`,Percent,"text-green-400"],
          ["Profit Factor",(m?.profit_factor??0).toFixed(2),TrendingUp,"text-blue-400"],
          ["Total P&L",`$${(m?.total_pnl??0).toLocaleString()}`,DollarSign,(m?.total_pnl??0)>=0?"text-green-400":"text-red-400"],
          ["Sharpe",(m?.sharpe_ratio??0).toFixed(2),BarChart3,"text-blue-400"],
          ["Calmar",(m?.calmar_ratio??0).toFixed(2),BarChart3,"text-blue-400"],
          ["Max DD",`${(m?.max_drawdown??0).toFixed(1)}%`,TrendingUp,"text-red-400"],
        ].map(([l,v,Icon,co])=>(
          <div key={l as string} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-3">
            <div className="flex items-center gap-2 mb-1">{Icon && <Icon className={`w-4 h-4 ${co}`} />}<span className="text-xs text-gray-500">{l as string}</span></div>
            <div className={`text-lg font-bold ${co}`}>{v as string}</div>
          </div>
        ))}
      </div>
      {m?.strategy_breakdown && Object.keys(m.strategy_breakdown).length > 0 && (
        <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Strategy Breakdown</h2>
          <table className="w-full text-sm">
            <thead><tr className="text-gray-500 text-left border-b border-[#1e1e2e]"><th className="pb-2 font-normal">Strategy</th><th className="pb-2 font-normal">Trades</th><th className="pb-2 font-normal">Winrate</th><th className="pb-2 font-normal">P&amp;L</th><th className="pb-2 font-normal">PF</th></tr></thead>
            <tbody>{Object.entries(m.strategy_breakdown).map(([n,s])=>(
              <tr key={n} className="border-b border-[#1e1e2e]/50"><td className="py-2 font-medium capitalize">{n}</td><td className="py-2">{s.count}</td><td className={`py-2 ${s.winrate>=0.5?"text-green-400":"text-red-400"}`}>{(s.winrate*100).toFixed(1)}%</td><td className={`py-2 ${s.total_pnl>=0?"text-green-400":"text-red-400"}`}>${s.total_pnl.toLocaleString()}</td><td className="py-2">{typeof s.profit_factor==="number"?s.profit_factor.toFixed(2):s.profit_factor}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4"><h2 className="text-sm font-medium text-gray-400 mb-3">Daily P&amp;L</h2><PnLChart /></div>
    </div>
  );
}
