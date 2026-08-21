import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { SignalPerformanceStats, ScoredSignalResponse } from '../types/dashboard';
import { SignalDetailModal } from '../components/common/SignalDetailModal';

export const SignalsHistoryPage: React.FC = () => {
  const [signals, setSignals] = useState<any[]>([]);
  const [performance, setPerformance] = useState<SignalPerformanceStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedSignal, setSelectedSignal] = useState<ScoredSignalResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const fetchSignals = async () => {
    setLoading(true);
    try {
      const [sigs, perf] = await Promise.all([
        api.getSignalsHistory(50, statusFilter || undefined),
        api.getSignalPerformance(),
      ]);
      setSignals(sigs);
      setPerformance(perf);
    } catch (err) {
      console.error('Failed to load signals history', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSignals();
  }, [statusFilter]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'HIT_T2':
        return { label: '🎯 HIT TARGET 2', bg: '#064E3B', color: '#34D399' };
      case 'HIT_T1':
        return { label: '✅ HIT TARGET 1', bg: '#065F46', color: '#10B981' };
      case 'STOPPED_OUT':
        return { label: '🛑 STOPPED OUT', bg: '#450A0A', color: '#F87171' };
      case 'EXPIRED':
        return { label: '⏱️ EXPIRED', bg: '#78350F', color: '#FBBF24' };
      default:
        return { label: '🟡 OPEN SIGNAL', bg: '#1E3A8A', color: '#60A5FA' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ backgroundColor: '#1F2937', padding: '16px 20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
          Historical Signal Performance & Excursion Tracking
        </h2>
        <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
          Tracking Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE), and Win Rate outcomes
        </p>
      </div>

      {/* Aggregate Stats Cards */}
      {performance && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TOTAL SIGNALS</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB' }}>{performance.total_signals}</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>WIN RATE</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#10B981' }}>{performance.win_rate_pct}%</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>AVG RISK/REWARD</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#60A5FA' }}>{performance.avg_rr}x</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>AVG MFE (UPWARD)</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#34D399' }}>+{performance.avg_mfe}%</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>AVG MAE (DRAWDOWN)</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#F87171' }}>-{performance.avg_mae}%</div>
          </div>
        </div>
      )}

      {/* Filter and Table */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', margin: 0 }}>
            Signal History Log
          </h3>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', color: '#9CA3AF' }}>Filter Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '4px 10px',
                fontSize: '12px',
              }}
            >
              <option value="">All Statuses</option>
              <option value="OPEN">Open Only</option>
              <option value="HIT_T1">Hit Target 1</option>
              <option value="HIT_T2">Hit Target 2</option>
              <option value="STOPPED_OUT">Stopped Out</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px', color: '#9CA3AF' }}>Loading signals history...</div>
        ) : signals.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: '#9CA3AF' }}>No signals recorded in database yet.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                  <th style={{ padding: '10px' }}>DATE / TIME</th>
                  <th style={{ padding: '10px' }}>SYMBOL</th>
                  <th style={{ padding: '10px' }}>SETUP</th>
                  <th style={{ padding: '10px' }}>SCORE</th>
                  <th style={{ padding: '10px' }}>ENTRY</th>
                  <th style={{ padding: '10px' }}>STOP LOSS</th>
                  <th style={{ padding: '10px' }}>TARGET 1</th>
                  <th style={{ padding: '10px' }}>R:R</th>
                  <th style={{ padding: '10px' }}>STATUS</th>
                  <th style={{ padding: '10px' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => {
                  const badge = getStatusBadge(s.status);
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid #1F2937', color: '#E5E7EB' }}>
                      <td style={{ padding: '10px', color: '#9CA3AF', fontSize: '11px' }}>
                        {s.created_at ? s.created_at.slice(0, 16).replace('T', ' ') : ''}
                      </td>
                      <td style={{ padding: '10px', fontWeight: 700 }}>{s.symbol.replace('.NS', '')}</td>
                      <td style={{ padding: '10px' }}>
                        <span style={{ padding: '2px 6px', backgroundColor: '#374151', borderRadius: '4px', fontSize: '11px' }}>
                          {s.signal_type}
                        </span>
                      </td>
                      <td style={{ padding: '10px', fontWeight: 700, color: s.score >= 80 ? '#10B981' : '#60A5FA' }}>
                        {s.score}
                      </td>
                      <td style={{ padding: '10px' }}>₹{s.entry_price.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#EF4444' }}>₹{s.stop_loss.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#10B981' }}>₹{s.target_1.toLocaleString()}</td>
                      <td style={{ padding: '10px', fontWeight: 600 }}>{s.risk_reward}x</td>
                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            padding: '3px 8px',
                            borderRadius: '4px',
                            fontSize: '10px',
                            fontWeight: 700,
                            backgroundColor: badge.bg,
                            color: badge.color,
                          }}
                        >
                          {badge.label}
                        </span>
                      </td>
                      <td style={{ padding: '10px' }}>
                        <button
                          onClick={() => {
                            const formattedSig: ScoredSignalResponse = {
                              symbol: s.symbol,
                              signal_type: s.signal_type,
                              strength: s.strength,
                              total_score: s.score,
                              breakdown: s.breakdown,
                              risk_reward: {
                                symbol: s.symbol,
                                entry_price: s.entry_price,
                                stop_loss: s.stop_loss,
                                target_1: s.target_1,
                                target_2: s.target_2,
                                risk_amount: s.entry_price - s.stop_loss,
                                reward_amount: s.target_1 - s.entry_price,
                                risk_percentage: ((s.entry_price - s.stop_loss) / s.entry_price * 100),
                                reward_percentage: ((s.target_1 - s.entry_price) / s.entry_price * 100),
                                rr_ratio: s.risk_reward,
                                is_acceptable: true,
                              },
                              sector: s.sector,
                              sector_rank: 0,
                              market_regime: s.market_regime,
                              timeframes_summary: s.timeframe_summary,
                              rationale: s.rationale,
                              timestamp: s.created_at,
                              is_tradable: true,
                            };
                            setSelectedSignal(formattedSig);
                          }}
                          style={{
                            padding: '4px 8px',
                            backgroundColor: '#374151',
                            border: 'none',
                            borderRadius: '4px',
                            color: '#F9FAFB',
                            fontSize: '11px',
                            cursor: 'pointer',
                          }}
                        >
                          View Breakdown
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <SignalDetailModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
    </div>
  );
};
