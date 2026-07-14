export default function TradesPage() {
  const trades = [
    { time: "14:32", pair: "BTCUSDT", dir: "LONG", entry: 65000, exit: 65400, pnl: 200, pnlPct: 0.62, strategy: "sweep", duration: "1h 45m", result: "win" },
    { time: "13:15", pair: "ETHUSDT", dir: "SHORT", entry: 3400, exit: 3380, pnl: 60, pnlPct: 0.59, strategy: "bounce", duration: "35m", result: "win" },
    { time: "11:48", pair: "SOLUSDT", dir: "LONG", entry: 142, exit: 138, pnl: -40, pnlPct: -2.82, strategy: "breakout", duration: "3h 10m", result: "loss" },
    { time: "10:22", pair: "BTCUSDT", dir: "LONG", entry: 64800, exit: 65100, pnl: 150, pnlPct: 0.46, strategy: "sweep", duration: "2h 5m", result: "win" },
    { time: "09:05", pair: "BNBUSDT", dir: "LONG", entry: 580, exit: 575, pnl: -50, pnlPct: -0.86, strategy: "bounce", duration: "1h 20m", result: "loss" },
    { time: "08:30", pair: "ETHUSDT", dir: "LONG", entry: 3350, exit: 3420, pnl: 210, pnlPct: 2.09, strategy: "sweep", duration: "4h 15m", result: "win" },
    { time: "07:12", pair: "SOLUSDT", dir: "SHORT", entry: 145, exit: 140, pnl: 50, pnlPct: 3.45, strategy: "bounce", duration: "1h 50m", result: "win" },
    { time: "06:45", pair: "BTCUSDT", dir: "SHORT", entry: 65200, exit: 65400, pnl: -100, pnlPct: -0.31, strategy: "breakout", duration: "45m", result: "loss" },
  ];

  const wins = trades.filter((t) => t.result === "win").length;
  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const winCount = trades.filter((t) => t.result === "win");
  const lossCount = trades.filter((t) => t.result === "loss");
  const totalProfit = winCount.reduce((s, t) => s + t.pnl, 0);
  const totalLoss = Math.abs(lossCount.reduce((s, t) => s + t.pnl, 0));

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">Trade History</h1>

      {/* Summary Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ["Trades", trades.length],
          ["Winrate", `${((wins / trades.length) * 100).toFixed(1)}%`],
          ["Total P&L", `$${totalPnl}`],
          ["Profit Factor", (totalLoss > 0 ? (totalProfit / totalLoss) : "∞").toString()],
          ["Avg P&L", `$${(totalPnl / trades.length).toFixed(0)}`],
        ].map(([label, val]) => (
          <div key={label} className="bg-[#12121a] rounded-xl border border-[#1e1e2e] p-3">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-lg font-bold mt-0.5">{val}</div>
          </div>
        ))}
      </div>

      {/* Trades Table */}
      <div className="bg-[#12121a] rounded-xl border border-[#1e1e2e] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-left border-b border-[#1e1e2e] bg-[#0d0d14]">
              <th className="py-3 px-4 font-normal">Time</th>
              <th className="py-3 px-4 font-normal">Pair</th>
              <th className="py-3 px-4 font-normal">Side</th>
              <th className="py-3 px-4 font-normal">Entry</th>
              <th className="py-3 px-4 font-normal">Exit</th>
              <th className="py-3 px-4 font-normal">P&L</th>
              <th className="py-3 px-4 font-normal">P&L%</th>
              <th className="py-3 px-4 font-normal">Strategy</th>
              <th className="py-3 px-4 font-normal">Duration</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-[#1e1e2e]/50 hover:bg-white/5">
                <td className="py-3 px-4 text-gray-400">{t.time}</td>
                <td className="py-3 px-4 font-medium">{t.pair}</td>
                <td className={`py-3 px-4 ${t.dir === "LONG" ? "text-green-400" : "text-red-400"}`}>{t.dir}</td>
                <td className="py-3 px-4">${t.entry.toLocaleString()}</td>
                <td className="py-3 px-4">${t.exit.toLocaleString()}</td>
                <td className={`py-3 px-4 font-medium ${t.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {t.pnl >= 0 ? "+" : ""}${t.pnl}
                </td>
                <td className={`py-3 px-4 ${t.pnlPct >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {t.pnlPct >= 0 ? "+" : ""}{t.pnlPct.toFixed(2)}%
                </td>
                <td className="py-3 px-4 capitalize text-gray-400">{t.strategy}</td>
                <td className="py-3 px-4 text-gray-500">{t.duration}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
