import React from 'react';
import type { ScoredSignalResponse } from '../../types/dashboard';

interface SignalCardProps {
  signal: ScoredSignalResponse;
  onViewDetails: (signal: ScoredSignalResponse) => void;
}

export const SignalCard: React.FC<SignalCardProps> = ({ signal, onViewDetails }) => {
  const getScoreColor = (score: number) => {
    if (score >= 90) return '#10B981';
    if (score >= 80) return '#34D399';
    if (score >= 70) return '#F59E0B';
    if (score >= 60) return '#60A5FA';
    return '#EF4444';
  };

  const getStrengthBadge = (strength: string) => {
    switch (strength) {
      case 'VERY_STRONG':
        return { label: '🔥 VERY STRONG', bg: '#064E3B', color: '#34D399' };
      case 'STRONG':
        return { label: '⚡ STRONG', bg: '#065F46', color: '#10B981' };
      case 'VALID':
        return { label: 'VALID SETUP', bg: '#78350F', color: '#FBBF24' };
      default:
        return { label: strength, bg: '#1F2937', color: '#9CA3AF' };
    }
  };

  const getConfidenceBadge = (conf?: string) => {
    switch (conf) {
      case 'HIGH':
        return { label: 'HIGH CONFIDENCE', color: '#10B981', bg: 'rgba(16, 185, 129, 0.15)' };
      case 'MEDIUM':
        return { label: 'MED CONFIDENCE', color: '#60A5FA', bg: 'rgba(96, 165, 250, 0.15)' };
      default:
        return { label: 'LOW CONFIDENCE', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.15)' };
    }
  };

  const badge = getStrengthBadge(signal.strength);
  const confBadge = getConfidenceBadge(signal.confidence);
  const scoreColor = getScoreColor(signal.total_score);

  return (
    <div
      style={{
        backgroundColor: '#1F2937',
        border: '1px solid #374151',
        borderRadius: '12px',
        padding: '18px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        position: 'relative',
        overflow: 'hidden',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
      }}
    >
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB' }}>
              {signal.symbol.replace('.NS', '')}
            </span>
            <span
              style={{
                fontSize: '11px',
                padding: '2px 8px',
                backgroundColor: '#374151',
                borderRadius: '4px',
                color: '#D1D5DB',
                fontWeight: 600,
              }}
            >
              {signal.sector}
            </span>
            <span
              style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                fontWeight: 700,
                color: confBadge.color,
                backgroundColor: confBadge.bg,
              }}
            >
              {confBadge.label}
            </span>
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '4px' }}>
            {signal.signal_type.replace('_', ' ')} • R:R {signal.risk_reward.rr_ratio}x
          </div>
        </div>

        <div style={{ textAlign: 'right' }}>
          <div
            style={{
              fontSize: '22px',
              fontWeight: 800,
              color: scoreColor,
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'flex-end',
            }}
          >
            {signal.total_score}
            <span style={{ fontSize: '12px', color: '#9CA3AF', marginLeft: '2px' }}>/100</span>
          </div>
          <div
            style={{
              display: 'inline-block',
              padding: '2px 8px',
              backgroundColor: badge.bg,
              color: badge.color,
              borderRadius: '4px',
              fontSize: '10px',
              fontWeight: 700,
              marginTop: '4px',
            }}
          >
            {badge.label}
          </div>
        </div>
      </div>

      {/* Trade Geometry Levels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '8px',
          padding: '10px 12px',
          backgroundColor: '#111827',
          borderRadius: '8px',
          marginBottom: '14px',
          fontSize: '12px',
          textAlign: 'center',
        }}
      >
        <div>
          <div style={{ color: '#9CA3AF', fontSize: '10px' }}>ENTRY</div>
          <div style={{ fontWeight: 700, color: '#60A5FA' }}>₹{signal.risk_reward.entry_price.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ color: '#9CA3AF', fontSize: '10px' }}>STOP LOSS</div>
          <div style={{ fontWeight: 700, color: '#EF4444' }}>₹{signal.risk_reward.stop_loss.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ color: '#9CA3AF', fontSize: '10px' }}>TARGET 1</div>
          <div style={{ fontWeight: 700, color: '#10B981' }}>₹{signal.risk_reward.target_1.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ color: '#9CA3AF', fontSize: '10px' }}>TARGET 2</div>
          <div style={{ fontWeight: 700, color: '#34D399' }}>₹{signal.risk_reward.target_2.toLocaleString()}</div>
        </div>
      </div>

      {/* Structured Rationale Snippets */}
      <div style={{ marginBottom: '14px', flexGrow: 1 }}>
        {signal.rationale.slice(0, 2).map((r, i) => (
          <div
            key={i}
            style={{
              fontSize: '11px',
              color: '#D1D5DB',
              marginBottom: '4px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span style={{ color: '#10B981' }}>•</span>
            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r}</span>
          </div>
        ))}

        {signal.rejection_risks && signal.rejection_risks.length > 0 && (
          <div
            style={{
              fontSize: '11px',
              color: '#FCA5A5',
              marginTop: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <span>⚠️</span>
            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {signal.rejection_risks[0]}
            </span>
          </div>
        )}
      </div>

      {/* Action Footer */}
      <button
        onClick={() => onViewDetails(signal)}
        style={{
          width: '100%',
          padding: '8px 0',
          backgroundColor: '#374151',
          border: '1px solid #4B5563',
          borderRadius: '6px',
          color: '#F9FAFB',
          fontSize: '12px',
          fontWeight: 600,
          cursor: 'pointer',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#4B5563')}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#374151')}
      >
        View Complete Score Breakdown →
      </button>
    </div>
  );
};
