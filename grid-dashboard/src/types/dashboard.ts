export type NavigationTab =
  | 'overview'
  | 'scanner'
  | 'sectors'
  | 'signals'
  | 'backtest'
  | 'bots';

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
  iei_score?: number;
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

export interface StrategyMetadata {
  id: string;
  name: string;
  description: string;
  default_t1_rr: number;
  default_t2_rr: number;
}

export interface StrategyBacktestTrade {
  trade_id: string;
  symbol: string;
  strategy: string;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  exit_reason: 'HIT_T1' | 'HIT_T2' | 'STOPPED_OUT' | 'TRAILING_SL' | 'TIMEOUT' | string;
  shares: number;
  pnl_amount: number;
  pnl_pct: number;
  r_multiple: number;
  holding_days: number;
  is_win: boolean;
  stop_loss: number;
  target_1: number;
  target_2: number;
}

export interface EquityCurvePoint {
  date: string;
  portfolio_value: number;
  benchmark_value: number;
  drawdown_pct: number;
}

export interface StrategyBacktestResponse {
  symbol: string;
  strategy: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  net_pnl_amount: number;
  net_pnl_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  expectancy_r: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  avg_winner_amount: number;
  avg_loser_amount: number;
  max_win_streak: number;
  max_loss_streak: number;
  avg_holding_days: number;
  equity_curve: EquityCurvePoint[];
  trades: StrategyBacktestTrade[];
}

export interface StrategyBacktestRequest {
  symbol?: string;
  universe?: string;
  strategy?: string;
  lookback_bars?: number;
  initial_capital?: number;
  risk_pct_per_trade?: number;
  target_1_rr?: number;
  target_2_rr?: number;
  use_trailing_sl?: boolean;
  max_holding_bars?: number;
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

export interface CorporateEvent {
  event_type: string;
  date: string;
  description: string;
}

export interface StockInfoResponse {
  symbol: string;
  company_name: string;
  sector: string;
  industry: string;
  isin: string;
  market_cap_category: 'Large Cap' | 'Mid Cap' | 'Small Cap' | string;
  website: string;
  business_summary: string;

  market_cap_cr: number;
  current_price: number;
  high_52w: number;
  low_52w: number;
  stock_pe: number;
  industry_pe: number;
  book_value: number;
  price_to_book: number;
  dividend_yield_pct: number;
  roce_pct: number;
  roe_pct: number;
  debt_to_equity: number;
  interest_coverage: number;
  eps_ttm: number;
  peg_ratio: number;
  free_cash_flow_cr: number;

  delivery_pct: number;
  delivery_quantity: number;
  traded_volume: number;
  upper_circuit: number;
  lower_circuit: number;
  circuit_band_pct: number;
  total_buy_qty: number;
  total_sell_qty: number;
  upcoming_events: CorporateEvent[];

  promoter_holding_pct: number;
  pledged_pct: number;
  fii_holding_pct: number;
  dii_holding_pct: number;
  public_holding_pct: number;
  promoter_trend: 'INCREASING' | 'STABLE' | 'DECREASING' | string;
  last_updated: string;
}

export interface FinancialRatiosResponse {
  symbol: string;
  company_name: string;
  market_cap_cr: number;
  market_cap_category: string;
  current_price: number;
  stock_pe: number;
  industry_pe: number;
  book_value: number;
  price_to_book: number;
  dividend_yield_pct: number;
  roce_pct: number;
  roe_pct: number;
  debt_to_equity: number;
  interest_coverage: number;
  eps_ttm: number;
  peg_ratio: number;
  free_cash_flow_cr: number;
  promoter_holding_pct: number;
  pledged_pct: number;
}

export interface DeliveryInfoResponse {
  symbol: string;
  delivery_pct: number;
  delivery_quantity: number;
  traded_volume: number;
  upper_circuit: number;
  lower_circuit: number;
  circuit_band_pct: number;
  total_buy_qty: number;
  total_sell_qty: number;
  upcoming_events: CorporateEvent[];
}

export interface LedgerStatsResponse {
  total_signals: number;
  winning_signals: number;
  losing_signals: number;
  expired_signals: number;
  active_signals: number;
  win_rate_pct: number;
  total_r_multiple: number;
  profit_factor: number;
  avg_r_per_trade: number;
  avg_mfe_pct: number;
  avg_mae_pct: number;
  setup_breakdown: Record<string, { total: number; wins: number; losses: number; total_r: number }>;
}

export interface BotRegistrationResponse {
  bot_id: string;
  name: string;
  target_broker: string;
  webhook_url: string;
  secret_key: string;
  subscribed_setups: string[];
  min_confidence_score: number;
  is_active: boolean;
  created_at: string;
}

export interface CreateBotRequest {
  name: string;
  target_broker: string;
  webhook_url: string;
  secret_key?: string;
  subscribed_setups: string[];
  min_confidence_score: number;
  is_active: boolean;
}

export interface DispatchReceiptResponse {
  dispatch_id: string;
  signal_id: string;
  bot_id: string;
  timestamp: string;
  status: 'SUCCESS' | 'FAILED' | 'RETRYING' | string;
  response_code: number;
  latency_ms: number;
  error_message?: string | null;
}
