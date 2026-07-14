import { AlertTriangle, Shield } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJSON, postJSON } from "../api/client";

interface RiskData {max_risk_per_trade:number;max_positions:number;max_correlation:number;max_exposure:number;stop_multipliers:Record<string,number>;drawdown_limits:Record<string,number>;recovery_threshold:number;recovery_exit_threshold:number;recovery_min_wins:number;recovery_mode:boolean;recovery_consecutive_wins:number}

export default function RiskPage() {
  const qc = useQueryClient();
  const { data: r } = useQuery<RiskData>({ queryKey: ["risk"], queryFn: () => fetchJSON("/api/risk"), refetchInterval: 30000 });

  const exitRec = useMutation({ mutationFn: () => postJSON("/api/risk/recovery/exit"), onSuccess: () => qc.invalidateQueries({ queryKey: ["risk"] }) });
  const { data: pf } = useQuery<{total_drawdown_pct:number}>({ queryKey: ["portfolio"], queryFn: () => fetchJSON("/portfolio"), refetchInterval: 5000 });

  const dd = r?.drawdown_limits ?? {daily:2,weekly:5,monthly:10,total:15};
  const cur = pf?.total_drawdown_pct ?? 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Risk Management</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[["Risk/Trade",`${(r?.max_risk_per_trade??1.5)*100}%`],["Max Positions",`${r?.max_positions??3}`],["Max Correlation",(r?.max_correlation??0.7).toFixed(2)],["Max Exposure",`${r?.max_exposure??3.0}%`]].map(([l,v])=>(
          <div key={l} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4"><div className="text-xs text-gray-500">{l}</div><div className="text-xl font-bold mt-1">{v}</div></div>
        ))}
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Stop-Loss Multipliers</h2>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(r?.stop_multipliers??{ultra_quiet:0.8,quiet:1.0,normal:1.2,volatile:1.5}).map(([k,v])=>(
            <div key={k} className="text-center"><div className="text-xs text-gray-500 capitalize mb-1">{k.replace("_"," ")}</div><div className="text-lg font-bold">×{v}</div></div>
          ))}
        </div>
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Drawdown Limits</h2>
        {Object.entries(dd).map(([k,v])=>{const pct=Math.min(100,(cur/v)*100);const co=pct>80?"bg-red-500":pct>50?"bg-yellow-500":"bg-green-500";return(
          <div key={k} className="mb-3"><div className="flex justify-between text-xs mb-1"><span className="text-gray-400 capitalize">{k}</span><span className="text-gray-500">{cur.toFixed(1)}% / {v.toFixed(1)}%</span></div><div className="h-2 bg-[#1e1e2e] rounded-full overflow-hidden"><div className={`h-full rounded-full ${co}`} style={{width:`${pct}%`}} /></div></div>
        )})}
      </div>

      <div className={`bg-[#12121a] rounded-xl border p-4 ${r?.recovery_mode?"border-red-500/30":"border-[#1e1e2e]"}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {r?.recovery_mode ? <AlertTriangle className="w-5 h-5 text-red-400" /> : <Shield className="w-5 h-5 text-green-400" />}
            <div><h2 className="font-medium">Recovery Mode: <span className={r?.recovery_mode?"text-red-400":"text-green-400"}>{r?.recovery_mode?"ACTIVE":"Normal"}</span></h2><p className="text-xs text-gray-500 mt-0.5">Threshold: {r?.recovery_threshold??8}% → risk halved. Exit: &lt;{r?.recovery_exit_threshold??5}% + {r?.recovery_min_wins??3} consecutive wins.</p></div>
          </div>
          {r?.recovery_mode && (
            <div className="flex items-center gap-3">
              <div className="text-right"><div className="text-xs text-gray-500">Consecutive Wins</div><div className="text-lg font-bold">{r?.recovery_consecutive_wins??0} / {r?.recovery_min_wins??3}</div></div>
              <button onClick={() => exitRec.mutate()} disabled={exitRec.isPending} className="px-3 py-1.5 rounded-lg text-xs bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20">{exitRec.isPending?"...":"Force Exit"}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
