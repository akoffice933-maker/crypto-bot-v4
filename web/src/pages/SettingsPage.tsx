import { useState } from "react";
import { Radio, Play, Square, RefreshCw, Globe, Bell, Eye, EyeOff } from "lucide-react";

export default function SettingsPage() {
  const [showKey, setShowKey] = useState(false);
  const [botStatus, setBotStatus] = useState<"running" | "stopped">("stopped");

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Bot Control */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Radio className="w-5 h-5 text-blue-400" />
            <div>
              <h2 className="font-semibold">Bot Control</h2>
              <p className="text-xs text-gray-500">Status: {botStatus === "running" ? (
                <span className="text-green-400">Running · 4h 23m uptime</span>
              ) : (
                <span className="text-gray-400">Stopped</span>
              )}</p>
            </div>
          </div>
          <div className="flex gap-2">
            {botStatus === "stopped" ? (
              <button
                onClick={() => setBotStatus("running")}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700"
              >
                <Play className="w-4 h-4" /> Start
              </button>
            ) : (
              <>
                <button
                  onClick={() => setBotStatus("stopped")}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700"
                >
                  <Square className="w-4 h-4" /> Stop
                </button>
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-yellow-600/20 text-yellow-400 text-sm hover:bg-yellow-600/30">
                  <RefreshCw className="w-4 h-4" /> Restart
                </button>
              </>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            ["Version", "5.0.0"],
            ["Mode", "paper"],
            ["Exchange", "binance"],
          ].map(([label, val]) => (
            <div key={label} className="bg-[#0a0a0f] rounded-lg p-3">
              <div className="text-xs text-gray-500">{label}</div>
              <div className="text-sm font-medium mt-0.5">{val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Exchange Settings */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4">
          <Globe className="w-5 h-5 text-green-400" />
          <h2 className="font-semibold">Exchange</h2>
          <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400">Testnet</span>
        </div>
        <div className="space-y-3">
          <InputRow label="Exchange ID" value="binance" />
          <InputRow label="API Key" value={showKey ? "abc123xyz" : "••••••••••••••••"} action={
            <button onClick={() => setShowKey(!showKey)} className="text-gray-400">{showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
          } />
          <InputRow label="API Secret" value="••••••••••••••••••••••••••" />
          <InputRow label="Testnet" value="Enabled" />
        </div>
        <button className="mt-4 px-4 py-2 rounded-lg bg-blue-600/10 text-blue-400 text-sm hover:bg-blue-600/20">
          Test Connection
        </button>
      </div>

      {/* Notifications */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4">
          <Bell className="w-5 h-5 text-yellow-400" />
          <h2 className="font-semibold">Notifications</h2>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm">Telegram</div>
              <div className="text-xs text-gray-500">Bot Token + Chat ID</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Not configured</span>
              <button className="text-xs text-blue-400 hover:underline">Configure</button>
            </div>
          </div>
          <div className="flex items-center justify-between py-2 border-t border-[#1e1e2e]">
            <div>
              <div className="text-sm">Email</div>
              <div className="text-xs text-gray-500">Alerts for critical events</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Not configured</span>
              <button className="text-xs text-blue-400 hover:underline">Configure</button>
            </div>
          </div>
          <div className="flex items-center justify-between py-2 border-t border-[#1e1e2e]">
            <div>
              <div className="text-sm">Event Webhook</div>
              <div className="text-xs text-gray-500">External HTTP endpoint</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Not configured</span>
              <button className="text-xs text-blue-400 hover:underline">Configure</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function InputRow({ label, value, action }: { label: string; value: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between bg-[#0a0a0f] rounded-lg px-3 py-2 border border-[#1e1e2e]">
      <span className="text-sm text-gray-400">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm font-mono text-gray-300">{value}</span>
        {action}
      </div>
    </div>
  );
}
