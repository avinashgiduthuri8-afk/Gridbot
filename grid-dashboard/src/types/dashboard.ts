export type NavigationTab =
  | 'overview'
  | 'active-grids'
  | 'positions'
  | 'orders'
  | 'trade-history'
  | 'analytics'
  | 'risk'
  | 'settings';

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
   Backend API Response Schemas
   ========================================================================== */

export interface HealthResponse {
  status: string;
  database_connected: boolean;
}

export interface GridResponse {
  grid_id: string;
  symbol: string;
  status: string;
  mode: string;
  entry_price: number;
  base_investment: number;
  dip_buy_amount: number;
  dip_percentage: number;
  profit_sell_amount: number;
  profit_percentage: number;
  max_levels: number;
  stop_loss_percentage: number;
  current_level: number;
  total_quantity: number;
  total_investment: number;
  average_entry_price: number;
  last_buy_price: number;
  next_buy_price: number;
  next_sell_price: number;
  realized_profit: number;
  completed_cycles: number;
  trailing_enabled: boolean;
  trailing_percentage?: number | null;
  trailing_peak_price?: number | null;
  created_at: string;
  updated_at: string;
}

export interface GridListResponse {
  grids: GridResponse[];
  count: number;
}

export interface CreateGridRequest {
  symbol: string;
  entry_price?: number;
  base_investment: number;
  dip_buy_amount: number;
  dip_percentage: number;
  profit_sell_amount: number;
  profit_percentage: number;
  max_levels: number;
  stop_loss_percentage: number;
  mode?: 'paper' | 'real';
  trailing_enabled?: boolean;
  trailing_percentage?: number | null;
}

export interface CreateGridResponse {
  grid_id: string;
  symbol: string;
  mode: string;
  status: string;
  message: string;
}

export interface ManualBuyRequest {
  inr_amount: number;
}

export interface ManualSellRequest {
  inr_amount?: number | null;
}

export interface ManualTradeResponse {
  success: boolean;
  grid_id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  inr_amount: number;
  mode: string;
  order_id?: string | null;
  message: string;
}

export interface GridActionResponse {
  success: boolean;
  grid_id: string;
  action: string;
  message: string;
}

export interface EmergencyStopRequest {
  enabled: boolean;
}

export interface EmergencyStopResponse {
  emergency_stop: boolean;
  message: string;
}

export interface PositionResponse {
  grid_id: string;
  symbol: string;
  status: string;
  mode: string;
  quantity: number;
  average_entry_price: number;
  invested: number;
  current_price?: number | null;
  realized_pnl: number;
  unrealized_pnl: number;
  combined_pnl: number;
  current_level: number;
  max_levels: number;
  trailing_enabled: boolean;
  trailing_peak_price?: number | null;
}

export interface PositionListResponse {
  positions: PositionResponse[];
  count: number;
}

export interface OrderResponse {
  order_id: string;
  grid_id: string;
  exchange_order_id?: string | null;
  symbol: string;
  side: string;
  order_type: string;
  price: number;
  quantity: number;
  filled_quantity: number;
  filled_price: number;
  status: string;
  fee: number;
  reconciliation_status: string;
  created_at: string;
  updated_at: string;
}

export interface OrderListResponse {
  orders: OrderResponse[];
  count: number;
}

export interface TradeResponse {
  trade_id: string;
  grid_id: string;
  order_id: string;
  symbol: string;
  side: string;
  price: number;
  quantity: number;
  investment_inr: number;
  fee: number;
  pnl: number;
  executed_at: string;
}

export interface TradeHistoryResponse {
  trades: TradeResponse[];
  count: number;
}

export interface PortfolioResponse {
  total_realized: number;
  total_unrealized: number;
  total_invested: number;
  combined_total: number;
  portfolio_return_pct: number;
  active_grid_count: number;
  paused_grid_count: number;
  completed_grid_count: number;
  stopped_grid_count: number;
}

export interface AnalyticsResponse {
  total_buys: number;
  total_sells: number;
  total_dust_writeoffs: number;
  total_realized_profit: number;
  win_rate_pct: number;
  max_drawdown_pct: number;
  profit_factor?: number | null;
  completed_cycles: number;
}

export interface RiskSettingsResponse {
  max_total_capital: number;
  max_capital_per_coin: number;
  max_simultaneous_grids: number;
  min_wallet_balance: number;
  daily_loss_limit: number;
}

export interface SettingsResponse {
  risk: RiskSettingsResponse;
  order_poll_interval_seconds: number;
  price_poll_interval_seconds: number;
  daily_summary_interval_seconds: number;
  monitor_interval_seconds?: number | null;
  emergency_stop_active: boolean;
  backup_enabled: boolean;
  webhook_enabled: boolean;
  grid_defaults?: Record<string, unknown> | null;
}
