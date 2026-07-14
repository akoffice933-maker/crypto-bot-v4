import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchJSON, postJSON } from "../api/client";
import { FileCode, Save, RotateCcw, Eye } from "lucide-react";

export default function ConfigPage() {
  const [env, setEnv] = useState("paper");
  const [raw, setRaw] = useState(false);

  const { data: cfg } = useQuery<{version:string;pairs:string[];timeframes:string[];mode:string}>({ queryKey: ["config-current"], queryFn: () => fetchJSON("/config/current"), refetchInterval: 30000 });
  const { data: vers } = useQuery<Array<{version:string;hash:string;loaded_at:string}>>({ queryKey: ["config-versions"], queryFn: () => fetchJSON("/config/versions"), refetchInterval: 60000 });

  const mReload = useMutation({ mutationFn: () => postJSON("/api/config/reload"), onSuccess: () => window.location.reload() });

  const envs = [{id:"production",label:"Production",active:false},{id:"paper",label:"Paper",active:true},{id:"backtest",label:"Backtest",active:false}];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Configuration</h1>
        <div className="flex gap-2">
          <button onClick={()=>setRaw(!raw)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs ${raw?"bg-yellow-500/10 text-yellow-400":"bg-blue-600/10 text-blue-400"}`}>{raw?<Eye className="w-3.5 h-3.5"/>:<FileCode className="w-3.5 h-3.5"/>}{raw?"Form Mode":"Raw YAML"}</button>
          <button onClick={()=>mReload.mutate()} disabled={mReload.isPending} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-green-600/10 text-green-400"><Save className="w-3.5 h-3.5"/> {mReload.isPending?"...":"Reload"}</button>
        </div>
      </div>
      <div className="flex gap-2">{envs.map(e=><button key={e.id} onClick={()=>setEnv(e.id)} className={`px-4 py-2 rounded-lg text-sm transition-all ${env===e.id?"bg-blue-600/20 text-blue-400 border border-blue-500/30":"bg-[#12121a] border border-[#1e1e2e] text-gray-400"}`}><div className="font-medium">{e.label}</div></button>)}</div>
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4"><h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Active Config</h2><div className="grid grid-cols-2 gap-3">
        <Row label="Version" value={cfg?.version??"unknown"}/>
        <Row label="Mode" value={cfg?.mode??"unknown"}/>
        <Row label="Pairs" value={(cfg?.pairs??[]).join(", ")}/>
        <Row label="Timeframes" value={(cfg?.timeframes??[]).join(", ")}/>
      </div></div>
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-4">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Version History</h2>
        <div className="space-y-2">{(vers??[{version:"5.0.0",hash:"-",loaded_at:new Date().toISOString()}]).map((v,i)=><div key={i} className="flex items-center justify-between py-2 border-b border-[#1e1e2e]/50 last:border-0"><div className="flex items-center gap-3"><span className="text-sm font-mono text-blue-400">{v.version}</span><span className="text-xs text-gray-500">{v.hash?.slice(0,12)}</span></div><div className="flex items-center gap-3"><span className="text-xs text-gray-500">{v.loaded_at?.slice(0,16)}</span>{i>0&&<button className="flex items-center gap-1 text-xs text-yellow-400"><RotateCcw className="w-3 h-3"/>Rollback</button>}</div></div>)}</div>
      </div>
    </div>
  );
}

function Row({label,value}:{label:string;value:string}){return <div className="flex justify-between items-center bg-[#0a0a0f] rounded-lg px-3 py-2 border border-[#1e1e2e]"><span className="text-sm text-gray-400">{label}</span><span className="text-sm font-medium text-gray-200">{value}</span></div>;}
