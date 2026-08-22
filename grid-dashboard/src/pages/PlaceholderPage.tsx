import React from 'react';
import { Card } from '../components/common/Card';
import type { NavigationTab } from '../types/dashboard';
import {
  Grid,
  Layers,
  ListOrdered,
  History,
  BarChart3,
  ShieldAlert,
  Settings as SettingsIcon,
} from 'lucide-react';

interface PlaceholderPageProps {
  tab: NavigationTab;
}

const TAB_CONFIGS: Record<
  Exclude<NavigationTab, 'overview'>,
  { title: string; desc: string; icon: React.ReactNode }
> = {
  'active-grids': {
    title: 'Active Grids View',
    desc: 'Manage and monitor multi-level DCA buy/sell grid triggers per coin.',
    icon: <Grid size={32} />,
  },
  positions: {
    title: 'Open Positions View',
    desc: 'Track coin holdings, unrealized P&L, break-even prices, and entry points.',
    icon: <Layers size={32} />,
  },
  orders: {
    title: 'Orders Management View',
    desc: 'View active buy/sell orders, fill statuses, and CoinDCX exchange order IDs.',
    icon: <ListOrdered size={32} />,
  },
  'trade-history': {
    title: 'Trade History Log View',
    desc: 'Audit realized gains, completed cycles, fees, and execution timestamps.',
    icon: <History size={32} />,
  },
  analytics: {
    title: 'Performance Analytics View',
    desc: 'Daily P&L charts, win rates, drawdown stats, and coin profitability breakdown.',
    icon: <BarChart3 size={32} />,
  },
  risk: {
    title: 'Risk & Capital Controls View',
    desc: 'Configure max simultaneous grids, capital caps per coin, and daily loss limits.',
    icon: <ShieldAlert size={32} />,
  },
  settings: {
    title: 'System Settings View',
    desc: 'Polling cadence, Google Drive backup options, and API endpoint configuration.',
    icon: <SettingsIcon size={32} />,
  },
};

export const PlaceholderPage: React.FC<PlaceholderPageProps> = ({ tab }) => {
  if (tab === 'overview') return null;

  const config = TAB_CONFIGS[tab];

  return (
    <Card className="placeholder-view-card">
      <div className="placeholder-icon">{config.icon}</div>
      <h2 className="placeholder-title">{config.title}</h2>
      <p className="placeholder-desc">{config.desc}</p>
      <div
        style={{
          marginTop: '1rem',
          padding: '0.5rem 1rem',
          borderRadius: '9999px',
          background: 'var(--neutral-badge)',
          color: 'var(--text-muted)',
          fontSize: '0.8rem',
        }}
      >
        View Ready for API Data Binding
      </div>
    </Card>
  );
};
