import React, { useState } from 'react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { Table } from '../components/common/Table';
import { StatusBadge } from '../components/common/StatusBadge';
import { GridDetailModal } from '../components/common/GridDetailModal';
import { CreateGridModal } from '../components/common/CreateGridModal';
import { formatInr } from '../utils/formatters';
import type { TableColumn, GridResponse, StatusType, NavigationTab } from '../types/dashboard';
import type { DashboardData } from '../hooks/useDashboardData';
import {
  Wallet,
  TrendingUp,
  Activity,
  Layers,
  ArrowUpRight,
  Plus,
} from 'lucide-react';

interface OverviewPageProps {
  data: DashboardData;
  loading: boolean;
  onNavigate: (tab: NavigationTab) => void;
  onRefresh?: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  data,
  loading,
  onNavigate,
  onRefresh,
}) => {
  const { portfolio, analytics, grids, positions } = data;
  const [selectedGrid, setSelectedGrid] = useState<GridResponse | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const activeGrids = grids.filter((g) => g.status === 'active');
  const recentGrids = grids.slice(0, 5);

  const gridColumns: TableColumn<GridResponse>[] = [
    {
      key: 'symbol',
      header: 'Coin / Symbol',
      render: (grid) => (
        <div>
          <div style={{ fontWeight: 700, color: '#fff' }}>{grid.symbol}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dark)' }}>
            {grid.grid_id.slice(0, 8)}...
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
      header: 'Invested',
      render: (grid) => formatInr(grid.total_investment),
    },
    {
      key: 'current_level',
      header: 'DCA Level',
      render: (grid) => (
        <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>
          {grid.current_level} / {grid.max_levels}
        </span>
      ),
    },
    {
      key: 'realized_profit',
      header: 'Realized P&L',
      align: 'right',
      render: (grid) => (
        <span
          style={{
            color: grid.realized_profit >= 0 ? 'var(--success)' : 'var(--danger)',
            fontWeight: 700,
          }}
        >
          {formatInr(grid.realized_profit)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Action',
      align: 'center',
      render: (grid) => (
        <button
          className="action-btn"
          onClick={() => setSelectedGrid(grid)}
          title="Inspect & Manage Grid"
          style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
        >
          <span>Manage</span>
        </button>
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Metric Cards Top Row */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Portfolio Value"
          value={formatInr(portfolio?.combined_total ?? 0)}
          subtext={`Invested: ${formatInr(portfolio?.total_invested ?? 0)}`}
          accentColor="var(--primary)"
          icon={<Wallet size={20} />}
        />
        <MetricCard
          title="Realized Profit"
          value={formatInr(portfolio?.total_realized ?? 0)}
          subtext={`Completed Cycles: ${analytics?.completed_cycles ?? 0}`}
          trend={(portfolio?.total_realized ?? 0) >= 0 ? 'up' : 'down'}
          accentColor="var(--success)"
          icon={<TrendingUp size={20} />}
        />
        <MetricCard
          title="Active DCA Grids"
          value={`${activeGrids.length} Active`}
          subtext={`${positions.length} with open positions`}
          accentColor="var(--accent-cyan)"
          icon={<Layers size={20} />}
        />
        <MetricCard
          title="Strategy Win Rate"
          value={`${(analytics?.win_rate_pct ?? 0).toFixed(1)}%`}
          subtext={`Buys: ${analytics?.total_buys ?? 0} | Sells: ${analytics?.total_sells ?? 0}`}
          trend="neutral"
          accentColor="var(--warning)"
          icon={<Activity size={20} />}
        />
      </div>

      {/* Main Content Area */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
        {/* Recent Grids Table */}
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <div>
              <h2 className="section-title">Active & Recent Grids</h2>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Overview of running DCA strategy deployments
              </span>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="action-btn"
                onClick={() => setShowCreateModal(true)}
                style={{
                  backgroundColor: 'var(--accent-cyan)',
                  color: '#000',
                  fontWeight: 700,
                  borderColor: 'var(--accent-cyan)',
                }}
              >
                <Plus size={14} />
                <span>New Grid</span>
              </button>
              <button
                className="action-btn"
                onClick={() => onNavigate('active-grids')}
              >
                <span>View All ({grids.length})</span>
                <ArrowUpRight size={14} />
              </button>
            </div>
          </div>

          <Table<GridResponse>
            columns={gridColumns}
            data={recentGrids}
            keyExtractor={(grid) => grid.grid_id}
            emptyMessage={
              loading ? 'Loading grids...' : 'No active grids running.'
            }
          />
        </Card>

        {/* Quick Strategy Performance Card */}
        <Card style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <h2 className="section-title">Strategy Highlights</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Execution & risk metrics summary
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Profit Factor</span>
              <span style={{ fontWeight: 600, color: '#fff' }}>
                {analytics?.profit_factor ? analytics.profit_factor.toFixed(2) : 'N/A'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Max Drawdown</span>
              <span style={{ fontWeight: 600, color: 'var(--danger)' }}>
                {(analytics?.max_drawdown_pct ?? 0).toFixed(2)}%
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Total Dust Writeoffs</span>
              <span style={{ fontWeight: 600, color: '#fff' }}>
                {analytics?.total_dust_writeoffs ?? 0}
              </span>
            </div>
          </div>
        </Card>
      </div>

      <GridDetailModal
        grid={selectedGrid}
        onClose={() => setSelectedGrid(null)}
        onRefresh={onRefresh}
      />

      <CreateGridModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={() => onRefresh?.()}
      />
    </div>
  );
};
