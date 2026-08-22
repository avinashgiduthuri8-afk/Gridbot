import React from 'react';
import type { NavigationTab } from '../../types/dashboard';
import {
  LayoutDashboard,
  Grid,
  Layers,
  ListOrdered,
  History,
  BarChart3,
  ShieldAlert,
  Settings,
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
  { id: 'active-grids', label: 'Active Grids', icon: <Grid size={18} /> },
  { id: 'positions', label: 'Positions', icon: <Layers size={18} /> },
  { id: 'orders', label: 'Orders', icon: <ListOrdered size={18} /> },
  { id: 'trade-history', label: 'Trade History', icon: <History size={18} /> },
  { id: 'analytics', label: 'Analytics', icon: <BarChart3 size={18} /> },
  { id: 'risk', label: 'Risk & Limits', icon: <ShieldAlert size={18} /> },
  { id: 'settings', label: 'Settings', icon: <Settings size={18} /> },
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
            <Bot size={20} />
          </div>
          {!collapsed && <span>GridBot</span>}
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
          <span className="bot-status-indicator" title="Bot Status: Online" />
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ color: '#fff', fontWeight: 600 }}>DCA Grid Engine</span>
              <span style={{ fontSize: '0.7rem' }}>v1.0.0</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
