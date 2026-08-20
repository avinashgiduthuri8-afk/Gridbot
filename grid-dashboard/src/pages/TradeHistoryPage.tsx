import React, { useMemo } from 'react';
import { Card } from '../components/common/Card';
import { Table } from '../components/common/Table';
import { formatInr, formatDate } from '../utils/formatters';
import type { TableColumn, TradeResponse } from '../types/dashboard';
import type { DashboardData } from '../hooks/useDashboardData';

interface TradeHistoryPageProps {
  data: DashboardData;
  loading: boolean;
}

export const TradeHistoryPage: React.FC<TradeHistoryPageProps> = ({
  data,
  loading,
}) => {
  const { trades } = data;

  const sortedTrades = useMemo(() => {
    return [...trades].sort((a, b) => {
      const timeA = new Date(a.executed_at).getTime();
      const timeB = new Date(b.executed_at).getTime();
      return timeB - timeA;
    });
  }, [trades]);

  const columns: TableColumn<TradeResponse>[] = [
    {
      key: 'symbol',
      header: 'Coin / Symbol',
      render: (t) => (
        <div>
          <div style={{ fontWeight: 700, color: '#fff' }}>{t.symbol}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dark)', fontFamily: 'monospace' }}>
            Trade ID: {t.trade_id}
          </div>
        </div>
      ),
    },
    {
      key: 'side',
      header: 'Side',
      render: (t) => (
        <span
          style={{
            padding: '0.2rem 0.5rem',
            borderRadius: '4px',
            fontSize: '0.75rem',
            fontWeight: 700,
            background: t.side.toUpperCase() === 'BUY' ? 'var(--success-light)' : 'var(--accent-cyan-light)',
            color: t.side.toUpperCase() === 'BUY' ? 'var(--success)' : 'var(--accent-cyan)',
            textTransform: 'uppercase',
          }}
        >
          {t.side}
        </span>
      ),
    },
    {
      key: 'price',
      header: 'Execution Price',
      render: (t) => formatInr(t.price),
    },
    {
      key: 'quantity',
      header: 'Quantity',
      render: (t) => (
        <span style={{ fontFamily: 'monospace' }}>
          {t.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
        </span>
      ),
    },
    {
      key: 'investment_inr',
      header: 'Investment (INR)',
      render: (t) => formatInr(t.investment_inr),
    },
    {
      key: 'fee',
      header: 'Fee',
      render: (t) => formatInr(t.fee),
    },
    {
      key: 'pnl',
      header: 'Realized P&L',
      align: 'right',
      render: (t) => (
        <span
          style={{
            color: t.pnl >= 0 ? 'var(--success)' : 'var(--danger)',
            fontWeight: 700,
          }}
        >
          {formatInr(t.pnl)}
        </span>
      ),
    },
    {
      key: 'executed_at',
      header: 'Execution Time',
      render: (t) => (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {formatDate(t.executed_at)}
        </span>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ padding: '1.5rem' }}>
        <div className="section-header">
          <div>
            <h2 className="section-title">Trade Execution Audit History</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Completed buy/sell order fills and realized profit/loss logs
            </span>
          </div>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Total Trades: {sortedTrades.length}
          </span>
        </div>

        <Table<TradeResponse>
          columns={columns}
          data={sortedTrades}
          keyExtractor={(t) => t.trade_id}
          emptyMessage={
            loading
              ? 'Loading trade history logs...'
              : 'No trade fills recorded in the database.'
          }
        />
      </Card>
    </div>
  );
};
