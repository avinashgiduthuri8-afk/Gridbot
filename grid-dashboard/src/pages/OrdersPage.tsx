import React, { useState, useMemo } from 'react';
import { Card } from '../components/common/Card';
import { Table } from '../components/common/Table';
import { StatusBadge } from '../components/common/StatusBadge';
import { formatInr, formatDate } from '../utils/formatters';
import type { TableColumn, OrderResponse, StatusType } from '../types/dashboard';
import type { DashboardData } from '../hooks/useDashboardData';
import { Search, Filter } from 'lucide-react';

interface OrdersPageProps {
  data: DashboardData;
  loading: boolean;
}

export const OrdersPage: React.FC<OrdersPageProps> = ({ data, loading }) => {
  const { orders } = data;
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const filteredOrders = useMemo(() => {
    return orders.filter((order) => {
      const matchesStatus =
        statusFilter === 'ALL' ||
        order.status.toUpperCase() === statusFilter.toUpperCase();
      const matchesSearch =
        !searchQuery ||
        order.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        order.order_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (order.exchange_order_id &&
          order.exchange_order_id.toLowerCase().includes(searchQuery.toLowerCase()));

      return matchesStatus && matchesSearch;
    });
  }, [orders, statusFilter, searchQuery]);

  const columns: TableColumn<OrderResponse>[] = [
    {
      key: 'symbol',
      header: 'Coin / Side',
      render: (ord) => (
        <div>
          <div style={{ fontWeight: 700, color: '#fff' }}>{ord.symbol}</div>
          <span
            style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              color: ord.side.toUpperCase() === 'BUY' ? 'var(--success)' : 'var(--accent-cyan)',
              textTransform: 'uppercase',
            }}
          >
            {ord.side} ({ord.order_type})
          </span>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (ord) => (
        <StatusBadge status={ord.status.toLowerCase() as StatusType} />
      ),
    },
    {
      key: 'price',
      header: 'Order Price',
      render: (ord) => formatInr(ord.price),
    },
    {
      key: 'quantity',
      header: 'Order Qty',
      render: (ord) => (
        <span style={{ fontFamily: 'monospace' }}>
          {ord.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
        </span>
      ),
    },
    {
      key: 'filled_quantity',
      header: 'Filled Qty / Price',
      render: (ord) => (
        <div style={{ fontSize: '0.8rem' }}>
          <div>{ord.filled_quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}</div>
          <div style={{ color: 'var(--text-muted)' }}>{formatInr(ord.filled_price)}</div>
        </div>
      ),
    },
    {
      key: 'reconciliation_status',
      header: 'Reconciliation',
      render: (ord) => (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
          {ord.reconciliation_status}
        </span>
      ),
    },
    {
      key: 'exchange_order_id',
      header: 'Exchange Order ID',
      render: (ord) => (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-dark)', fontFamily: 'monospace' }}>
          {ord.exchange_order_id || 'N/A (Simulated)'}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Created Time',
      render: (ord) => (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {formatDate(ord.created_at)}
        </span>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ padding: '1.5rem' }}>
        <div className="section-header" style={{ marginBottom: '1.25rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h2 className="section-title">Order Lifecycle Management</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Active buy/sell orders and status reconciliation
            </span>
          </div>

          {/* Filters Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {/* Search Input */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.4rem 0.75rem',
              }}
            >
              <Search size={14} color="var(--text-muted)" />
              <input
                type="text"
                placeholder="Search symbol or order ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#fff',
                  fontSize: '0.8rem',
                  width: '180px',
                }}
              />
            </div>

            {/* Status Dropdown Filter */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.4rem 0.75rem',
              }}
            >
              <Filter size={14} color="var(--text-muted)" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#fff',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                }}
              >
                <option value="ALL" style={{ background: '#0d1322', color: '#fff' }}>
                  All Statuses
                </option>
                <option value="OPEN" style={{ background: '#0d1322', color: '#fff' }}>
                  OPEN
                </option>
                <option value="FILLED" style={{ background: '#0d1322', color: '#fff' }}>
                  FILLED
                </option>
                <option value="CANCELLED" style={{ background: '#0d1322', color: '#fff' }}>
                  CANCELLED
                </option>
              </select>
            </div>
          </div>
        </div>

        <Table<OrderResponse>
          columns={columns}
          data={filteredOrders}
          keyExtractor={(ord) => ord.order_id}
          emptyMessage={
            loading
              ? 'Loading orders...'
              : 'No matching orders found in the database.'
          }
        />
      </Card>
    </div>
  );
};
