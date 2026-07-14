import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "../api/client";
import { Pause, Play, Search } from "lucide-react";

type LogEntry = {ts:string;level:string;service:string;message:string};

export default function LogsPage() {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const { data } = useQuery<{logs:LogEntry[];total:number}>({ queryKey: ["logs"], queryFn: () => fetchJSON("/api/logs"), refetchInterval: paused ? false : 3000 });
  const logs = data?.logs ?? [];
  const filtered = logs.filter(l => {
    if (filter !== "ALL" && l.level !== filter) return false;
    if (search && !l.message.toLowerCase().includes(search.toLowerCase()) && !l.service.includes(search)) return false;
    return true;
  });
  const cm: Record<string,string> = {DEBUG:"text-gray-500",INFO:"text-blue-400",WARNING:"text-yellow-400",ERROR:"text-red-400",CRITICAL:"text-red-500 font-bold"};

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Logs</h1>
        <button onClick={() => setPaused(!paused)} className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${paused?"bg-yellow-500/10 text-yellow-400":"bg-green-500/10 text-green-400"}`}>{paused?<Play className="w-4 h-4"/>:<Pause className="w-4 h-4"/>}{paused?"Paused":"Live"}</button>
      </div>
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]"><Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search logs..." className="w-full bg-[#12121a] border border-[#1e1e2e] rounded-lg py-2 pl-9 pr-3 text-sm text-gray-200 placeholder-gray-600"/></div>
        {["ALL","DEBUG","INFO","WARNING","ERROR","CRITICAL"].map(lv=><button key={lv} onClick={()=>setFilter(lv)} className={`px-3 py-1.5 rounded-lg text-xs font-medium ${filter===lv?"bg-blue-600/20 text-blue-400 border border-blue-500/30":"bg-[#12121a] border border-[#1e1e2e] text-gray-400"}`}>{lv}</button>)}
      </div>
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
        <div className="overflow-auto max-h-[60vh] font-mono text-xs">
          {filtered.map((l,i)=><div key={i} className="flex gap-3 px-4 py-1.5 hover:bg-white/[0.02] border-b border-[#1e1e2e]/30"><span className="text-gray-600 shrink-0 w-24">{l.ts?.slice(11,23)??""}</span><span className={`shrink-0 w-16 ${cm[l.level]??"text-gray-400"}`}>{l.level}</span><span className="text-purple-400 shrink-0 w-32">{l.service}</span><span className="text-gray-300">{l.message}</span></div>)}
          {filtered.length===0&&<div className="p-4 text-center text-gray-500">No log entries</div>}
        </div>
      </div>
    </div>
  );
}
