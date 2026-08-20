import React from 'react';
import { Card } from '../components/common/Card';
import { Table } from '../components/common/Table';
import { StatusBadge } from '../components/common/StatusBadge';
import { formatInr } from '../utils/formatters';
import type { TableColumn, PositionResponse, StatusType } from '../types/dashboard';
import type { DashboardData } from '../hooks/useDashboardData';

interface PositionsPageProps {
  data: DashboardData;
  loading: boolean;
}

export const PositionsPage: React.FC<PositionsPageProps> = ({
  data,
  loading,
}) => {
  const { positions } = data;

  const columns: TableColumn<PositionResponse>[] = [
    {
      key: 'symbol',
      header: 'Coin / Symbol',
      render: (pos) => (
        <div>
          <div style={{ fontWeight: 700, color: '#fff', fontSize: '0.95rem' }}>
            {pos.symbol}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Level {pos.current_level} / {pos.max_levels}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status & Mode',
      render: (pos) => (
        <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
          <StatusBadge status={pos.status.toLowerCase() as StatusType} />
          <StatusBadge status={pos.mode.toLowerCase() as StatusType} label={pos.mode.toUpperCase()} showDot={false} />
        </div>
      ),
    },
    {
      key: 'quantity',
      header: 'Holding Quantity',
      render: (pos) => (
        <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>
          {pos.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
        </span>
      ),
    },
    {
      key: 'average_entry_price',
      header: 'Avg Entry Price',
      render: (pos) => formatInr(pos.average_entry_price),
    },
    {
      key: 'current_price',
      header: 'Current Price',
      render: (pos) =>
        pos.current_price ? formatInr(pos.current_price) : <span style={{ color: 'var(--text-dark)' }}>N/A (Read-Only)</span>,
    },
    {
      key: 'invested',
      header: 'Invested Capital',
      render: (pos) => formatInr(pos.invested),
    },
    {
      key: 'realized_pnl',
      header: 'Realized P&L',
      align: 'right',
      render: (pos) => (
        <span
          style={{
            color: pos.realized_pnl >= 0 ? 'var(--success)' : 'var(--danger)',
            fontWeight: 600,
          }}
        >
          {formatInr(pos.realized_pnl)}
        </span>
      ),
    },
    {
      key: 'unrealized_pnl',
      header: 'Unrealized P&L',
      align: 'right',
      render: (pos) => (
        <span
          style={{
            color: pos.unrealized_pnl >= 0 ? 'var(--success)' : 'var(--danger)',
            fontWeight: 600,
          }}
        >
          {formatInr(pos.unrealized_pnl)}
        </span>
      ),
    },
    {
      key: 'combined_pnl',
      header: 'Combined P&L',
      align: 'right',
      render: (pos) => (
        <span
          style={{
            color: pos.combined_pnl >= 0 ? 'var(--success)' : 'var(--danger)',
            fontWeight: 700,
          }}
        >
          {formatInr(pos.combined_pnl)}
        </span>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ padding: '1.5rem' }}>
        <div className="section-header">
          <div>
            <h2 className="section-title">Open Holdings & Positions</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Active and paused DCA grid positions holding non-zero asset quantities
            </span>
          </div>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Open Positions: {positions.length}
          </span>
        </div>

        <Table<PositionResponse>
          columns={columns}
          data={positions}
          keyExtractor={(pos) => pos.grid_id}
          emptyMessage={
            loading
              ? 'Loading open positions...'
              : 'No open positions holding coin inventory currently.'
          }
        />
      </Card>
    </div>
  );
};
