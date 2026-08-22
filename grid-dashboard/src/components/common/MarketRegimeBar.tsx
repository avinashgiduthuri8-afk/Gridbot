import React from 'react';
import type { MarketRegimeResponse, SessionInfo } from '../../types/dashboard';
import { Activity, ShieldAlert, ShieldCheck, Shield } from 'lucide-react';

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
  const getRegimeBadge = (regimeName?: string) => {
    switch (regimeName) {
      case 'STRONG_BULLISH':
        return { label: '🚀 STRONG BULLISH', bg: '#064E3B', color: '#34D399', border: '#10B981' };
      case 'BULLISH':
        return { label: '🟢 BULLISH TRENDING', bg: '#065F46', color: '#10B981', border: '#059669' };
      case 'NEUTRAL':
        return { label: '🟡 SIDEWAYS RANGE', bg: '#78350F', color: '#FBBF24', border: '#F59E0B' };
      case 'BEARISH':
        return { label: '🔴 BEARISH DOWNTREND', bg: '#450A0A', color: '#F87171', border: '#EF4444' };
      case 'STRONG_BEARISH':
        return { label: '⚠️ STAGE-4 DOWNTREND', bg: '#450A0A', color: '#FCA5A5', border: '#DC2626' };
      case 'HIGH_VOLATILITY':
        return { label: '⚡ HIGH VOLATILITY VIX', bg: '#500724', color: '#F472B6', border: '#DB2777' };
      default:
        return { label: '📊 ANALYZING REGIME', bg: '#1F2937', color: '#9CA3AF', border: '#374151' };
    }
  };

  const getSessionBadge = (state?: string) => {
    switch (state) {
      case 'INTRADAY_REGULAR':
        return { label: '🟢 LIVE INTRADAY (09:15–15:30 IST)', color: '#10B981', bg: '#064E3B' };
      case 'MARKET_OPEN':
        return { label: '🟡 MARKET OPENING (09:15 IST)', color: '#FBBF24', bg: '#78350F' };
      case 'PRE_MARKET':
        return { label: '🔵 PRE-MARKET (09:00–09:15 IST)', color: '#60A5FA', bg: '#1E3A8A' };
      case 'MARKET_CLOSE':
        return { label: '🟠 CLOSING AUCTION (15:30 IST)', color: '#FB923C', bg: '#7C2D12' };
      case 'POST_MARKET':
        return { label: '🟣 POST-MARKET (15:40–16:00 IST)', color: '#C084FC', bg: '#581C87' };
      default:
        return { label: '⚪ MARKET CLOSED', color: '#9CA3AF', bg: '#1F2937' };
    }
  };

  const vixValue = regime?.vix_value ?? 14.2;
  const getVixStatus = (val: number) => {
    if (val < 15.0) return { label: 'SAFE (<15)', color: '#10B981', icon: <ShieldCheck size={14} /> };
    if (val <= 18.0) return { label: 'CAUTION (15-18)', color: '#F59E0B', icon: <Shield size={14} /> };
    return { label: 'HIGH RISK (>18)', color: '#EF4444', icon: <ShieldAlert size={14} /> };
  };

  const regimeBadge = getRegimeBadge(regime?.regime);
  const sessionBadge = getSessionBadge(session?.session_state);
  const vixStatus = getVixStatus(vixValue);

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 20px',
        backgroundColor: '#111827',
        border: '1px solid #1F2937',
        borderRadius: '12px',
        marginBottom: '18px',
        gap: '14px',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
      }}
    >
      {/* Left: Regime Pill & Index Trends */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
        <div
          style={{
            padding: '5px 12px',
            backgroundColor: regimeBadge.bg,
            border: `1px solid ${regimeBadge.border}`,
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 800,
            color: regimeBadge.color,
            letterSpacing: '0.5px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          {regimeBadge.label}
        </div>

        <div style={{ display: 'flex', gap: '18px', fontSize: '13px', alignItems: 'center' }}>
          <div>
            <span style={{ color: '#9CA3AF', fontSize: '11px', display: 'block' }}>NIFTY 50 (20/50 EMA)</span>
            <strong style={{ color: (regime?.nifty_50_change ?? 0) >= 0 ? '#10B981' : '#EF4444', fontFamily: 'monospace' }}>
              {(regime?.nifty_50_change ?? 0) >= 0 ? '+' : ''}
              {regime?.nifty_50_change?.toFixed(2) ?? '0.00'}%
            </strong>
          </div>

          <div style={{ borderLeft: '1px solid #374151', height: '24px' }} />

          <div>
            <span style={{ color: '#9CA3AF', fontSize: '11px', display: 'block' }}>BANK NIFTY</span>
            <strong style={{ color: (regime?.nifty_bank_change ?? 0) >= 0 ? '#10B981' : '#EF4444', fontFamily: 'monospace' }}>
              {(regime?.nifty_bank_change ?? 0) >= 0 ? '+' : ''}
              {regime?.nifty_bank_change?.toFixed(2) ?? '0.00'}%
            </strong>
          </div>

          <div style={{ borderLeft: '1px solid #374151', height: '24px' }} />

          {/* India VIX Gauge */}
          <div>
            <span style={{ color: '#9CA3AF', fontSize: '11px', display: 'block' }}>INDIA VIX GAUGE</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '1px' }}>
              <span style={{ color: vixStatus.color }}>{vixStatus.icon}</span>
              <strong style={{ color: vixStatus.color, fontFamily: 'monospace' }}>
                {vixValue.toFixed(1)}
              </strong>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  color: vixStatus.color,
                  padding: '1px 5px',
                  backgroundColor: `${vixStatus.color}18`,
                  borderRadius: '4px',
                }}
              >
                {vixStatus.label}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Right: Session Clock & Status Pill */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            padding: '5px 12px',
            backgroundColor: sessionBadge.bg,
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 700,
            color: sessionBadge.color,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Activity size={13} />
          {sessionBadge.label}
        </div>
        <div style={{ fontSize: '12px', color: '#9CA3AF', fontFamily: 'monospace' }}>
          {session?.current_time_ist || 'IST'}
        </div>
      </div>
    </div>
  );
};
