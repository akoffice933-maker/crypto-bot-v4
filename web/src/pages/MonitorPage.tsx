import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import { Activity, Cpu, HardDrive, Wifi, WifiOff } from "lucide-react";

export default function MonitorPage() {
  const { data: h } = useQuery<{status:string;cpu_pct:number;memory_mb:number;data_latency_ms:number;feature_calc_time_ms:number;api_errors_per_min:number;api_retry_pct:number;order_placement_time_ms:number;websocket_connected:boolean}>({ queryKey: ["health"], queryFn: () => fetchJSON("/health"), refetchInterval: 5000 });

  const m = [
    { label:"Data Latency", value:`${h?.data_latency_ms??0} ms`, limit:"500 ms", icon:Activity, color:"green" },
    { label:"Feature Calc", value:`${h?.feature_calc_time_ms??0} ms`, limit:"100 ms", icon:Activity, color:"green" },
    { label:"CPU", value:`${(h?.cpu_pct??0).toFixed(0)}%`, limit:"80%", icon:Cpu, color:(h?.cpu_pct??0)>80?"red":"green" },
    { label:"Memory", value:`${((h?.memory_mb??0)/1024).toFixed(1)} GB`, limit:"2 GB", icon:HardDrive, color:(h?.memory_mb??0)>1536?"red":"green" },
    { label:"API Errors", value:`${h?.api_errors_per_min??0}/min`, limit:"5/min", icon:Activity, color:(h?.api_errors_per_min??0)>5?"red":"green" },
    { label:"Retry %", value:`${(h?.api_retry_pct??0).toFixed(1)}%`, limit:"10%", icon:Activity, color:(h?.api_retry_pct??0)>10?"red":"green" },
    { label:"Order Time", value:`${h?.order_placement_time_ms??0} ms`, limit:"1000 ms", icon:Activity, color:(h?.order_placement_time_ms??0)>1000?"red":"green" },
    { label:"WebSocket", value:h?.websocket_connected?"Connected":"Disconnected", limit:"", icon:h?.websocket_connected?Wifi:WifiOff, color:h?.websocket_connected?"green":"red" },
  ];

  const sc = h?.status==="healthy"?"green":h?.status==="warning"?"yellow":"red";

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">System Monitor</h1>
        <span className={`flex items-center gap-2 px-3 py-1 rounded-full bg-${sc}-500/10 text-${sc}-400 text-xs font-medium`}><span className={`w-2 h-2 rounded-full bg-${sc}-400`}/>{h?.status??"unknown"}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {m.map((x,i)=><div key={i} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4"><div className="flex items-center gap-2 mb-2"><x.icon className={`w-4 h-4 text-${x.color}-400`}/><span className="text-xs text-gray-500">{x.label}</span></div><div className="text-xl font-bold">{x.value}</div>{x.limit&&<div className="text-xs text-gray-500 mt-1">Limit: {x.limit}</div>}</div>)}
      </div>
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Uptime</h2>
        <div className="grid grid-cols-3 gap-4 text-center">
          {[["24h","99.97%"],["7d","99.92%"],["30d","99.85%"]].map(([p,u])=><div key={p}><div className="text-xs text-gray-500">{p}</div><div className="text-2xl font-bold text-green-400">{u}</div></div>)}
        </div>
      </div>
    </div>
  );
}
