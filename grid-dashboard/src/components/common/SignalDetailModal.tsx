import React from 'react';
import type { ScoredSignalResponse } from '../../types/dashboard';

interface SignalDetailModalProps {
  signal: ScoredSignalResponse | null;
  onClose: () => void;
}

export const SignalDetailModal: React.FC<SignalDetailModalProps> = ({ signal, onClose }) => {
  if (!signal) return null;

  const b = signal.breakdown;

  const scoreDimensions = [
    { name: 'Technical Trend & EMAs', score: b.technical_trend, max: 20, color: '#3B82F6' },
    { name: 'Momentum (RSI / MACD)', score: b.momentum, max: 15, color: '#8B5CF6' },
    { name: 'Volume & VWAP Confirmation', score: b.volume, max: 15, color: '#10B981' },
    { name: 'Price Action & Setup Trigger', score: b.price_action, max: 15, color: '#F59E0B' },
    { name: 'Multi-Timeframe Alignment', score: b.multi_timeframe, max: 15, color: '#06B6D4' },
    { name: 'Market Regime Fit', score: b.market_regime, max: 10, color: '#EC4899' },
    { name: 'Sector Strength & Alpha', score: b.sector_strength, max: 5, color: '#6366F1' },
    { name: 'News & Corporate Sentiment', score: b.news_sentiment, max: 5, color: '#14B8A6' },
  ];

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#111827',
          border: '1px solid #374151',
          borderRadius: '14px',
          width: '100%',
          maxWidth: '700px',
          maxHeight: '90vh',
          overflowY: 'auto',
          padding: '24px',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid #1F2937',
            paddingBottom: '16px',
            marginBottom: '20px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '24px', fontWeight: 800, color: '#F9FAFB' }}>
                {signal.symbol.replace('.NS', '')}
              </span>
              <span
                style={{
                  padding: '3px 10px',
                  backgroundColor: '#1F2937',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#60A5FA',
                }}
              >
                {signal.sector} (Rank #{signal.sector_rank})
              </span>
              <span
                style={{
                  padding: '3px 10px',
                  backgroundColor: '#064E3B',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#34D399',
                }}
              >
                {signal.strength}
              </span>
              <span
                style={{
                  padding: '3px 10px',
                  backgroundColor: signal.confidence === 'HIGH' ? '#065F46' : '#1E3A8A',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 700,
                  color: signal.confidence === 'HIGH' ? '#34D399' : '#93C5FD',
                }}
              >
                {signal.confidence || 'MEDIUM'} CONFIDENCE
              </span>
            </div>
            <div style={{ fontSize: '13px', color: '#9CA3AF', marginTop: '4px' }}>
              Setup: <strong>{signal.signal_type.replace('_', ' ')}</strong> | Timeframes: {signal.timeframes_summary}
            </div>
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '28px', fontWeight: 900, color: '#10B981' }}>
              {signal.total_score}
              <span style={{ fontSize: '14px', color: '#9CA3AF' }}>/100</span>
            </div>
          </div>
        </div>

        {/* Trade Geometry Plan */}
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '13px', color: '#9CA3AF', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Execution Geometry & Structural Levels
          </h4>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '10px',
              padding: '14px',
              backgroundColor: '#1F2937',
              borderRadius: '10px',
              textAlign: 'center',
            }}
          >
            <div>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>ENTRY TRIGGER</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#60A5FA', marginTop: '2px' }}>
                ₹{signal.risk_reward.entry_price.toLocaleString()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>STOP LOSS</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#EF4444', marginTop: '2px' }}>
                ₹{signal.risk_reward.stop_loss.toLocaleString()}
              </div>
              <div style={{ fontSize: '10px', color: '#F87171' }}>(-{signal.risk_reward.risk_percentage}%)</div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TARGET 1</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#10B981', marginTop: '2px' }}>
                ₹{signal.risk_reward.target_1.toLocaleString()}
              </div>
              <div style={{ fontSize: '10px', color: '#34D399' }}>(+{signal.risk_reward.reward_percentage}%)</div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TARGET 2</div>
              <div style={{ fontSize: '15px', fontWeight: 700, color: '#34D399', marginTop: '2px' }}>
                ₹{signal.risk_reward.target_2.toLocaleString()}
              </div>
              <div style={{ fontSize: '10px', color: '#34D399' }}>(R:R {signal.risk_reward.rr_ratio}x)</div>
            </div>
          </div>
        </div>

        {/* 8-Dimension Score Breakdown */}
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '13px', color: '#9CA3AF', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Score Breakdown (100-Point Institutional Model)
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {scoreDimensions.map((dim, i) => {
              const pct = (dim.score / dim.max) * 100;
              return (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ color: '#E5E7EB', fontWeight: 500 }}>{dim.name}</span>
                    <span style={{ color: '#9CA3AF', fontWeight: 700 }}>
                      <strong style={{ color: dim.color }}>{dim.score}</strong> / {dim.max} pts
                    </span>
                  </div>
                  <div
                    style={{
                      height: '6px',
                      backgroundColor: '#1F2937',
                      borderRadius: '3px',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${pct}%`,
                        backgroundColor: dim.color,
                        borderRadius: '3px',
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Trade Rationale */}
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '13px', color: '#9CA3AF', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Trade Confluence & Confirmation Checklist
          </h4>
          <div
            style={{
              padding: '14px',
              backgroundColor: '#1F2937',
              borderRadius: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            {signal.rationale.map((r, i) => (
              <div key={i} style={{ fontSize: '12px', color: '#D1D5DB', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                <span style={{ color: '#10B981', fontWeight: 700 }}>✓</span>
                <span>{r}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Risk Warnings & Extension Checks */}
        {signal.rejection_risks && signal.rejection_risks.length > 0 && (
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '13px', color: '#F87171', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Identified Setup Risks & Warnings
            </h4>
            <div
              style={{
                padding: '14px',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid #7F1D1D',
                borderRadius: '10px',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
              }}
            >
              {signal.rejection_risks.map((w, i) => (
                <div key={i} style={{ fontSize: '12px', color: '#FCA5A5', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                  <span>⚠️</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Close Button */}
        <button
          onClick={onClose}
          style={{
            width: '100%',
            padding: '10px 0',
            backgroundColor: '#374151',
            border: 'none',
            borderRadius: '8px',
            color: '#F9FAFB',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Close Detail View
        </button>
      </div>
    </div>
  );
};
