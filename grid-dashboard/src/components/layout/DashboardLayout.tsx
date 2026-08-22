import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import type { NavigationTab, HealthResponse } from '../../types/dashboard';

interface DashboardLayoutProps {
  activeTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  health: HealthResponse | null;
  loading: boolean;
  lastUpdated: Date | null;
  emergencyStopActive?: boolean;
  onRefresh: () => void;
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  activeTab,
  onTabChange,
  health,
  loading,
  lastUpdated,
  emergencyStopActive = false,
  onRefresh,
  children,
}) => {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="app-layout">
      <Sidebar
        activeTab={activeTab}
        onTabChange={onTabChange}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
      />
      <div className="main-content">
        <Header
          activeTab={activeTab}
          health={health}
          loading={loading}
          lastUpdated={lastUpdated}
          emergencyStopActive={emergencyStopActive}
          onRefresh={onRefresh}
        />
        <main className="page-container">{children}</main>
      </div>
    </div>
  );
};
