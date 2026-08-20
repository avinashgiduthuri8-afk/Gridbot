import React from 'react';
import { MetricCard } from '../components/common/MetricCard';
import { Card } from '../components/common/Card';
import { Table } from '../components/common/Table';
import type { TableColumn } from '../types/dashboard';
import { DollarSign, Activity, Wallet, ShieldAlert } from 'lucide-react';

interface ActiveGridSummaryRow {
  id: string;
  symbol: string;
  mode: string;
  status: string;
  invested: string;
  realizedPnl: string;
}

export const OverviewPage: React.FC = () => {
  // Empty data array - API integration will populate this in future phase
  const activeGrids: ActiveGridSummaryRow[] = [];

  const columns: TableColumn<ActiveGridSummaryRow>[] = [
    { key: 'symbol', header: 'Coin / Symbol' },
    { key: 'mode', header: 'Mode' },
    { key: 'status', header: 'Status' },
    { key: 'invested', header: 'Capital Invested' },
    { key: 'realizedPnl', header: 'Realized P&L', align: 'right' },
  ];

  return (
    <div>
      {/* Metrics Row */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Realized P&L"
          value="?0.00"
          change="0.00%"
          trend="neutral"
          subtext="Lifetime P&L"
          icon={<DollarSign size={20} />}
          accentColor="#10b981"
        />
        <MetricCard
          title="Active Grids"
          value="0"
          subtext="Max 5 Simultaneous"
          icon={<Activity size={20} />}
          accentColor="#6366f1"
        />
        <MetricCard
          title="Available Wallet"
          value="?0.00"
          subtext="Min ?500 balance reserve"
          icon={<Wallet size={20} />}
          accentColor="#06b6d4"
        />
        <MetricCard
          title="Risk Exposure"
          value="0.00%"
          change="Safe"
          trend="neutral"
          subtext="Daily Loss Limit ?2,000"
          icon={<ShieldAlert size={20} />}
          accentColor="#f59e0b"
        />
      </div>

      {/* Grid Layout Section */}
      <div className="overview-grid-2col">
        {/* Main Recent Grids Table Card */}
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <h2 className="section-title">Active Grid Monitors</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Real-time DCA Grid Execution
            </span>
          </div>

          <Table<ActiveGridSummaryRow>
            columns={columns}
            data={activeGrids}
            keyExtractor={(row) => row.id}
            emptyMessage="No active DCA grids currently running"
          />
        </Card>

        {/* System & Engine Status Sidebar Card */}
        <Card style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="section-header">
            <h2 className="section-title">Engine Health</h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Database Connection
              </span>
              <span style={{ fontSize: '0.85rem', color: 'var(--success)', fontWeight: 600 }}>
                Read-Only Standby
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Exchange Client
              </span>
              <span style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                CoinDCX REST
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Risk Manager
              </span>
              <span style={{ fontSize: '0.85rem', color: 'var(--success)', fontWeight: 600 }}>
                Enforced (5 Grids Max)
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Polling Frequency
              </span>
              <span style={{ fontSize: '0.85rem', color: '#fff', fontWeight: 500 }}>
                5s Price / 8s Order
              </span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
