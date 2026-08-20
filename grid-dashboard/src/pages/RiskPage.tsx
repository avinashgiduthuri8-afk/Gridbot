import React from 'react';
import { MetricCard } from '../components/common/MetricCard';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/common/StatusBadge';
import { ProgressBar } from '../components/common/ProgressBar';
import { formatInr, formatPct } from '../utils/formatters';
import type { DashboardData } from '../hooks/useDashboardData';
import {
  ShieldAlert,
  PieChart,
  Wallet,
  Activity,
  AlertTriangle,
  HardDrive,
  Webhook,
} from 'lucide-react';

interface RiskPageProps {
  data: DashboardData;
  loading: boolean;
}

export const RiskPage: React.FC<RiskPageProps> = ({ data, loading }) => {
  const { settings, portfolio } = data;

  const risk = settings?.risk;
  const maxCapital = risk?.max_total_capital ?? 50000;
  const currentInvested = portfolio?.total_invested ?? 0;
  const utilizationPct = maxCapital > 0 ? (currentInvested / maxCapital) * 100 : 0;
  const maxGrids = risk?.max_simultaneous_grids ?? 5;
  const activeGrids = portfolio?.active_grid_count ?? 0;
  const isEmergencyHalted = settings?.emergency_stop_active ?? false;

  return (
    <div>
      {/* Emergency Stop Prominent Warning */}
      {isEmergencyHalted && (
        <Card
          style={{
            padding: '1.25rem 1.5rem',
            marginBottom: '1.5rem',
            background: 'var(--danger-light)',
            borderColor: 'rgba(239, 68, 68, 0.5)',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <AlertTriangle color="var(--danger)" size={28} />
          <div>
            <div style={{ fontWeight: 700, color: '#fff', fontSize: '1.1rem' }}>
              EMERGENCY STOP IS ACTIVE
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              All new grid creations and order placements are currently blocked by the Risk Manager.
            </div>
          </div>
        </Card>
      )}

      {/* Risk Metrics Row */}
      <div className="metrics-grid">
        <MetricCard
          title="Capital Utilization"
          value={formatPct(utilizationPct)}
          subtext={`${formatInr(currentInvested)} / ${formatInr(maxCapital)}`}
          icon={<PieChart size={20} />}
          accentColor="#6366f1"
          loading={loading && !settings}
        />
        <MetricCard
          title="Grid Slots Used"
          value={`${activeGrids} / ${maxGrids}`}
          subtext="Simultaneous Grids Limit"
          icon={<Activity size={20} />}
          accentColor="#06b6d4"
          loading={loading && !settings}
        />
        <MetricCard
          title="Daily Loss Limit"
          value={formatInr(risk?.daily_loss_limit)}
          subtext="Max allowed realized daily loss"
          icon={<ShieldAlert size={20} />}
          accentColor="#f59e0b"
          loading={loading && !settings}
        />
        <MetricCard
          title="Min Wallet Reserve"
          value={formatInr(risk?.min_wallet_balance)}
          subtext="Required unallocated balance"
          icon={<Wallet size={20} />}
          accentColor="#10b981"
          loading={loading && !settings}
        />
      </div>

      {/* Capital Allocation & Gauges */}
      <Card style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        <div className="section-header">
          <h2 className="section-title">Portfolio Risk Exposure & Capacity</h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Total Capital Allocation</span>
              <span style={{ fontWeight: 600, color: '#fff' }}>{formatInr(currentInvested)} / {formatInr(maxCapital)}</span>
            </div>
            <ProgressBar value={utilizationPct} color="var(--primary)" height={10} />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Active Grid Slots Limit</span>
              <span style={{ fontWeight: 600, color: '#fff' }}>{activeGrids} of {maxGrids} slots</span>
            </div>
            <ProgressBar value={(activeGrids / maxGrids) * 100} color="var(--accent-cyan)" height={10} />
          </div>
        </div>
      </Card>

      {/* Detailed Risk Allocation Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <h2 className="section-title">Capital & Risk Rules</h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-color)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Max Capital Per Coin
              </span>
              <span style={{ fontSize: '0.85rem', color: '#fff', fontWeight: 600 }}>
                {formatInr(risk?.max_capital_per_coin)}
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-color)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Max Total Portfolio Capital
              </span>
              <span style={{ fontSize: '0.85rem', color: '#fff', fontWeight: 600 }}>
                {formatInr(risk?.max_total_capital)}
              </span>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-color)',
              }}
            >
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Emergency Stop Mode
              </span>
              <StatusBadge
                status={isEmergencyHalted ? 'error' : 'success'}
                label={isEmergencyHalted ? 'HALTED' : 'NORMAL'}
              />
            </div>
          </div>
        </Card>

        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <h2 className="section-title">Subsystems & Safeguards</h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-color)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <HardDrive size={16} color="var(--accent-cyan)" />
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Google Drive Backup
                </span>
              </div>
              <StatusBadge
                status={settings?.backup_enabled ? 'active' : 'stopped'}
                label={settings?.backup_enabled ? 'Enabled' : 'Disabled'}
              />
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-color)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Webhook size={16} color="var(--primary)" />
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  CoinDCX Webhook Receiver
                </span>
              </div>
              <StatusBadge
                status={settings?.webhook_enabled ? 'active' : 'stopped'}
                label={settings?.webhook_enabled ? 'Enabled' : 'Disabled'}
              />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
