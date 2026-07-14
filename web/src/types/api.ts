export interface PortfolioState {
  balance: number;
  equity: number;
  open_positions_count: number;
  daily_pnl: number;
  weekly_pnl: number;
  monthly_pnl: number;
  total_drawdown_pct: number;
  recovery_mode: boolean;
  positions: Record<string, Position>;
}

export interface Position {
  direction: "LONG" | "SHORT";
  entry_price: number;
  size: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  current_pnl: number;
  strategy: string;
}

export interface Trade {
  trade_id: string;
  timestamp: string;
  pair: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  size: number;
  pnl: number;
  fees: number;
  strategy: string;
  confidence: number;
}

export interface AnalyticsMetrics {
  total_trades: number;
  wins: number;
  losses: number;
  winrate: number;
  profit_factor: number;
  expectancy: number;
  avg_win: number;
  avg_loss: number;
  total_pnl: number;
  total_fees: number;
  sharpe_ratio: number;
  calmar_ratio: number;
  recovery_factor: number;
  avg_mae: number;
  avg_mfe: number;
  avg_slippage: number;
  max_drawdown: number;
  strategy_breakdown: Record<string, StrategyMetrics>;
}

export interface StrategyMetrics {
  count: number;
  winrate: number;
  total_pnl: number;
  profit_factor: number | string;
}

export interface HealthStatus {
  status: "healthy" | "warning" | "critical";
  last_check: string;
  data_latency_ms: number;
  feature_calc_time_ms: number;
  cpu_pct: number;
  memory_mb: number;
  api_errors_per_min: number;
  api_retry_pct: number;
  order_placement_time_ms: number;
  websocket_connected: boolean;
}

export interface UptimeMetrics {
  hours: number;
  snapshots: number;
  availability_pct: number;
  healthy_pct: number;
  warning_pct: number;
  critical_pct: number;
}

export interface StrategyConfig {
  name: string;
  enabled: boolean;
  wick_ratio: number;
  volume_multiplier: number;
  tolerance: number;
  min_rr: number;
  sl_atr_mult?: number;
  tp_min?: number;
  tp_max?: number;
  metrics?: StrategyMetrics;
}

export interface LearningStatus {
  ewma_expected_return: number;
  strategies: Record<string, { expected_winrate: number; std: number; ci_lower: number; ci_upper: number }>;
  trade_count: number;
}

export interface ExecutionQuality {
  avg_slippage: number;
  avg_slippage_pct: number;
  avg_latency_ms: number;
  fill_rate: number;
  cancel_rate: number;
  partial_rate: number;
  total_executions: number;
}

export interface BotStatus {
  running: boolean;
  mode: string;
  version: string;
  uptime_seconds: number;
  websocket: boolean;
}

export interface WSMessage {
  topic: string;
  data: Record<string, unknown>;
  timestamp: string;
  event_id: string;
}

export interface AlertRecord {
  id: string;
  symbol: string;
  action: string;
  timestamp: string;
  processed: boolean;
  has_signal: boolean;
}

export interface IndicatorInfo {
  name: string;
  description: string;
  params: Record<string, unknown>;
  alert_condition: string;
}

export interface SocialSignals {
  sentiment_score: number;
  trust_score: number;
  fear_greed: number;
  fear_greed_label: string;
  composite: number;
  recommendation: string;
  asset: string;
}

export interface DrawdownLimits {
  daily: number;
  weekly: number;
  monthly: number;
  total: number;
}

export interface RiskParams {
  max_risk_per_trade: number;
  max_positions: number;
  max_correlation: number;
  max_exposure: number;
  stop_multipliers: Record<string, number>;
  drawdown_limits: DrawdownLimits;
  recovery_threshold: number;
  recovery_exit_threshold: number;
  recovery_min_wins: number;
  recovery_mode: boolean;
  recovery_consecutive_wins: number;
}
