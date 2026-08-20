import React from 'react';
import { StatusBadge } from '../common/StatusBadge';
import { RefreshCw, Radio, Bell } from 'lucide-react';
import type { NavigationTab, HealthResponse } from '../../types/dashboard';

interface HeaderProps {
  activeTab: NavigationTab;
  health: HealthResponse | null;
  loading: boolean;
  lastUpdated: Date | null;
  onRefresh: () => void;
}

const TAB_TITLES: Record<NavigationTab, string> = {
  overview: 'Dashboard Overview',
  'active-grids': 'Active Grids',
  positions: 'Open Positions',
  orders: 'Orders Management',
  'trade-history': 'Trade Execution History',
  analytics: 'Performance Analytics',
  risk: 'Risk & Capital Controls',
  settings: 'System Configuration',
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
        <h1 className="header-title">{TAB_TITLES[activeTab]}</h1>
        <StatusBadge status="paper" label="Paper Mode" />
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

        <button className="action-btn" title="Notifications">
          <Bell size={14} />
        </button>
      </div>
    </header>
  );
};
