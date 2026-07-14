import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import type { PortfolioState, Position } from "../types/api";

export default function TradesPage() {
  const { data: pf } = useQuery<PortfolioState>({ queryKey: ["portfolio"], queryFn: () => fetchJSON("/portfolio"), refetchInterval: 5000 });
  const positions = (pf?.positions ?? {}) as Record<string, Position>;
  const entries = Object.entries(positions);

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Trade History</h1>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[["Open Positions",entries.length],["Balance",`$${(pf?.balance??0).toLocaleString()}`],["Equity",`$${(pf?.equity??0).toLocaleString()}`],["Daily PnL",`$${(pf?.daily_pnl??0).toLocaleString()}`],["Drawdown",`${(pf?.total_drawdown_pct??0).toFixed(1)}%`]].map(([l,v])=><div key={l} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-3"><div className="text-xs text-gray-500">{l}</div><div className="text-lg font-bold mt-0.5">{v}</div></div>)}
      </div>
      {entries.length===0 ? <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4 text-center text-gray-500">No trades yet</div> : (
        <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-500 text-left border-b border-[#1e1e2e] bg-[#0d0d14]"><th className="py-3 px-4 font-normal">Pair</th><th className="py-3 px-4 font-normal">Side</th><th className="py-3 px-4 font-normal">Entry</th><th className="py-3 px-4 font-normal">P&amp;L</th><th className="py-3 px-4 font-normal">Strategy</th></tr></thead>
            <tbody>{entries.map(([pair,pos])=><tr key={pair} className="border-b border-[#1e1e2e]/50 hover:bg-white/5"><td className="py-3 px-4 font-medium">{pair}</td><td className={`py-3 px-4 ${pos.direction==="LONG"?"text-green-400":"text-red-400"}`}>{pos.direction}</td><td className="py-3 px-4">${pos.entry_price.toLocaleString()}</td><td className={`py-3 px-4 font-medium ${pos.current_pnl>=0?"text-green-400":"text-red-400"}`}>${pos.current_pnl.toLocaleString()}</td><td className="py-3 px-4 capitalize text-gray-400">{pos.strategy}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
