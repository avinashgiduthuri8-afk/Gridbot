import React from 'react';
import { StatusBadge } from '../common/StatusBadge';
import { RefreshCw, Radio, Bell } from 'lucide-react';
import type { NavigationTab } from '../../types/dashboard';

interface HeaderProps {
  activeTab: NavigationTab;
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

export const Header: React.FC<HeaderProps> = ({ activeTab }) => {
  return (
    <header className="header">
      <div className="header-title-section">
        <h1 className="header-title">{TAB_TITLES[activeTab]}</h1>
        <StatusBadge status="paper" label="Paper Mode" />
      </div>

      <div className="header-actions">
        <button className="action-btn" title="Refresh Data">
          <RefreshCw size={14} />
          <span>Refresh</span>
        </button>
        <button className="action-btn" title="System Connection Status">
          <Radio size={14} color="#10b981" />
          <span>Backend Ready</span>
        </button>
        <button className="action-btn" title="Notifications">
          <Bell size={14} />
        </button>
      </div>
    </header>
  );
};
