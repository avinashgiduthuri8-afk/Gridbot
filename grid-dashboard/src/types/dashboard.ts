export type NavigationTab =
  | 'overview'
  | 'scanner'
  | 'sectors'
  | 'signals'
  | 'backtest';

export type StatusType =
  | 'active'
  | 'paused'
  | 'stopped'
  | 'error'
  | 'success'
  | 'warning'
  | 'paper'
  | 'live'
  | 'real'
  | 'filled'
  | 'open'
  | 'cancelled'
  | 'info'
  | 'default';

export interface MetricData {
  title: string;
  value: string;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
  subtext?: string;
  accentColor?: string;
}

export interface TableColumn<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  width?: string;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  data: T[];
  emptyMessage?: string;
  keyExtractor: (row: T) => string;
}

/* ==========================================================================
   Indian Stock Market Scanner Schemas (PROJECT-BETA)
   ========================================================================== */

export interface MarketRegimeResponse {
  regime: string;
  nifty_50_change: number;
  nifty_bank_change: number;
  vix_value: number;
  vix_change: number;
  vix_status: string;
  nifty_trend: string;
  bank_trend: string;
  regime_score: number;
  long_confidence_multiplier: number;
  summary: string;
}

export interface SectorItem {
  sector: string;
  index_symbol: string;
  change_pct_1d: number;
  change_pct_5d: number;
  change_pct_20d: number;
  relative_strength: number;
  momentum_rank: number;
  status: 'LEADING' | 'IMPROVING' | 'WEAKENING' | 'LAGGING' | string;
}

export interface SectorMatrixResponse {
  leading_sectors: string[];
  improving_sectors: string[];
  lagging_sectors: string[];
  sectors: SectorItem[];
}

export interface ScoreBreakdown {
  technical_trend: number;
  momentum: number;
  volume: number;
  price_action: number;
  multi_timeframe: number;
  market_regime: number;
  sector_strength: number;
  news_sentiment: number;
  total_score: number;
}

export interface RiskRewardPlanResponse {
  symbol: string;
  entry_price: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  risk_amount: number;
  reward_amount: number;
  risk_percentage: number;
  reward_percentage: number;
  rr_ratio: number;
  is_acceptable: boolean;
  rejection_reason?: string;
}

export interface ScoredSignalResponse {
  symbol: string;
  signal_type: 'BREAKOUT' | 'PULLBACK' | 'MOMENTUM_CONTINUATION' | 'REVERSAL' | string;
  strength: 'VERY_STRONG' | 'STRONG' | 'VALID' | 'WATCHLIST' | 'REJECT' | string;
  total_score: number;
  breakdown: ScoreBreakdown;
  risk_reward: RiskRewardPlanResponse;
  confidence?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  lifecycle_state?: string;
  setup_reason?: string;
  confirmation_reason?: string;
  sector: string;
  sector_rank: number;
  market_regime: string;
  timeframes_summary: string;
  rationale: string[];
  rejection_risks?: string[];
  timestamp: string;
  is_tradable: boolean;
}

export interface SessionInfo {
  current_time_ist: string;
  session_state: string;
  is_market_open: boolean;
  is_trading_day: boolean;
  is_holiday: boolean;
  is_weekend: boolean;
  valid_signal_window: boolean;
}

export interface ScanResponse {
  timestamp: string;
  session_info: SessionInfo;
  regime: MarketRegimeResponse;
  total_scanned: number;
  total_passed_liquidity: number;
  top_signals: ScoredSignalResponse[];
  watchlist: ScoredSignalResponse[];
  scan_duration_seconds: number;
}

export interface BacktestOutcomeResponse {
  symbol: string;
  signal_type: string;
  score: number;
  status: 'HIT_T1' | 'HIT_T2' | 'STOPPED_OUT' | 'EXPIRED' | string;
  mfe_pct: number;
  mae_pct: number;
  realized_pnl_pct: number;
  holding_bars: number;
  exit_price: number;
  entry_price: number;
  stop_loss: number;
  target_1: number;
}

export interface BacktestReportResponse {
  universe: string;
  total_signals: number;
  winning_signals: number;
  losing_signals: number;
  expired_signals: number;
  win_rate_pct: number;
  profit_factor: number;
  avg_return_pct: number;
  avg_mfe_pct: number;
  avg_mae_pct: number;
  max_drawdown_pct: number;
  avg_holding_bars: number;
  by_regime: Record<string, { count: number; win_rate: number; avg_return: number }>;
  by_setup: Record<string, { count: number; win_rate: number; avg_return: number }>;
  outcomes: BacktestOutcomeResponse[];
}

export interface SignalPerformanceStats {
  total_signals: number;
  winning_signals: number;
  losing_signals: number;
  win_rate_pct: number;
  avg_rr: number;
  avg_mfe: number;
  avg_mae: number;
  avg_return_pct: number;
}

export interface HealthResponse {
  status: string;
  database_connected: boolean;
}
