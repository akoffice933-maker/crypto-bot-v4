import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJSON, postJSON } from "../api/client";
import type { PortfolioState, Position } from "../types/api";

export default function PositionsPage() {
  const qc = useQueryClient();
  const { data: pf } = useQuery<PortfolioState>({ queryKey: ["portfolio"], queryFn: () => fetchJSON("/portfolio"), refetchInterval: 5000 });
  const closeMut = useMutation({ mutationFn: (p: string) => postJSON(`/api/positions/${p}/close`), onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }) });
  const positions = (pf?.positions ?? {}) as Record<string, Position>;
  const entries = Object.entries(positions);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Positions</h1>
        <div className="flex gap-2">
          <button onClick={() => entries.filter(([_,p])=>p.direction==="LONG").forEach(([pair])=>closeMut.mutate(pair))} className="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">Close All LONG</button>
          <button onClick={() => entries.filter(([_,p])=>p.direction==="SHORT").forEach(([pair])=>closeMut.mutate(pair))} className="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">Close All SHORT</button>
        </div>
      </div>
      {entries.length===0 ? <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4 text-center text-gray-500">No open positions</div> : (
        <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-500 text-left border-b border-[#1e1e2e] bg-[#0d0d14]"><th className="py-3 px-4 font-normal">Pair</th><th className="py-3 px-4 font-normal">Side</th><th className="py-3 px-4 font-normal">Entry</th><th className="py-3 px-4 font-normal">P&amp;L</th><th className="py-3 px-4 font-normal">SL</th><th className="py-3 px-4 font-normal">TP</th><th className="py-3 px-4 font-normal">Strategy</th><th className="py-3 px-4 font-normal"></th></tr></thead>
            <tbody>{entries.map(([pair, pos]) => (
              <tr key={pair} className="border-b border-[#1e1e2e]/50 hover:bg-white/5">
                <td className="py-3 px-4 font-medium">{pair}</td>
                <td className={`py-3 px-4 font-medium ${pos.direction==="LONG"?"text-green-400":"text-red-400"}`}>{pos.direction}</td>
                <td className="py-3 px-4">${pos.entry_price.toLocaleString()}</td>
                <td className={`py-3 px-4 font-medium ${pos.current_pnl>=0?"text-green-400":"text-red-400"}`}>${pos.current_pnl.toLocaleString()}</td>
                <td className="py-3 px-4">${pos.stop_loss.toLocaleString()}</td>
                <td className="py-3 px-4">${pos.tp1.toLocaleString()}</td>
                <td className="py-3 px-4 capitalize text-gray-400">{pos.strategy}</td>
                <td className="py-3 px-4"><button onClick={() => closeMut.mutate(pair)} className="text-xs text-red-400 hover:underline">Close</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
