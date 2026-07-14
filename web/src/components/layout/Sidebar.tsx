import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, CandlestickChart, ArrowLeftRight, Target, Shield,
  BarChart3, Tv, Settings, Activity, ScrollText, Radio, PlayCircle
} from "lucide-react";
import { useAppStore } from "../../store/appStore";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/positions", label: "Positions", icon: CandlestickChart },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/strategies", label: "Strategies", icon: Target },
  { to: "/risk", label: "Risk", icon: Shield },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/tradingview", label: "TradingView", icon: Tv },
  { to: "/config", label: "Config", icon: Settings },
  { to: "/monitor", label: "Monitor", icon: Activity },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/settings", label: "Settings", icon: Radio },
];

const linkCls = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
    isActive
      ? "bg-blue-600/20 text-blue-400 font-medium"
      : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
  }`;

export function Sidebar() {
  const { sidebarOpen, toggleSidebar, botRunning, botMode } = useAppStore();

  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-[#0d0d14] border-r border-[#1e1e2e] z-40 transition-all duration-200 flex flex-col ${
        sidebarOpen ? "w-60" : "w-16"
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-14 border-b border-[#1e1e2e]">
        <PlayCircle className="w-6 h-6 text-blue-500 shrink-0" />
        {sidebarOpen && (
          <span className="font-bold text-sm whitespace-nowrap">
            Crypto Bot <span className="text-blue-400">v5</span>
          </span>
        )}
      </div>

      {/* Status */}
      <div className={`px-4 py-3 border-b border-[#1e1e2e] ${sidebarOpen ? "" : "flex justify-center"}`}>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              botRunning ? "bg-green-500 animate-pulse" : "bg-gray-500"
            }`}
          />
          {sidebarOpen && (
            <span className="text-xs text-gray-400">
              {botRunning ? `${botMode}` : "Stopped"}
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={linkCls}>
            <Icon className="w-5 h-5 shrink-0" />
            {sidebarOpen && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Toggle */}
      <button
        onClick={toggleSidebar}
        className="h-10 border-t border-[#1e1e2e] text-gray-500 hover:text-gray-300 text-xs flex items-center justify-center"
      >
        {sidebarOpen ? "◀" : "▶"}
      </button>
    </aside>
  );
}
