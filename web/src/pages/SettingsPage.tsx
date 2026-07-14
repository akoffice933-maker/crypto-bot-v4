import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJSON, postJSON } from "../api/client";
import { Radio, Play, Square, RefreshCw, Globe, Bell, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useAppStore } from "../store/appStore";

export default function SettingsPage() {
  const [sk, setSk] = useState(false);
  const qc = useQueryClient();
  const { setBotRunning } = useAppStore();

  const { data: bs } = useQuery<{running:boolean;mode:string;version:string}>({ queryKey: ["bot-status"], queryFn: () => fetchJSON("/api/bot/status"), refetchInterval: 10000 });
  const { data: st } = useQuery<{exchange_id:string;testnet:boolean;api_key_configured:boolean;notifications:Record<string,boolean>}>({ queryKey: ["settings"], queryFn: () => fetchJSON("/api/settings"), refetchInterval: 60000 });

  const mStart = useMutation({ mutationFn: () => postJSON("/api/bot/start"), onSuccess: () => { setBotRunning(true); qc.invalidateQueries({ queryKey: ["bot-status"] }); } });
  const mStop = useMutation({ mutationFn: () => postJSON("/api/bot/stop"), onSuccess: () => { setBotRunning(false); qc.invalidateQueries({ queryKey: ["bot-status"] }); } });
  const mRestart = useMutation({ mutationFn: () => postJSON("/api/bot/restart"), onSuccess: () => qc.invalidateQueries({ queryKey: ["bot-status"] }) });

  const running = bs?.running ?? false;

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Settings</h1>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3"><Radio className="w-5 h-5 text-blue-400"/><div><h2 className="font-semibold">Bot Control</h2><p className="text-xs text-gray-500">Status: {running?<span className="text-green-400">Running</span>:<span className="text-gray-400">Stopped</span>}</p></div></div>
          <div className="flex gap-2">
            {!running ? <button onClick={()=>mStart.mutate()} disabled={mStart.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700"><Play className="w-4 h-4"/> Start</button>
            : <><button onClick={()=>mStop.mutate()} disabled={mStop.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700"><Square className="w-4 h-4"/> Stop</button>
            <button onClick={()=>mRestart.mutate()} disabled={mRestart.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-yellow-600/20 text-yellow-400 text-sm hover:bg-yellow-600/30"><RefreshCw className="w-4 h-4"/> Restart</button></>}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          {[["Version",bs?.version??"5.0.0"],["Mode",bs?.mode??"unknown"],["Exchange",st?.exchange_id??"binance"]].map(([l,v])=><div key={l as string} className="bg-[#0a0a0f] rounded-lg p-3"><div className="text-xs text-gray-500">{l as string}</div><div className="text-sm font-medium mt-0.5">{v}</div></div>)}
        </div>
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4"><Globe className="w-5 h-5 text-green-400"/><h2 className="font-semibold">Exchange</h2><span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400">{st?.testnet?"Testnet":"Production"}</span></div>
        <div className="space-y-3">
          <Row label="Exchange ID" value={st?.exchange_id??"binance"}/>
          <Row label="API Key" value={st?.api_key_configured?(sk?"Configured":"••••••••"):"Not set"} action={<button onClick={()=>setSk(!sk)} className="text-gray-400">{sk?<EyeOff className="w-4 h-4"/>:<Eye className="w-4 h-4"/>}</button>}/>
          <Row label="Testnet" value={st?.testnet?"Enabled":"Disabled"}/>
        </div>
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-5">
        <div className="flex items-center gap-3 mb-4"><Bell className="w-5 h-5 text-yellow-400"/><h2 className="font-semibold">Notifications</h2></div>
        {["Telegram","Email","Webhook"].map(ch=><div key={ch} className="flex items-center justify-between py-2 border-t border-[#1e1e2e]"><div><div className="text-sm">{ch}</div><div className="text-xs text-gray-500">{ch==="Telegram"?"Bot Token + Chat ID":ch==="Email"?"Alerts for critical events":"External HTTP endpoint"}</div></div><div className="flex items-center gap-2"><span className="text-xs text-gray-500">Not configured</span><button className="text-xs text-blue-400 hover:underline">Configure</button></div></div>)}
      </div>
    </div>
  );
}

function Row({label,value,action}:{label:string;value:string;action?:React.ReactNode}) {
  return <div className="flex items-center justify-between bg-[#0a0a0f] rounded-lg px-3 py-2 border border-[#1e1e2e]"><span className="text-sm text-gray-400">{label}</span><div className="flex items-center gap-2"><span className="text-sm font-mono text-gray-300">{value}</span>{action}</div></div>;
}
