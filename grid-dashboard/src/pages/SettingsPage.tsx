import React from 'react';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/common/StatusBadge';
import { formatInr } from '../utils/formatters';
import type { DashboardData } from '../hooks/useDashboardData';
import { Sliders, Shield, Clock, HardDrive, Lock } from 'lucide-react';

interface SettingsPageProps {
  data: DashboardData;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ data }) => {
  const { settings } = data;
  const risk = settings?.risk;

  return (
    <div>
      {/* Read-Only Notice Banner */}
      <Card
        style={{
          padding: '1rem 1.25rem',
          marginBottom: '1.5rem',
          background: 'rgba(99, 102, 241, 0.1)',
          borderColor: 'rgba(99, 102, 241, 0.3)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}
      >
        <Lock size={18} color="var(--primary)" />
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Operational settings are read-only in this dashboard phase. Secrets (API keys, Telegram tokens) are safely masked and excluded from API responses.
        </span>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem' }}>
        {/* Risk & Limits Config Card */}
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Shield size={18} color="var(--primary)" />
              <h2 className="section-title">Risk Control Parameters</h2>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Max Total Capital</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{formatInr(risk?.max_total_capital)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Max Capital Per Coin</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{formatInr(risk?.max_capital_per_coin)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Max Simultaneous Grids</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{risk?.max_simultaneous_grids ?? 5} Grids</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Min Wallet Balance Reserve</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{formatInr(risk?.min_wallet_balance)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Daily Realized Loss Limit</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{formatInr(risk?.daily_loss_limit)}</span>
            </div>
          </div>
        </Card>

        {/* Polling & Engine Cadence Card */}
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Clock size={18} color="var(--accent-cyan)" />
              <h2 className="section-title">Engine Polling Intervals</h2>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Price Polling Interval</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{settings?.price_poll_interval_seconds ?? 5} seconds</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Order Monitor Interval</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{settings?.order_poll_interval_seconds ?? 8} seconds</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Daily Telegram Summary</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{settings?.daily_summary_interval_seconds ?? 86400} seconds</span>
            </div>
            {settings?.monitor_interval_seconds && (
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Persisted Monitor Interval</span>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>{settings.monitor_interval_seconds} seconds</span>
              </div>
            )}
          </div>
        </Card>

        {/* Subsystem Integrations Card */}
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <HardDrive size={18} color="var(--success)" />
              <h2 className="section-title">Integrations & Subsystems</h2>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Emergency Stop</span>
              <StatusBadge status={settings?.emergency_stop_active ? 'error' : 'success'} label={settings?.emergency_stop_active ? 'ACTIVE' : 'NORMAL'} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Google Drive Backup</span>
              <StatusBadge status={settings?.backup_enabled ? 'active' : 'stopped'} label={settings?.backup_enabled ? 'Enabled' : 'Disabled'} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>CoinDCX Webhook Receiver</span>
              <StatusBadge status={settings?.webhook_enabled ? 'active' : 'stopped'} label={settings?.webhook_enabled ? 'Enabled' : 'Disabled'} />
            </div>
          </div>
        </Card>

        {/* Grid Presets Card */}
        {settings?.grid_defaults && (
          <Card style={{ padding: '1.5rem' }}>
            <div className="section-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Sliders size={18} color="var(--warning)" />
                <h2 className="section-title">Grid Defaults Presets</h2>
              </div>
            </div>

            <pre
              style={{
                background: 'rgba(0,0,0,0.3)',
                padding: '1rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                color: 'var(--text-muted)',
                overflowX: 'auto',
              }}
            >
              {JSON.stringify(settings.grid_defaults, null, 2)}
            </pre>
          </Card>
        )}
      </div>
    </div>
  );
};
