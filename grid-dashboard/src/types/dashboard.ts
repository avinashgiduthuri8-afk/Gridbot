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
  | 'paper'
  | 'live'
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
