import { useState } from 'react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { OverviewPage } from './pages/OverviewPage';
import { ScannerPage } from './pages/ScannerPage';
import { SectorsPage } from './pages/SectorsPage';
import { SignalsHistoryPage } from './pages/SignalsHistoryPage';
import { BacktestPage } from './pages/BacktestPage';
import { BotsPage } from './pages/BotsPage';
import { useDashboardData } from './hooks/useDashboardData';
import { useDispatchWebSocket } from './hooks/useDispatchWebSocket';
import type { NavigationTab } from './types/dashboard';
import { Bell, X, ArrowRight } from 'lucide-react';

export function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');
  const { data, loading, error, lastUpdated, refetch } = useDashboardData(15000);
  const { connected: _connected, latestNotification, clearNotification } = useDispatchWebSocket();

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
      {/* Real-Time Live Signal Dispatch Alert Toast */}
      {latestNotification && (
        <div
          style={{
            backgroundColor: '#1E3A8A',
            border: '1px solid #3B82F6',
            borderRadius: '8px',
            padding: '12px 18px',
            marginBottom: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.4)',
            animation: 'fadeIn 0.3s ease-in-out',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ backgroundColor: '#2563EB', padding: '6px', borderRadius: '50%', color: '#fff' }}>
              <Bell size={16} />
            </div>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#F9FAFB' }}>
                🚀 NEW GRADE-A SIGNAL EMITTED: {latestNotification.symbol} ({latestNotification.setup_type})
              </div>
              <div style={{ fontSize: '11px', color: '#93C5FD' }}>
                Entry: ₹{latestNotification.entry_price.toFixed(2)} | Target 1: ₹{latestNotification.target_1.toFixed(2)} | Stop Loss: ₹{latestNotification.stop_loss.toFixed(2)} | Score: {latestNotification.confidence_score.toFixed(1)}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => {
                clearNotification();
                setActiveTab('scanner');
              }}
              style={{
                backgroundColor: '#2563EB',
                border: 'none',
                color: '#fff',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              View in Scanner <ArrowRight size={12} />
            </button>
            <button
              onClick={clearNotification}
              style={{
                background: 'none',
                border: 'none',
                color: '#9CA3AF',
                cursor: 'pointer',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}

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
