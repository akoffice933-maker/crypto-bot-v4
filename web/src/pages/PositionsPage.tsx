export default function PositionsPage() {
  const positions = [
    { pair: "BTCUSDT", dir: "LONG", entry: 65000, current: 65400, pnl: 200, sl: 64500, tp: 66000, strategy: "sweep", age: "2h 15m" },
    { pair: "ETHUSDT", dir: "SHORT", entry: 3400, current: 3350, pnl: 150, sl: 3450, tp: 3300, strategy: "bounce", age: "45m" },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Positions</h1>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">Close All LONG</button>
          <button className="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">Close All SHORT</button>
        </div>
      </div>

      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-left border-b border-[#1e1e2e] bg-[#0d0d14]">
              <th className="py-3 px-4 font-normal">Pair</th>
              <th className="py-3 px-4 font-normal">Side</th>
              <th className="py-3 px-4 font-normal">Entry</th>
              <th className="py-3 px-4 font-normal">Current</th>
              <th className="py-3 px-4 font-normal">P&L</th>
              <th className="py-3 px-4 font-normal">SL</th>
              <th className="py-3 px-4 font-normal">TP</th>
              <th className="py-3 px-4 font-normal">Strategy</th>
              <th className="py-3 px-4 font-normal">Age</th>
              <th className="py-3 px-4 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => (
              <tr key={i} className="border-b border-[#1e1e2e]/50 hover:bg-white/5">
                <td className="py-3 px-4 font-medium">{p.pair}</td>
                <td className={`py-3 px-4 font-medium ${p.dir === "LONG" ? "text-green-400" : "text-red-400"}`}>{p.dir}</td>
                <td className="py-3 px-4">${p.entry.toLocaleString()}</td>
                <td className="py-3 px-4">${p.current.toLocaleString()}</td>
                <td className={`py-3 px-4 font-medium ${p.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                  ${p.pnl.toLocaleString()} ({((p.pnl / (p.entry * 0.1)) * 100).toFixed(1)}%)
                </td>
                <td className="py-3 px-4">${p.sl.toLocaleString()}</td>
                <td className="py-3 px-4">${p.tp.toLocaleString()}</td>
                <td className="py-3 px-4 capitalize text-gray-400">{p.strategy}</td>
                <td className="py-3 px-4 text-gray-500">{p.age}</td>
                <td className="py-3 px-4">
                  <button className="text-xs text-red-400 hover:underline">Close</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
