import React from 'react';
import { MetricCard } from '../components/common/MetricCard';
import { Card } from '../components/common/Card';
import { formatInr, formatPct } from '../utils/formatters';
import type { DashboardData } from '../hooks/useDashboardData';
import {
  TrendingUp,
  RotateCcw,
  CheckCircle2,
  Percent,
  TrendingDown,
  Scale,
  ShoppingCart,
  Tag,
} from 'lucide-react';

interface AnalyticsPageProps {
  data: DashboardData;
  loading: boolean;
}

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({
  data,
  loading,
}) => {
  const { analytics } = data;

  const totalBuys = analytics?.total_buys ?? 0;
  const totalSells = analytics?.total_sells ?? 0;
  const completedCycles = analytics?.completed_cycles ?? 0;
  const realizedProfit = analytics?.total_realized_profit ?? 0;
  const winRate = analytics?.win_rate_pct ?? 0;
  const maxDrawdown = analytics?.max_drawdown_pct ?? 0;
  const profitFactor = analytics?.profit_factor;
  const dustWriteoffs = analytics?.total_dust_writeoffs ?? 0;

  return (
    <div>
      {/* Metrics Row 1 */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Realized Profit"
          value={formatInr(realizedProfit)}
          change={formatPct(winRate)}
          trend={realizedProfit >= 0 ? 'up' : 'down'}
          subtext="Net Trading Gains"
          icon={<TrendingUp size={20} />}
          accentColor="#10b981"
          loading={loading && !analytics}
        />
        <MetricCard
          title="Win Rate"
          value={formatPct(winRate)}
          subtext={`Completed Cycles: ${completedCycles}`}
          icon={<Percent size={20} />}
          accentColor="#6366f1"
          loading={loading && !analytics}
        />
        <MetricCard
          title="Max Drawdown"
          value={formatPct(maxDrawdown)}
          trend="down"
          subtext="Peak-to-Trough Decline"
          icon={<TrendingDown size={20} />}
          accentColor="#ef4444"
          loading={loading && !analytics}
        />
        <MetricCard
          title="Profit Factor"
          value={profitFactor !== undefined && profitFactor !== null ? profitFactor.toFixed(2) : 'N/A'}
          subtext="Gross Gains / Gross Losses"
          icon={<Scale size={20} />}
          accentColor="#f59e0b"
          loading={loading && !analytics}
        />
      </div>

      {/* Analytics Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.25rem' }}>
        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <h2 className="section-title">Order Execution Volume</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <ShoppingCart size={18} color="var(--success)" />
                <span>Total Buy Executions</span>
              </div>
              <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#fff' }}>{totalBuys}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Tag size={18} color="var(--accent-cyan)" />
                <span>Total Sell Executions</span>
              </div>
              <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#fff' }}>{totalSells}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <RotateCcw size={18} color="var(--primary)" />
                <span>Completed Cycles</span>
              </div>
              <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#fff' }}>{completedCycles}</span>
            </div>
          </div>
        </Card>

        <Card style={{ padding: '1.5rem' }}>
          <div className="section-header">
            <h2 className="section-title">System & Dust Analytics</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={18} color="var(--warning)" />
                <span>Dust Write-offs</span>
              </div>
              <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#fff' }}>{dustWriteoffs}</span>
            </div>

            <div
              style={{
                marginTop: '0.5rem',
                padding: '0.85rem 1rem',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-color)',
                fontSize: '0.8rem',
                color: 'var(--text-muted)',
              }}
            >
              Analytics math is re-computed directly from historical grid cycles and fill records in SQLite.
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
