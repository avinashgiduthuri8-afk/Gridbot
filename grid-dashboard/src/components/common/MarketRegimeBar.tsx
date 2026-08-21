import React from 'react';
import type { MarketRegimeResponse, SessionInfo } from '../../types/dashboard';

interface MarketRegimeBarProps {
  regime?: MarketRegimeResponse | null;
  session?: SessionInfo | null;
  loading?: boolean;
}

export const MarketRegimeBar: React.FC<MarketRegimeBarProps> = ({
  regime,
  session,
  loading: _loading,
}) => {
  const getRegimeColor = (regimeName?: string) => {
    switch (regimeName) {
      case 'STRONG_BULLISH':
        return '#10B981';
      case 'BULLISH':
        return '#34D399';
      case 'NEUTRAL':
        return '#F59E0B';
      case 'BEARISH':
        return '#F87171';
      case 'STRONG_BEARISH':
        return '#EF4444';
      case 'HIGH_VOLATILITY':
        return '#EC4899';
      default:
        return '#6B7280';
    }
  };

  const getSessionBadge = (state?: string) => {
    switch (state) {
      case 'INTRADAY_REGULAR':
        return { label: '🟢 LIVE INTRADAY', color: '#10B981' };
      case 'MARKET_OPEN':
        return { label: '🟡 MARKET OPEN', color: '#F59E0B' };
      case 'PRE_MARKET':
        return { label: '🔵 PRE-MARKET', color: '#3B82F6' };
      case 'MARKET_CLOSE':
        return { label: '🟠 CLOSING SESSION', color: '#F97316' };
      case 'POST_MARKET':
        return { label: '🟣 POST-MARKET', color: '#8B5CF6' };
      default:
        return { label: '⚪ MARKET CLOSED', color: '#6B7280' };
    }
  };

  const sessionBadge = getSessionBadge(session?.session_state);

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 18px',
        backgroundColor: '#111827',
        border: '1px solid #1F2937',
        borderRadius: '10px',
        marginBottom: '18px',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
        <div
          style={{
            padding: '4px 10px',
            backgroundColor: `${getRegimeColor(regime?.regime)}22`,
            border: `1px solid ${getRegimeColor(regime?.regime)}`,
            borderRadius: '6px',
            fontSize: '13px',
            fontWeight: 700,
            color: getRegimeColor(regime?.regime),
            letterSpacing: '0.5px',
          }}
        >
          {regime ? regime.regime.replace('_', ' ') : 'ANALYZING REGIME'}
        </div>

        <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
          <div>
            <span style={{ color: '#9CA3AF' }}>NIFTY 50: </span>
            <strong style={{ color: (regime?.nifty_50_change ?? 0) >= 0 ? '#10B981' : '#EF4444' }}>
              {(regime?.nifty_50_change ?? 0) >= 0 ? '+' : ''}
              {regime?.nifty_50_change?.toFixed(2) ?? '0.00'}%
            </strong>
          </div>

          <div>
            <span style={{ color: '#9CA3AF' }}>BANK NIFTY: </span>
            <strong style={{ color: (regime?.nifty_bank_change ?? 0) >= 0 ? '#10B981' : '#EF4444' }}>
              {(regime?.nifty_bank_change ?? 0) >= 0 ? '+' : ''}
              {regime?.nifty_bank_change?.toFixed(2) ?? '0.00'}%
            </strong>
          </div>

          <div>
            <span style={{ color: '#9CA3AF' }}>INDIA VIX: </span>
            <strong style={{ color: '#F59E0B' }}>
              {regime?.vix_value?.toFixed(1) ?? '14.0'} ({regime?.vix_status ?? 'NORMAL'})
            </strong>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            padding: '4px 10px',
            backgroundColor: '#1F2937',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 600,
            color: sessionBadge.color,
          }}
        >
          {sessionBadge.label}
        </div>
        <div style={{ fontSize: '12px', color: '#9CA3AF' }}>
          {session?.current_time_ist || '09:15 - 15:30 IST'}
        </div>
      </div>
    </div>
  );
};
