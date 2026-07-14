import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAppStore } from "./store/appStore";
import { Layout } from "./components/layout/Layout";
import { useWebSocket } from "./hooks/useWebSocket";
import DashboardPage from "./pages/DashboardPage";
import PositionsPage from "./pages/PositionsPage";
import TradesPage from "./pages/TradesPage";
import StrategiesPage from "./pages/StrategiesPage";
import RiskPage from "./pages/RiskPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import TradingViewPage from "./pages/TradingViewPage";
import ConfigPage from "./pages/ConfigPage";
import MonitorPage from "./pages/MonitorPage";
import LogsPage from "./pages/LogsPage";
import SettingsPage from "./pages/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 3000, retry: 1 } },
});

function WSHandler() {
  const { setBotRunning } = useAppStore();

  useWebSocket((msg) => {
    switch (msg.topic) {
      case "health.changed":
        setBotRunning(msg.data.status === "healthy" || msg.data.status === "warning");
        break;
    }
  });

  return null;
}

export default function App() {
  const { theme } = useAppStore();

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className={theme}>
          <WSHandler />
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="positions" element={<PositionsPage />} />
              <Route path="trades" element={<TradesPage />} />
              <Route path="strategies" element={<StrategiesPage />} />
              <Route path="risk" element={<RiskPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="tradingview" element={<TradingViewPage />} />
              <Route path="config" element={<ConfigPage />} />
              <Route path="monitor" element={<MonitorPage />} />
              <Route path="logs" element={<LogsPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
