import { useState } from "react";
import { Copy, Check, Zap, Radio, Globe } from "lucide-react";

const WEBHOOK_URL = `${typeof window !== "undefined" ? window.location.origin : ""}/webhook/tradingview`;

const indicators = [
  { name: "rsi", label: "RSI (Relative Strength Index)", params: { length: 14 } },
  { name: "macd", label: "MACD", params: { fast: 12, slow: 26, signal: 9 } },
  { name: "ema", label: "EMA Crossover", params: { fast: 9, slow: 21 } },
  { name: "bollinger_bands", label: "Bollinger Bands", params: { length: 20, mult: 2.0 } },
  { name: "stochastic", label: "Stochastic", params: { k: 14, d: 3 } },
];

const socialData = { fear_greed: 45, label: "neutral", composite: 0.52, recommendation: "neutral" };

export default function TradingViewPage() {
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">TradingView Integration</h1>

      {/* Webhook Card */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4">
          <Radio className="w-5 h-5 text-blue-400" />
          <h2 className="font-semibold">Webhook Endpoint</h2>
        </div>
        <div className="flex items-center gap-3 bg-[#0a0a0f] rounded-lg p-3 border border-[#1e1e2e]">
          <code className="flex-1 text-sm text-blue-300 font-mono break-all">{WEBHOOK_URL}</code>
          <button onClick={() => copy(WEBHOOK_URL, "url")} className="p-2 hover:bg-white/5 rounded text-gray-400">
            {copied === "url" ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Paste this URL in your TradingView alert's Webhook URL field. Supported formats: JSON, OctoBot-style, plain text, PineConnector.
        </p>
      </div>

      {/* Indicators */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4">
          <Zap className="w-5 h-5 text-yellow-400" />
          <h2 className="font-semibold">Indicators & PineScript Templates</h2>
        </div>
        <div className="space-y-3">
          {indicators.map((ind) => (
            <div key={ind.name} className="flex items-center justify-between bg-[#0a0a0f] rounded-lg p-3 border border-[#1e1e2e]">
              <div>
                <div className="text-sm font-medium">{ind.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {Object.entries(ind.params).map(([k, v]) => `${k}=${v}`).join(", ")}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => copy(`// ${ind.label} Alert\n// Add this to TradingView alert message:\n// {"action":"{{strategy.order.action}}","symbol":"BTCUSDT","indicator":"${ind.name}","indicator_value":{{plot("${ind.name.toUpperCase()}")}},"confidence":0.8}`, ind.name)}
                  className="px-3 py-1.5 text-xs rounded-lg bg-blue-600/20 text-blue-400 hover:bg-blue-600/30"
                >
                  {copied === ind.name ? "Copied!" : "Copy PineScript"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Social Signals */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4">
          <Globe className="w-5 h-5 text-purple-400" />
          <h2 className="font-semibold">Social & Sentiment Signals</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-[#0a0a0f] rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500 mb-1">Fear & Greed</div>
            <div className={`text-2xl font-bold ${
              socialData.fear_greed > 60 ? "text-green-400" : socialData.fear_greed < 40 ? "text-red-400" : "text-yellow-400"
            }`}>
              {socialData.fear_greed}
            </div>
            <div className="text-xs text-gray-500 capitalize">{socialData.label}</div>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500 mb-1">Composite</div>
            <div className="text-2xl font-bold text-blue-400">{(socialData.composite * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500 mb-1">Recommendation</div>
            <div className="text-lg font-bold text-purple-400 capitalize">{socialData.recommendation}</div>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500 mb-1">Alerts 24h</div>
            <div className="text-2xl font-bold text-gray-300">12</div>
          </div>
        </div>
      </div>
    </div>
  );
}
