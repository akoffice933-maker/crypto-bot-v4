import { Target, Edit3, Power } from "lucide-react";

const strategies = [
  { name: "Sweep", type: "sweep", enabled: true, wick_ratio: 1.8, volume_multiplier: 1.25, tolerance: 0.0018, min_rr: 2.0, trades: 342, winrate: 0.54, pnl: 2340 },
  { name: "Bounce", type: "bounce", enabled: true, wick_ratio: 1.5, volume_multiplier: 1.10, tolerance: 0.0018, min_rr: 1.5, trades: 218, winrate: 0.51, pnl: 890 },
  { name: "Breakout", type: "breakout", enabled: false, wick_ratio: 0, volume_multiplier: 0, tolerance: 0, min_rr: 0, sl_atr_mult: 1.5, tp_min: 0.02, tp_max: 0.04, trades: 156, winrate: 0.38, pnl: -340 },
];

export default function StrategiesPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Strategies</h1>

      <div className="grid gap-4">
        {strategies.map((s) => (
          <div key={s.name} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Target className="w-5 h-5 text-blue-400" />
                <h2 className="text-lg font-semibold">{s.name}</h2>
                <span className={`px-2 py-0.5 rounded text-xs ${
                  s.enabled ? "bg-green-500/10 text-green-400" : "bg-gray-500/10 text-gray-400"
                }`}>
                  {s.enabled ? "Active" : "Disabled"}
                </span>
              </div>
              <div className="flex gap-2">
                <button className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-gray-200">
                  <Power className="w-4 h-4" />
                </button>
                <button className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-blue-400">
                  <Edit3 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-3">
              <Param label="Trades" value={s.trades} />
              <Param label="Winrate" value={`${(s.winrate * 100).toFixed(1)}%`} color={s.winrate >= 0.5 ? "text-green-400" : "text-red-400"} />
              <Param label="P&L" value={`$${s.pnl.toLocaleString()}`} color={s.pnl >= 0 ? "text-green-400" : "text-red-400"} />
              {s.name !== "Breakout" ? (
                <>
                  <Param label="Wick Ratio" value={s.wick_ratio} />
                  <Param label="Min RR" value={`1:${s.min_rr}`} />
                </>
              ) : (
                <>
                  <Param label="SL ATR×" value={s.sl_atr_mult ?? 0} />
                  <Param label="TP Range" value={`${((s.tp_min ?? 0) * 100).toFixed(0)}–${((s.tp_max ?? 0) * 100).toFixed(0)}%`} />
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Param({ label, value, color = "text-gray-300" }: { label: string; value: string | number; color?: string }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-sm font-medium ${color}`}>{value}</div>
    </div>
  );
}
