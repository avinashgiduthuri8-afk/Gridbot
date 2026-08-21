import { useState } from 'react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { OverviewPage } from './pages/OverviewPage';
import { ScannerPage } from './pages/ScannerPage';
import { SectorsPage } from './pages/SectorsPage';
import { SignalsHistoryPage } from './pages/SignalsHistoryPage';
import { BacktestPage } from './pages/BacktestPage';
import { BotsPage } from './pages/BotsPage';
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
      case 'bots':
        return <BotsPage />;
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
