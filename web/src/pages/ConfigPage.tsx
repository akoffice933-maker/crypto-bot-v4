import { useState } from "react";
import { FileCode, Save, RotateCcw, Eye } from "lucide-react";

const envs = [
  { id: "production", label: "Production", file: "production.yaml", active: false, updated: "2026-07-13 10:00" },
  { id: "paper", label: "Paper Trading", file: "paper.yaml", active: true, updated: "2026-07-14 08:30" },
  { id: "backtest", label: "Backtest", file: "backtest.yaml", active: false, updated: "2026-07-12 15:45" },
];

const sampleYaml = `system_version: 5.0.0

data:
  pairs: [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT]
  timeframes: [15m, 1h, 4h, 1d]

strategy:
  sweep:
    enabled: true
    wick_ratio: 1.8
    volume_multiplier: 1.25
    min_rr: 2.0

risk:
  max_risk_per_trade: 0.015
  max_positions: 3

execution:
  max_slippage: 0.0005
  limit_timeout: 60`;

export default function ConfigPage() {
  const [activeEnv, setActiveEnv] = useState("paper");
  const [rawMode, setRawMode] = useState(false);
  const [yaml, setYaml] = useState(sampleYaml);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Configuration</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setRawMode(!rawMode)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs ${
              rawMode ? "bg-yellow-500/10 text-yellow-400" : "bg-blue-600/10 text-blue-400"
            }`}
          >
            {rawMode ? <Eye className="w-3.5 h-3.5" /> : <FileCode className="w-3.5 h-3.5" />}
            {rawMode ? "Form Mode" : "Raw YAML"}
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-green-600/10 text-green-400">
            <Save className="w-3.5 h-3.5" /> Save
          </button>
        </div>
      </div>

      {/* Environment Tabs */}
      <div className="flex gap-2">
        {envs.map((env) => (
          <button
            key={env.id}
            onClick={() => setActiveEnv(env.id)}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              activeEnv === env.id
                ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                : "bg-[#12121a] border border-[#1e1e2e] text-gray-400 hover:text-gray-200"
            }`}
          >
            <div className="font-medium">{env.label}</div>
            <div className="text-xs opacity-60">{env.file}</div>
          </button>
        ))}
      </div>

      {/* Config Editor */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
        {rawMode ? (
          <textarea
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            className="w-full h-[500px] bg-transparent p-4 font-mono text-sm text-gray-200 resize-none outline-none"
            spellCheck={false}
          />
        ) : (
          <div className="p-4 space-y-4">
            <FormSection title="Data">
              <FormRow label="Pairs" value="BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT" />
              <FormRow label="Timeframes" value="15m, 1h, 4h, 1d" />
            </FormSection>
            <FormSection title="Strategy — Sweep">
              <FormRow label="Enabled" value="true" />
              <FormRow label="Wick Ratio" value="1.8" />
              <FormRow label="Volume Multiplier" value="1.25" />
              <FormRow label="Min RR" value="2.0" />
            </FormSection>
            <FormSection title="Risk">
              <FormRow label="Max Risk/Trade" value="1.5%" />
              <FormRow label="Max Positions" value="3" />
              <FormRow label="Max Correlation" value="0.70" />
            </FormSection>
            <FormSection title="Execution">
              <FormRow label="Max Slippage" value="0.05%" />
              <FormRow label="Limit Timeout" value="60s" />
            </FormSection>
          </div>
        )}
      </div>

      {/* Version History */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Version History</h2>
        <div className="space-y-2">
          {["5.0.0", "4.5.0", "4.4.1"].map((v, i) => (
            <div key={v} className="flex items-center justify-between py-2 border-b border-[#1e1e2e]/50 last:border-0">
              <div className="flex items-center gap-3">
                <span className="text-sm font-mono text-blue-400">{v}</span>
                <span className="text-xs text-gray-500">a1b2c3d4</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-500">{["2026-07-14", "2026-07-13", "2026-07-13"][i]}</span>
                {i > 0 && (
                  <button className="flex items-center gap-1 text-xs text-yellow-400 hover:text-yellow-300">
                    <RotateCcw className="w-3 h-3" /> Rollback
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{title}</h3>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </div>
  );
}

function FormRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center bg-[#0a0a0f] rounded-lg px-3 py-2 border border-[#1e1e2e]">
      <span className="text-sm text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-200">{value}</span>
    </div>
  );
}
