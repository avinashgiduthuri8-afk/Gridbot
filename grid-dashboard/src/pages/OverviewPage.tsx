import React, { useState } from 'react';
import { MetricCard } from '../components/common/MetricCard';
import { Card } from '../components/common/Card';
import { Table } from '../components/common/Table';
import { StatusBadge } from '../components/common/StatusBadge';
import { ProgressBar } from '../components/common/ProgressBar';
import { GridDetailModal } from '../components/common/GridDetailModal';
import { formatInr, formatPct } from '../utils/formatters';
import type { TableColumn, GridResponse, StatusType } from '../types/dashboard';
import { DollarSign, Activity, Wallet, ShieldAlert, AlertTriangle, RefreshCw, Eye, Info } from 'lucide-react';
import type { DashboardData } from '../hooks/useDashboardData';

interface OverviewPageProps {
  data: DashboardData;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  data,
  loading,
  error,
  onRefresh,
}) => {
  const { portfolio, settings, health, grids } = data;
  const [selectedGrid, setSelectedGrid] = useState<GridResponse | null>(null);

  const currentInvested = portfolio?.total_invested ?? 0;
  const maxCapital = settings?.risk.max_total_capital ?? 50000;
  const utilizationPct = maxCapital > 0 ? (currentInvested / maxCapital) * 100 : 0;

  // Grid columns for table
  const columns: TableColumn<GridResponse>[] = [
    {
      key: 'symbol',
      header: 'Coin / Symbol',
      render: (grid) => (
        <div>
          <div style={{ fontWeight: 600, color: '#fff' }}>{grid.symbol}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Level {grid.current_level} / {grid.max_levels}
          </div>
        </div>
      ),
    },
    {
      key: 'mode',
      header: 'Mode',
      render: (grid) => (
        <StatusBadge
          status={grid.mode.toLowerCase() as StatusType}
          label={grid.mode.toUpperCase()}
          showDot={false}
        />
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (grid) => (
        <StatusBadge status={grid.status.toLowerCase() as StatusType} />
      ),
    },
    {
      key: 'total_investment',
      header: 'Invested Capital',
      render: (grid) => formatInr(grid.total_investment),
    },
    {
      key: 'realized_profit',
      header: 'Realized P&L',
      align: 'right',
      render: (grid) => (
        <span
          style={{
            color: grid.realized_profit >= 0 ? 'var(--success)' : 'var(--danger)',
            fontWeight: 600,
          }}
        >
          {formatInr(grid.realized_profit)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Inspect',
      align: 'center',
      render: (grid) => (
        <button
          className="action-btn"
          onClick={() => setSelectedGrid(grid)}
          title="Inspect Grid Details"
          style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
        >
          <Eye size={12} />
        </button>
      ),
    },
  ];

  return (
    <div>
      {/* Error Banner State */}
      {error && (
        <Card
          style={{
            padding: '1.25rem 1.5rem',
            marginBottom: '1.5rem',
            background: 'var(--danger-light)',
            borderColor: 'rgba(239, 68, 68, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <AlertTriangle color="var(--danger)" size={24} />
            <div>
              <div style={{ fontWeight: 600, color: '#fff' }}>Backend Connection Issue</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                {error} (Verify FastAPI server is running at http://127.0.0.1:8000)
              </div>
            </div>
          </div>
          <button className="action-btn" onClick={onRefresh}>
            <RefreshCw size={14} />
            <span>Retry Connection</span>
          </button>
        </Card>
      )}

      {/* Metrics Row */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Realized P&L"
          value={formatInr(portfolio?.total_realized)}
          change={formatPct(portfolio?.portfolio_return_pct)}
          trend={
            (portfolio?.portfolio_return_pct ?? 0) > 0
              ? 'up'
              : (portfolio?.portfolio_return_pct ?? 0) < 0
              ? 'down'
              : 'neutral'
          }
          subtext="Lifetime Realized Gains"
          icon={<DollarSign size={20} />}
          accentColor="#10b981"
          loading={loading && !portfolio}
        />
        <MetricCard
          title="Active Grids"
          value={(portfolio?.active_grid_count ?? 0).toString()}
          subtext={`Max Limit: ${settings?.risk.max_simultaneous_grids ?? 5} Grids`}
          icon={<Activity size={20} />}
          accentColor="#6366f1"
          loading={loading && !portfolio}
        />
        <MetricCard
          title="Capital Invested"
          value={formatInr(portfolio?.total_invested)}
          subtext={`Max Cap: ${formatInr(settings?.risk.max_total_capital ?? 50000)}`}
          icon={<Wallet size={20} />}
          accentColor="#06b6d4"
          loading={loading && !portfolio}
        />
        <MetricCard
          title="Risk Exposure"
          value={
            settings?.emergency_stop_active
              ? 'HALTED'
              : `${utilizationPct.toFixed(1)}%`
          }
          change={settings?.emergency_stop_active ? 'EMERGENCY STOP' : 'Safe'}
          trend={settings?.emergency_stop_active ? 'down' : 'neutral'}
          subtext={`Daily Loss Limit ${formatInr(settings?.risk.daily_loss_limit ?? 2000)}`}
          icon={<ShieldAlert size={20} />}
          accentColor="#f59e0b"
          loading={loading && !settings}
        />
      </div>

      {/* Grid Layout Section */}
      <div className="overview-grid-2col">
        {/* Main Recent Grids Table Card */}
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <h2 className="section-title">Active Grid Monitors</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {grids.length} Active / Managed DCA Grids
            </span>
          </div>

          <Table<GridResponse>
            columns={columns}
            data={grids}
            keyExtractor={(grid) => grid.grid_id}
            emptyMessage={
              loading
                ? 'Fetching grid data from FastAPI backend...'
                : 'No active DCA grids currently running in backend database'
            }
          />
        </Card>

        {/* System & Engine Status Sidebar Card */}
        <Card style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="section-header">
            <h2 className="section-title">Portfolio & Engine Health</h2>
            <StatusBadge
              status={health?.status === 'ok' ? 'active' : 'error'}
              label={health?.status === 'ok' ? 'Online' : 'Degraded'}
            />
          </div>

          {/* Capital Utilization Progress */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff', marginBottom: '0.5rem' }}>
              Capital Utilization Gauge
            </div>
            <ProgressBar value={utilizationPct} color="var(--primary)" showLabel />
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
              {formatInr(currentInvested)} invested out of {formatInr(maxCapital)} portfolio cap
            </div>
          </div>

          {/* Grid Status Distribution Pills */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff', marginBottom: '0.65rem' }}>
              Grid Status Breakdown
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              <StatusBadge status="active" label={`Active: ${portfolio?.active_grid_count ?? 0}`} />
              <StatusBadge status="paused" label={`Paused: ${portfolio?.paused_grid_count ?? 0}`} />
              <StatusBadge status="stopped" label={`Stopped: ${portfolio?.stopped_grid_count ?? 0}`} />
              <StatusBadge status="info" label={`Completed: ${portfolio?.completed_grid_count ?? 0}`} />
            </div>
          </div>

          {/* Deferred Chart Note */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-dark)', background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '6px' }}>
            <Info size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
            <span>Time-series P&L chart deferred: backend currently provides aggregate totals rather than historical daily time-series points.</span>
          </div>
        </Card>
      </div>

      {/* Read-Only Grid Detail Modal */}
      <GridDetailModal
        grid={selectedGrid}
        onClose={() => setSelectedGrid(null)}
      />
    </div>
  );
};
