import { Activity, Cpu, HardDrive, Wifi, WifiOff } from "lucide-react";

const metrics = [
  { label: "Data Latency", value: "124 ms", limit: 500, color: "green" },
  { label: "Feature Calc", value: "48 ms", limit: 100, color: "green" },
  { label: "CPU", value: "34%", limit: 80, color: "green" },
  { label: "Memory", value: "1.2 GB", limit: 2.0, color: "green" },
  { label: "API Errors/min", value: "0", limit: 5, color: "green" },
  { label: "Retry %", value: "2.1%", limit: 10, color: "green" },
  { label: "Order Time", value: "320 ms", limit: 1000, color: "green" },
  { label: "WebSocket", value: "Connected", limit: 100, color: "green" },
];

export default function MonitorPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">System Monitor</h1>
        <span className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-xs font-medium">
          <span className="w-2 h-2 rounded-full bg-green-400" />
          Healthy
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {metrics.map((m) => (
          <div key={m.label} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
            <div className="flex items-center gap-2 mb-2">
              {m.label === "WebSocket" ? (
                m.value === "Connected" ? <Wifi className="w-4 h-4 text-green-400" /> : <WifiOff className="w-4 h-4 text-red-400" />
              ) : m.label === "CPU" ? (
                <Cpu className="w-4 h-4 text-blue-400" />
              ) : m.label === "Memory" ? (
                <HardDrive className="w-4 h-4 text-yellow-400" />
              ) : (
                <Activity className="w-4 h-4 text-blue-400" />
              )}
              <span className="text-xs text-gray-500">{m.label}</span>
            </div>
            <div className="text-xl font-bold">{m.value}</div>
            <div className="text-xs text-gray-500 mt-1">Limit: {m.limit}{m.label === "Memory" ? " GB" : m.label === "Data Latency" || m.label === "Feature Calc" || m.label === "Order Time" ? " ms" : m.label === "CPU" || m.label === "Retry %" ? "%" : ""}</div>
          </div>
        ))}
      </div>

      {/* Uptime */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Uptime</h2>
        <div className="grid grid-cols-3 gap-4 text-center">
          {[
            ["24h", "99.97%"],
            ["7d", "99.92%"],
            ["30d", "99.85%"],
          ].map(([period, uptime]) => (
            <div key={period}>
              <div className="text-xs text-gray-500">{period}</div>
              <div className="text-2xl font-bold text-green-400">{uptime}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
