import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import { Target, Power } from "lucide-react";

export default function StrategiesPage() {
  const { data } = useQuery<{strategies: Array<{name:string;enabled:boolean;wick_ratio?:number;volume_multiplier?:number;min_rr?:number;sl_atr_mult?:number;tp_min?:number;tp_max?:number;winrate?:number}>}>({ queryKey: ["strategies"], queryFn: () => fetchJSON("/api/strategies"), refetchInterval: 30000 });

  const list = data?.strategies ?? [
    {name:"sweep",enabled:true,wick_ratio:1.8,volume_multiplier:1.25,min_rr:2.0},
    {name:"bounce",enabled:true,wick_ratio:1.5,volume_multiplier:1.10,min_rr:1.5},
    {name:"breakout",enabled:true,sl_atr_mult:1.5,tp_min:0.02,tp_max:0.04},
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Strategies</h1>
      <div className="grid gap-4">
        {list.map(s => (
          <div key={s.name} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Target className="w-5 h-5 text-blue-400" />
                <h2 className="text-lg font-semibold capitalize">{s.name}</h2>
                <span className={`px-2 py-0.5 rounded text-xs ${s.enabled?"bg-green-500/10 text-green-400":"bg-gray-500/10 text-gray-400"}`}>{s.enabled?"Active":"Disabled"}</span>
              </div>
              <button className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-gray-200"><Power className="w-4 h-4" /></button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {s.winrate !== undefined && <P label="Winrate" value={`${(s.winrate*100).toFixed(1)}%`} c={s.winrate>=0.5?"text-green-400":"text-red-400"} />}
              {s.wick_ratio && <P label="Wick Ratio" value={s.wick_ratio} />}
              {s.volume_multiplier && <P label="Vol Mult" value={`×${s.volume_multiplier}`} />}
              {s.min_rr && <P label="Min RR" value={`1:${s.min_rr}`} />}
              {s.sl_atr_mult && <P label="SL ATR×" value={s.sl_atr_mult} />}
              {s.tp_min !== undefined && s.tp_max !== undefined && <P label="TP Range" value={`${((s.tp_min??0)*100).toFixed(0)}–${((s.tp_max??0)*100).toFixed(0)}%`} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function P({label,value,c="text-gray-300"}:{label:string;value:number|string;c?:string}) {
  return <div><div className="text-xs text-gray-500">{label}</div><div className={`text-sm font-medium ${c}`}>{value}</div></div>;
}
