import React, { useState } from 'react';
import { StatusBadge } from '../common/StatusBadge';
import { RefreshCw, Radio, ShieldAlert } from 'lucide-react';
import { EmergencyStopModal } from '../common/EmergencyStopModal';
import type { NavigationTab, HealthResponse } from '../../types/dashboard';

interface HeaderProps {
  activeTab: NavigationTab;
  health: HealthResponse | null;
  loading: boolean;
  lastUpdated: Date | null;
  emergencyStopActive?: boolean;
  onRefresh: () => void;
}

const TAB_TITLES: Record<NavigationTab, string> = {
  overview: 'Market Overview & Regime',
  scanner: 'Indian Stock Scanner',
  sectors: 'Sector Strength & Momentum',
  signals: 'Signals Log & MFE/MAE History',
  backtest: 'Scanner Backtesting Suite',
  'active-grids': 'Active Grids',
  positions: 'Open Positions',
  orders: 'Orders Management',
  'trade-history': 'Trade Execution History',
  analytics: 'Performance Analytics',
  risk: 'Risk & Capital Controls',
  settings: 'System Configuration',
};

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  health,
  loading,
  lastUpdated,
  emergencyStopActive = false,
  onRefresh,
}) => {
  const [showEmergencyModal, setShowEmergencyModal] = useState(false);
  const isHealthy = health?.status === 'ok' && health?.database_connected;

  return (
    <>
      <header className="header">
        <div className="header-title-section">
          <h1 className="header-title">{TAB_TITLES[activeTab]}</h1>
          <StatusBadge status="paper" label="NSE / BSE Mode" />
          {emergencyStopActive && (
            <StatusBadge status="error" label="EMERGENCY STOP ON" />
          )}
        </div>

        <div className="header-actions">
          {lastUpdated && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dark)' }}>
              Updated: {lastUpdated.toLocaleTimeString()}
            </span>
          )}

          <button
            className="action-btn"
            onClick={() => setShowEmergencyModal(true)}
            style={{
              backgroundColor: emergencyStopActive ? 'rgba(239, 68, 68, 0.2)' : 'rgba(255, 255, 255, 0.05)',
              borderColor: emergencyStopActive ? 'var(--danger)' : 'var(--border-color)',
              color: emergencyStopActive ? '#fca5a5' : 'var(--text-main)',
            }}
            title="Emergency Stop Controls"
          >
            <ShieldAlert size={14} color={emergencyStopActive ? 'var(--danger)' : 'var(--warning)'} />
            <span>{emergencyStopActive ? 'Emergency Stop: ON' : 'Emergency Stop: OFF'}</span>
          </button>

          <button
            className="action-btn"
            onClick={onRefresh}
            disabled={loading}
            title="Refresh Data"
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>{loading ? 'Refreshing...' : 'Refresh'}</span>
          </button>

          <button className="action-btn" title="Backend Server Status">
            <Radio size={14} color={isHealthy ? '#10b981' : '#ef4444'} />
            <span>{isHealthy ? 'Backend Connected' : 'Disconnected'}</span>
          </button>
        </div>
      </header>

      <EmergencyStopModal
        isOpen={showEmergencyModal}
        currentState={emergencyStopActive}
        onClose={() => setShowEmergencyModal(false)}
        onSuccess={onRefresh}
      />
    </>
  );
};
