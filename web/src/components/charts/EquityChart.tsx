import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Area, AreaChart } from "recharts";

const mockData = Array.from({ length: 50 }, (_, i) => ({
  time: i,
  equity: 10000 + i * 40 + Math.sin(i / 5) * 200,
  drawdown: Math.max(0, -Math.sin(i / 5) * 100),
}));

export function EquityChart() {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={mockData}>
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
        <XAxis dataKey="time" hide />
        <YAxis hide />
        <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#equityGrad)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function PnLChart() {
  const data = Array.from({ length: 30 }, (_, i) => ({
    day: i + 1,
    pnl: (Math.random() - 0.45) * 500,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
        <XAxis dataKey="day" hide />
        <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
          {data.map((entry, i) => (
            <rect key={i} fill={entry.pnl >= 0 ? "#22c55e" : "#ef4444"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
