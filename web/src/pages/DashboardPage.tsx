import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJSON, postJSON } from "../api/client";
import { MetricCard } from "../components/ui/MetricCard";
import { EquityChart } from "../components/charts/EquityChart";
import type { PortfolioState, HealthStatus, BotStatus, Position } from "../types/api";
import { useAppStore } from "../store/appStore";

export default function DashboardPage() {
  const [tf, setTf] = useState("1d");
  const qc = useQueryClient();
  const { setBotRunning } = useAppStore();

  const { data: pf } = useQuery<PortfolioState>({ queryKey: ["portfolio"], queryFn: () => fetchJSON("/portfolio"), refetchInterval: 5000 });
  const { data: h } = useQuery<HealthStatus>({ queryKey: ["health"], queryFn: () => fetchJSON("/health"), refetchInterval: 10000 });
  const { data: bs } = useQuery<BotStatus>({ queryKey: ["bot-status"], queryFn: () => fetchJSON("/api/bot/status"), refetchInterval: 10000 });

  const startMut = useMutation({ mutationFn: () => postJSON("/api/bot/start"), onSuccess: () => { setBotRunning(true); qc.invalidateQueries({ queryKey: ["bot-status"] }); } });
  const stopMut = useMutation({ mutationFn: () => postJSON("/api/bot/stop"), onSuccess: () => { setBotRunning(false); qc.invalidateQueries({ queryKey: ["bot-status"] }); } });
  const closeMut = useMutation({ mutationFn: (p: string) => postJSON(`/api/positions/${p}/close`), onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }) });

  const sc = h?.status === "healthy" ? "green" : h?.status === "warning" ? "yellow" : "red";
  const positions = (pf?.positions ?? {}) as Record<string, Position>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-3">
          <span className={`inline-flex gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-${sc}-500/10 text-${sc}-400`}><span className={`w-1.5 h-1.5 rounded-full bg-${sc}-400`} />{h?.status ?? "unknown"}</span>
          {["1d","1w","1m"].map(t => <button key={t} onClick={() => setTf(t)} className={`px-2 py-1 text-xs rounded ${tf===t?"bg-blue-600 text-white":"bg-white/5 text-gray-400"}`}>{t}</button>)}
          {bs?.running ? <button onClick={() => stopMut.mutate()} className="px-3 py-1 text-xs rounded bg-red-500/10 text-red-400 hover:bg-red-500/20">Stop</button>
          : <button onClick={() => startMut.mutate()} className="px-3 py-1 text-xs rounded bg-green-500/10 text-green-400 hover:bg-green-500/20">Start</button>}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Balance" value={`$${(pf?.balance??0).toLocaleString()}`} color="blue" />
        <MetricCard label="Equity" value={`$${(pf?.equity??0).toLocaleString()}`} color="green" />
        <MetricCard label="Day PnL" value={`$${Math.abs(pf?.daily_pnl??0).toLocaleString()}`} change={(pf?.balance&&pf.daily_pnl)?(pf.daily_pnl/pf.balance)*100:0} color={(pf?.daily_pnl??0)>=0?"green":"red"} />
        <MetricCard label="Positions" value={pf?.open_positions_count??0} color="blue" />
        <MetricCard label="Drawdown" value={`${(pf?.total_drawdown_pct??0).toFixed(1)}%`} color={(pf?.total_drawdown_pct??0)>5?"red":"yellow"} />
        <MetricCard label="Recovery" value={pf?.recovery_mode?"ACTIVE":"Normal"} color={pf?.recovery_mode?"red":"green"} />
        <MetricCard label="CPU" value={`${(h?.cpu_pct??0).toFixed(0)}%`} color={(h?.cpu_pct??0)>80?"red":"green"} />
        <MetricCard label="Memory" value={`${((h?.memory_mb??0)/1024).toFixed(1)} GB`} color="gray" />
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4"><h2 className="text-sm font-medium text-gray-400 mb-3">Equity Curve</h2><EquityChart /></div>

      {Object.keys(positions).length === 0 ? (
        <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4 text-center text-gray-500">No open positions</div>
      ) : (
        <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Open Positions</h2>
          <table className="w-full text-sm">
            <thead><tr className="text-gray-500 text-left border-b border-[#1e1e2e]"><th className="pb-2 font-normal">Pair</th><th className="pb-2 font-normal">Side</th><th className="pb-2 font-normal">Entry</th><th className="pb-2 font-normal">SL</th><th className="pb-2 font-normal">TP</th><th className="pb-2 font-normal">P&amp;L</th><th className="pb-2 font-normal">Strategy</th><th className="pb-2 font-normal"></th></tr></thead>
            <tbody>{Object.entries(positions).map(([pair, pos]) => (
              <tr key={pair} className="border-b border-[#1e1e2e]/50 hover:bg-white/5">
                <td className="py-2 font-medium">{pair}</td>
                <td className={`py-2 ${pos.direction==="LONG"?"text-green-400":"text-red-400"}`}>{pos.direction}</td>
                <td className="py-2">${pos.entry_price.toLocaleString()}</td><td className="py-2">${pos.stop_loss.toLocaleString()}</td><td className="py-2">${pos.tp1.toLocaleString()}</td>
                <td className={`py-2 ${pos.current_pnl>=0?"text-green-400":"text-red-400"}`}>${pos.current_pnl.toLocaleString()}</td>
                <td className="py-2 text-gray-500">{pos.strategy}</td>
                <td className="py-2"><button onClick={() => closeMut.mutate(pair)} disabled={closeMut.isPending} className="text-xs text-red-400 hover:underline">{closeMut.isPending?"...":"Close"}</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
