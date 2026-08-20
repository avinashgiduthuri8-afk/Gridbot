import { useState } from 'react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { OverviewPage } from './pages/OverviewPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import type { NavigationTab } from './types/dashboard';

export function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');

  return (
    <DashboardLayout activeTab={activeTab} onTabChange={setActiveTab}>
      {activeTab === 'overview' ? (
        <OverviewPage />
      ) : (
        <PlaceholderPage tab={activeTab} />
      )}
    </DashboardLayout>
  );
}

export default App;
