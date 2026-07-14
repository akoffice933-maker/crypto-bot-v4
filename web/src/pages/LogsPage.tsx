import { useState } from "react";
import { Pause, Play, Search } from "lucide-react";

const logLevels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;
type LogLevel = (typeof logLevels)[number];

const mockLogs = Array.from({ length: 50 }, (_, i) => ({
  ts: new Date(Date.now() - i * 15000).toISOString(),
  level: (["INFO", "INFO", "INFO", "DEBUG", "WARNING", "ERROR", "INFO", "INFO", "CRITICAL", "DEBUG"] as LogLevel[])[i % 10],
  service: ["data_service", "strategy_engine", "risk_engine", "execution_engine", "portfolio_engine", "health_monitor"][i % 6],
  message: [
    "Fetched 100 candles for BTCUSDT/1h",
    "Signal generated: SWEEP LONG BTCUSDT confidence=0.82",
    "Risk decision: approved, size=0.015 BTC",
    "Order filled: 65001.50, slippage=0.002%",
    "Position opened: BTCUSDT LONG @ 65001.50",
    "Health check passed: all metrics green",
    "WebSocket reconnected after 3.2s",
    "Bayesian update: sweep winrate 0.54 → 0.55",
    "Circuit breaker OPEN: 5+ API failures in 60s",
    "Feature calc took 48ms (limit: 100ms)",
  ][i % 10],
}));

export default function LogsPage() {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<LogLevel | "ALL">("ALL");
  const [search, setSearch] = useState("");

  const filtered = mockLogs.filter((l) => {
    if (filter !== "ALL" && l.level !== filter) return false;
    if (search && !l.message.toLowerCase().includes(search.toLowerCase()) && !l.service.includes(search)) return false;
    return true;
  });

  const colorMap: Record<LogLevel, string> = {
    DEBUG: "text-gray-500",
    INFO: "text-blue-400",
    WARNING: "text-yellow-400",
    ERROR: "text-red-400",
    CRITICAL: "text-red-500 font-bold",
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Logs</h1>
        <button
          onClick={() => setPaused(!paused)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
            paused ? "bg-yellow-500/10 text-yellow-400" : "bg-green-500/10 text-green-400"
          }`}
        >
          {paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          {paused ? "Paused" : "Live"}
        </button>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search logs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#12121a] border border-[#1e1e2e] rounded-lg py-2 pl-9 pr-3 text-sm text-gray-200 placeholder-gray-600"
          />
        </div>
        {(["ALL", ...logLevels] as const).map((level) => (
          <button
            key={level}
            onClick={() => setFilter(level)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
              filter === level
                ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                : "bg-[#12121a] border border-[#1e1e2e] text-gray-400 hover:text-gray-200"
            }`}
          >
            {level}
          </button>
        ))}
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
        <div className="overflow-auto max-h-[60vh] font-mono text-xs">
          {filtered.map((log, i) => (
            <div
              key={i}
              className="flex gap-3 px-4 py-1.5 hover:bg-white/[0.02] border-b border-[#1e1e2e]/30"
            >
              <span className="text-gray-600 shrink-0 w-24">{log.ts.slice(11, 23)}</span>
              <span className={`shrink-0 w-16 ${colorMap[log.level]}`}>{log.level}</span>
              <span className="text-purple-400 shrink-0 w-32">{log.service}</span>
              <span className="text-gray-300">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
