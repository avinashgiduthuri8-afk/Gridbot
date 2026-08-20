import React, { useState } from 'react';
import { Card } from '../components/common/Card';
import { Table } from '../components/common/Table';
import { StatusBadge } from '../components/common/StatusBadge';
import { GridDetailModal } from '../components/common/GridDetailModal';
import { formatInr } from '../utils/formatters';
import type { TableColumn, GridResponse, StatusType } from '../types/dashboard';
import type { DashboardData } from '../hooks/useDashboardData';
import { Eye } from 'lucide-react';

interface ActiveGridsPageProps {
  data: DashboardData;
  loading: boolean;
}

export const ActiveGridsPage: React.FC<ActiveGridsPageProps> = ({
  data,
  loading,
}) => {
  const { grids } = data;
  const [selectedGrid, setSelectedGrid] = useState<GridResponse | null>(null);

  const columns: TableColumn<GridResponse>[] = [
    {
      key: 'symbol',
      header: 'Coin / Symbol',
      render: (grid) => (
        <div>
          <div style={{ fontWeight: 700, color: '#fff', fontSize: '0.95rem' }}>
            {grid.symbol}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dark)', fontFamily: 'monospace' }}>
            ID: {grid.grid_id.slice(0, 8)}...
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
      key: 'entry_price',
      header: 'Entry Price',
      render: (grid) => formatInr(grid.entry_price),
    },
    {
      key: 'total_investment',
      header: 'Invested Capital',
      render: (grid) => (
        <div>
          <div style={{ fontWeight: 600, color: '#fff' }}>{formatInr(grid.total_investment)}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Base: {formatInr(grid.base_investment)}
          </div>
        </div>
      ),
    },
    {
      key: 'average_entry_price',
      header: 'Avg Entry',
      render: (grid) => formatInr(grid.average_entry_price),
    },
    {
      key: 'current_level',
      header: 'Level',
      render: (grid) => (
        <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>
          {grid.current_level} / {grid.max_levels}
        </span>
      ),
    },
    {
      key: 'next_buy_price',
      header: 'Next Buy / Sell',
      render: (grid) => (
        <div style={{ fontSize: '0.8rem' }}>
          <div style={{ color: 'var(--success)' }}>Buy: {formatInr(grid.next_buy_price)}</div>
          <div style={{ color: 'var(--accent-cyan)' }}>Sell: {formatInr(grid.next_sell_price)}</div>
        </div>
      ),
    },
    {
      key: 'completed_cycles',
      header: 'Cycles',
      align: 'center',
      render: (grid) => (
        <span style={{ fontWeight: 600, color: '#fff' }}>{grid.completed_cycles}</span>
      ),
    },
    {
      key: 'realized_profit',
      header: 'Realized Profit',
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
      header: 'Inspect',
      align: 'center',
      render: (grid) => (
        <button
          className="action-btn"
          onClick={() => setSelectedGrid(grid)}
          title="Inspect Read-Only Grid Details"
          style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
        >
          <Eye size={12} />
          <span>View</span>
        </button>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ padding: '1.5rem' }}>
        <div className="section-header">
          <div>
            <h2 className="section-title">Active & Historical DCA Grids</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Manage multi-level buy/sell grid triggers per coin
            </span>
          </div>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Total Grids: {grids.length}
          </span>
        </div>

        <Table<GridResponse>
          columns={columns}
          data={grids}
          keyExtractor={(grid) => grid.grid_id}
          emptyMessage={
            loading
              ? 'Loading DCA grid records...'
              : 'No DCA grids found in the database.'
          }
        />
      </Card>

      {/* Read-Only Grid Detail Modal */}
      <GridDetailModal
        grid={selectedGrid}
        onClose={() => setSelectedGrid(null)}
      />
    </div>
  );
};
