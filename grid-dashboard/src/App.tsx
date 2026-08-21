import { useState } from 'react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { OverviewPage } from './pages/OverviewPage';
import { ScannerPage } from './pages/ScannerPage';
import { SectorsPage } from './pages/SectorsPage';
import { SignalsHistoryPage } from './pages/SignalsHistoryPage';
import { BacktestPage } from './pages/BacktestPage';
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
            onNavigate={setActiveTab}
            onRefresh={refetch}
          />
        );
      case 'scanner':
        return <ScannerPage />;
      case 'sectors':
        return <SectorsPage />;
      case 'signals':
        return <SignalsHistoryPage />;
      case 'backtest':
        return <BacktestPage />;
      case 'active-grids':
        return <ActiveGridsPage data={data} loading={loading} onRefresh={refetch} />;
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
            onNavigate={setActiveTab}
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
      emergencyStopActive={data.settings?.emergency_stop_active ?? false}
      onRefresh={refetch}
    >
      {error && (
        <div className="error-banner">
          <strong>System Notice:</strong> {error}
        </div>
      )}
      {renderActivePage()}
    </DashboardLayout>
  );
}

export default App;
