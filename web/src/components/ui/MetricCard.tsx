import { cn } from "../../lib/utils";

interface Props {
  label: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon?: React.ReactNode;
  color?: "green" | "red" | "blue" | "yellow" | "gray";
}

const colorMap = {
  green: "text-green-400 border-green-500/20 bg-green-500/5",
  red: "text-red-400 border-red-500/20 bg-red-500/5",
  blue: "text-blue-400 border-blue-500/20 bg-blue-500/5",
  yellow: "text-yellow-400 border-yellow-500/20 bg-yellow-500/5",
  gray: "text-gray-400 border-gray-500/20 bg-gray-500/5",
};

export function MetricCard({ label, value, change, changeLabel, icon, color = "blue" }: Props) {
  const changeSign = change !== undefined ? (change >= 0 ? "+" : "") : "";
  const changeColor = change !== undefined ? (change >= 0 ? "text-green-400" : "text-red-400") : "";

  return (
    <div className={cn("rounded-xl border p-4 animate-fade-in", colorMap[color])}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
        {icon}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {change !== undefined && (
        <div className={cn("text-xs mt-1", changeColor)}>
          {changeSign}{change.toFixed(2)}{changeLabel ?? "%"}
        </div>
      )}
    </div>
  );
}
