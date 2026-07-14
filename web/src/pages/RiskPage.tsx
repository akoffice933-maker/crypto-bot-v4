import { Shield, AlertTriangle } from "lucide-react";

const riskDefaults = {
  max_risk_per_trade: 1.5,
  max_positions: 3,
  max_correlation: 0.7,
  max_exposure: 3.0,
  stop_multipliers: { ultra_quiet: 0.8, quiet: 1.0, normal: 1.2, volatile: 1.5 },
  drawdown_limits: { daily: 2.0, weekly: 5.0, monthly: 10.0, total: 15.0 },
  recovery: { active: false, current_drawdown: 3.2, threshold: 8.0, exit_threshold: 5.0, wins: 0, required: 3 },
};

function ProgressBar({ label, current, limit }: { label: string; current: number; limit: number }) {
  const pct = Math.min(100, (current / limit) * 100);
  const color = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-green-500";
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-500">{current.toFixed(1)}% / {limit.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-[#1e1e2e] rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function RiskPage() {
  const { drawdown_limits, stop_multipliers, recovery } = riskDefaults;

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Risk Management</h1>

      {/* Risk Params */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ["Risk/Trade", "1.5%"],
          ["Max Positions", "3"],
          ["Max Correlation", "0.70"],
          ["Max Exposure", "3.0%"],
        ].map(([label, val]) => (
          <div key={label} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-xl font-bold mt-1">{val}</div>
          </div>
        ))}
      </div>

      {/* Stop Multipliers */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Stop-Loss Multipliers</h2>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(stop_multipliers).map(([regime, val]) => (
            <div key={regime} className="text-center">
              <div className="text-xs text-gray-500 capitalize mb-1">{regime.replace("_", " ")}</div>
              <div className="text-lg font-bold">×{val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Drawdown Limits */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Drawdown Limits</h2>
        <ProgressBar label="Daily" current={1.2} limit={drawdown_limits.daily} />
        <ProgressBar label="Weekly" current={2.8} limit={drawdown_limits.weekly} />
        <ProgressBar label="Monthly" current={3.2} limit={drawdown_limits.monthly} />
        <ProgressBar label="Total" current={3.2} limit={drawdown_limits.total} />
      </div>

      {/* Recovery Mode */}
      <div className={`bg-[#12121a] rounded-xl border p-4 ${recovery.active ? "border-red-500/30" : "border-[#1e1e2e]"}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {recovery.active ? (
              <AlertTriangle className="w-5 h-5 text-red-400" />
            ) : (
              <Shield className="w-5 h-5 text-green-400" />
            )}
            <div>
              <h2 className="font-medium">
                Recovery Mode: <span className={recovery.active ? "text-red-400" : "text-green-400"}>
                  {recovery.active ? "ACTIVE" : "Normal"}
                </span>
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Threshold: {recovery.threshold}% drawdown → risk halved, learning frozen.
                Exit: &lt;{recovery.exit_threshold}% + {recovery.required} consecutive wins.
              </p>
            </div>
          </div>
          {recovery.active && (
            <div className="text-right">
              <div className="text-xs text-gray-500">Consecutive Wins</div>
              <div className="text-lg font-bold">{recovery.wins} / {recovery.required}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
