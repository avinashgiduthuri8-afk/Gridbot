import React from 'react';
import { StatusBadge } from '../common/StatusBadge';
import { RefreshCw, Radio } from 'lucide-react';
import type { NavigationTab, HealthResponse } from '../../types/dashboard';

interface HeaderProps {
  activeTab: NavigationTab;
  health: HealthResponse | null;
  loading: boolean;
  lastUpdated: Date | null;
  onRefresh: () => void;
}

const TAB_TITLES: Record<NavigationTab, string> = {
  overview: 'Market Overview & Regime',
  scanner: 'Indian Stock Scanner',
  sectors: 'Sector Strength & Momentum',
  signals: 'Signals Log & MFE/MAE History',
  backtest: 'Scanner Backtesting Suite',
};

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  health,
  loading,
  lastUpdated,
  onRefresh,
}) => {
  const isHealthy = health?.status === 'ok' && health?.database_connected;

  return (
    <header className="header">
      <div className="header-title-section">
        <h1 className="header-title">{TAB_TITLES[activeTab] || 'Indian Stock Scanner'}</h1>
        <StatusBadge status="active" label="NSE / BSE Live" />
      </div>

      <div className="header-actions">
        {lastUpdated && (
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dark)' }}>
            Updated: {lastUpdated.toLocaleTimeString()}
          </span>
        )}

        <button
          className="action-btn"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh Data"
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          <span>{loading ? 'Refreshing...' : 'Refresh'}</span>
        </button>

        <button className="action-btn" title="Backend Server Status">
          <Radio size={14} color={isHealthy ? '#10b981' : '#ef4444'} />
          <span>{isHealthy ? 'Backend Connected' : 'Disconnected'}</span>
        </button>
      </div>
    </header>
  );
};
