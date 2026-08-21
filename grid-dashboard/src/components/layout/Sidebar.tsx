import React from 'react';
import type { NavigationTab } from '../../types/dashboard';
import {
  LayoutDashboard,
  Search,
  PieChart,
  Target,
  PlaySquare,
  TrendingUp,
  Bot,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface SidebarProps {
  activeTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const NAV_ITEMS: { id: NavigationTab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={18} /> },
  { id: 'scanner', label: 'Stock Scanner', icon: <Search size={18} /> },
  { id: 'sectors', label: 'Sector Matrix', icon: <PieChart size={18} /> },
  { id: 'signals', label: 'Signals Log', icon: <Target size={18} /> },
  { id: 'backtest', label: 'Backtesting', icon: <PlaySquare size={18} /> },
  { id: 'bots', label: 'Execution Bots', icon: <Bot size={18} /> },
];

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  collapsed,
  onToggleCollapse,
}) => {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="brand-title">
          <div className="brand-icon">
            <TrendingUp size={20} />
          </div>
          {!collapsed && <span>NSE Scanner</span>}
        </div>
        <button
          className="collapse-toggle"
          onClick={onToggleCollapse}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <ul className="nav-list">
        {NAV_ITEMS.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <li key={item.id}>
              <button
                className={`nav-item-btn ${isActive ? 'active' : ''}`}
                onClick={() => onTabChange(item.id)}
                title={collapsed ? item.label : undefined}
              >
                {item.icon}
                {!collapsed && <span>{item.label}</span>}
              </button>
            </li>
          );
        })}
      </ul>

      <div className="sidebar-footer">
        <div className="bot-info-card">
          <span className="bot-status-indicator" title="Scanner Status: Live" />
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ color: '#fff', fontWeight: 600 }}>Indian Stock Scanner</span>
              <span style={{ fontSize: '0.7rem' }}>PROJECT-BETA</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
