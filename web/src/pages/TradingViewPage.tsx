import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import { Copy, Check, Zap, Radio, Globe } from "lucide-react";

const WEBHOOK_URL = `${typeof window!=="undefined"?window.location.origin:""}/webhook/tradingview`;

export default function TradingViewPage() {
  const [copied, setCopied] = useState<string|null>(null);
  const copy = (text:string,id:string)=>{navigator.clipboard.writeText(text);setCopied(id);setTimeout(()=>setCopied(null),2000);};

  const { data: social } = useQuery<{fear_greed:number;fear_greed_label:string;composite:number;recommendation:string}>({ queryKey: ["social"], queryFn: () => fetchJSON("/webhook/social?pair=BTCUSDT"), refetchInterval: 60000 });

  const indicators = [
    {name:"rsi",label:"RSI (Relative Strength Index)",params:{length:14}},
    {name:"macd",label:"MACD",params:{fast:12,slow:26,signal:9}},
    {name:"ema",label:"EMA Crossover",params:{fast:9,slow:21}},
    {name:"bollinger_bands",label:"Bollinger Bands",params:{length:20,mult:2.0}},
    {name:"stochastic",label:"Stochastic",params:{k:14,d:3}},
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">TradingView Integration</h1>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4"><Radio className="w-5 h-5 text-blue-400"/><h2 className="font-semibold">Webhook Endpoint</h2></div>
        <div className="flex items-center gap-3 bg-[#0a0a0f] rounded-lg p-3 border border-[#1e1e2e]">
          <code className="flex-1 text-sm text-blue-300 font-mono break-all">{WEBHOOK_URL}</code>
          <button onClick={()=>copy(WEBHOOK_URL,"url")} className="p-2 hover:bg-white/5 rounded text-gray-400">{copied==="url"?<Check className="w-4 h-4 text-green-400"/>:<Copy className="w-4 h-4"/>}</button>
        </div>
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4"><Zap className="w-5 h-5 text-yellow-400"/><h2 className="font-semibold">Indicators &amp; PineScript</h2></div>
        <div className="space-y-3">{indicators.map(ind=><div key={ind.name} className="flex items-center justify-between bg-[#0a0a0f] rounded-lg p-3 border border-[#1e1e2e]"><div><div className="text-sm font-medium">{ind.label}</div><div className="text-xs text-gray-500 mt-0.5">{Object.entries(ind.params).map(([k,v])=>`${k}=${v}`).join(", ")}</div></div><button onClick={()=>copy(`{"action":"BUY","symbol":"BTCUSDT","indicator":"${ind.name}","indicator_value":0,"confidence":0.8}`,ind.name)} className="px-3 py-1.5 text-xs rounded-lg bg-blue-600/20 text-blue-400 hover:bg-blue-600/30">{copied===ind.name?"Copied!":"Copy"}</button></div>)}</div>
      </div>

      {social && (
        <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
          <div className="flex items-center gap-3 mb-4"><Globe className="w-5 h-5 text-purple-400"/><h2 className="font-semibold">Social &amp; Sentiment</h2></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-[#0a0a0f] rounded-lg p-3 text-center"><div className="text-xs text-gray-500 mb-1">Fear &amp; Greed</div><div className={`text-2xl font-bold ${social.fear_greed>60?"text-green-400":social.fear_greed<40?"text-red-400":"text-yellow-400"}`}>{social.fear_greed}</div><div className="text-xs text-gray-500 capitalize">{social.fear_greed_label}</div></div>
            <div className="bg-[#0a0a0f] rounded-lg p-3 text-center"><div className="text-xs text-gray-500 mb-1">Composite</div><div className="text-2xl font-bold text-blue-400">{(social.composite*100).toFixed(0)}%</div></div>
            <div className="bg-[#0a0a0f] rounded-lg p-3 text-center"><div className="text-xs text-gray-500 mb-1">Recommendation</div><div className="text-lg font-bold text-purple-400 capitalize">{social.recommendation}</div></div>
          </div>
        </div>
      )}
    </div>
  );
}
