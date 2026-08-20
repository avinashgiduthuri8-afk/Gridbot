import { useState } from 'react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { OverviewPage } from './pages/OverviewPage';
import { ActiveGridsPage } from './pages/ActiveGridsPage';
import { PositionsPage } from './pages/PositionsPage';
import { OrdersPage } from './pages/OrdersPage';
import { TradeHistoryPage } from './pages/TradeHistoryPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { RiskPage } from './pages/RiskPage';
import { SettingsPage } from './pages/SettingsPage';
import { useDashboardData } from './hooks/useDashboardData';
import type { NavigationTab } from './types/dashboard';

export function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');

  const { data, loading, error, lastUpdated, refetch } = useDashboardData(15000);

  const renderActivePage = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <OverviewPage
            data={data}
            loading={loading}
            error={error}
            onRefresh={refetch}
          />
        );
      case 'active-grids':
        return <ActiveGridsPage data={data} loading={loading} />;
      case 'positions':
        return <PositionsPage data={data} loading={loading} />;
      case 'orders':
        return <OrdersPage data={data} loading={loading} />;
      case 'trade-history':
        return <TradeHistoryPage data={data} loading={loading} />;
      case 'analytics':
        return <AnalyticsPage data={data} loading={loading} />;
      case 'risk':
        return <RiskPage data={data} loading={loading} />;
      case 'settings':
        return <SettingsPage data={data} />;
      default:
        return (
          <OverviewPage
            data={data}
            loading={loading}
            error={error}
            onRefresh={refetch}
          />
        );
    }
  };

  return (
    <DashboardLayout
      activeTab={activeTab}
      onTabChange={setActiveTab}
      health={data.health}
      loading={loading}
      lastUpdated={lastUpdated}
      onRefresh={refetch}
    >
      {renderActivePage()}
    </DashboardLayout>
  );
}

export default App;
