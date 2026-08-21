import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { LedgerStatsResponse, ScoredSignalResponse } from '../types/dashboard';
import { SignalDetailModal } from '../components/common/SignalDetailModal';
import { StockDetailDrawer } from '../components/common/StockDetailDrawer';
import { Info } from 'lucide-react';

export const SignalsHistoryPage: React.FC = () => {
  const [signals, setSignals] = useState<any[]>([]);
  const [ledgerStats, setLedgerStats] = useState<LedgerStatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedSignal, setSelectedSignal] = useState<ScoredSignalResponse | null>(null);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const fetchSignals = async () => {
    setLoading(true);
    try {
      const [sigs, stats] = await Promise.all([
        api.getSignalsHistory(50, statusFilter || undefined),
        api.getLedgerStats(),
      ]);
      setSignals(sigs);
      setLedgerStats(stats);
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
        return { label: '🎯 TARGET 2 (+3.5R)', bg: '#064E3B', color: '#34D399' };
      case 'HIT_T1':
        return { label: '✅ TARGET 1 (+2.0R)', bg: '#065F46', color: '#10B981' };
      case 'STOPPED_OUT':
        return { label: '🛑 STOPPED (-1.0R)', bg: '#450A0A', color: '#F87171' };
      case 'EXPIRED':
        return { label: '⏱️ EXPIRED (0.0R)', bg: '#78350F', color: '#FBBF24' };
      default:
        return { label: '🟡 TRACKING LIVE', bg: '#1E3A8A', color: '#60A5FA' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header Banner */}
      <div style={{ backgroundColor: '#1F2937', padding: '16px 20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
          Live Signal Lifecycle Tracker &amp; R-Multiple Ledger
        </h2>
        <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
          Real-time trade state machine (Target 1 / Target 2 / Stop Loss), mathematical R-accounting, and setup win rates
        </p>
      </div>

      {/* Aggregate Institutional R-Scorecard */}
      {ledgerStats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TOTAL SIGNALS GENERATED</div>
            <div style={{ fontSize: '22px', fontWeight: 900, color: '#F9FAFB', marginTop: '2px' }}>
              {ledgerStats.total_signals}
            </div>
            <div style={{ fontSize: '10px', color: '#60A5FA', marginTop: '2px' }}>
              {ledgerStats.active_signals} currently active
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>WIN RATE</div>
            <div style={{ fontSize: '22px', fontWeight: 900, color: ledgerStats.win_rate_pct >= 50 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
              {ledgerStats.win_rate_pct.toFixed(1)}%
            </div>
            <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '2px' }}>
              {ledgerStats.winning_signals}W - {ledgerStats.losing_signals}L
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TOTAL R-MULTIPLES</div>
            <div style={{ fontSize: '22px', fontWeight: 900, color: ledgerStats.total_r_multiple >= 0 ? '#10B981' : '#EF4444', marginTop: '2px' }}>
              {ledgerStats.total_r_multiple >= 0 ? `+${ledgerStats.total_r_multiple.toFixed(1)}R` : `${ledgerStats.total_r_multiple.toFixed(1)}R`}
            </div>
            <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '2px' }}>
              Avg: {ledgerStats.avg_r_per_trade >= 0 ? `+${ledgerStats.avg_r_per_trade.toFixed(2)}R` : `${ledgerStats.avg_r_per_trade.toFixed(2)}R`} / trade
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>PROFIT FACTOR</div>
            <div style={{ fontSize: '22px', fontWeight: 900, color: ledgerStats.profit_factor >= 1.5 ? '#10B981' : '#60A5FA', marginTop: '2px' }}>
              {ledgerStats.profit_factor > 0 ? `${ledgerStats.profit_factor.toFixed(2)}x` : 'N/A'}
            </div>
            <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '2px' }}>
              Gross Gain / Loss R
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TRACKED SETUPS</div>
            <div style={{ fontSize: '22px', fontWeight: 900, color: '#F59E0B', marginTop: '2px' }}>
              {Object.keys(ledgerStats.setup_breakdown).length}
            </div>
            <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '2px' }}>
              VCP, Breakout, Pullback
            </div>
          </div>
        </div>
      )}

      {/* Filter and Signal Ledger Table */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', margin: 0 }}>
            Signal Execution History Log
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
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <option value="">All Statuses</option>
              <option value="HIT_T1">Hit Target 1 (+2.0R)</option>
              <option value="HIT_T2">Hit Target 2 (+3.5R)</option>
              <option value="STOPPED_OUT">Stopped Out (-1.0R)</option>
              <option value="OPEN">Open / Active</option>
            </select>
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                <th style={{ padding: '10px' }}>TIMESTAMP</th>
                <th style={{ padding: '10px' }}>SYMBOL</th>
                <th style={{ padding: '10px' }}>SECTOR</th>
                <th style={{ padding: '10px' }}>SETUP</th>
                <th style={{ padding: '10px' }}>ENTRY</th>
                <th style={{ padding: '10px' }}>STOP LOSS</th>
                <th style={{ padding: '10px' }}>TARGET 1</th>
                <th style={{ padding: '10px' }}>TARGET 2</th>
                <th style={{ padding: '10px' }}>STATUS</th>
                <th style={{ padding: '10px' }}>OUTCOME P&amp;L</th>
                <th style={{ padding: '10px' }}>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {signals.length > 0 ? (
                signals.map((s, i) => {
                  const badge = getStatusBadge(s.status);
                  const cleanSym = s.symbol.replace('.NS', '');
                  return (
                    <tr
                      key={s.signal_id || i}
                      style={{
                        borderBottom: '1px solid #1F2937',
                        color: '#E5E7EB',
                        backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.1)',
                      }}
                    >
                      <td style={{ padding: '10px', fontSize: '11px', color: '#9CA3AF' }}>
                        {s.created_at ? s.created_at.slice(0, 16).replace('T', ' ') : '--'}
                      </td>
                      <td style={{ padding: '10px' }}>
                        <button
                          onClick={() => setDrawerSymbol(cleanSym)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#60A5FA',
                            fontWeight: 800,
                            fontSize: '13px',
                            cursor: 'pointer',
                            padding: 0,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                          title="Open Stock Fundamentals"
                        >
                          {cleanSym} <Info size={12} />
                        </button>
                      </td>
                      <td style={{ padding: '10px', color: '#9CA3AF' }}>{s.sector}</td>
                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            padding: '2px 6px',
                            backgroundColor: '#374151',
                            borderRadius: '4px',
                            fontSize: '11px',
                          }}
                        >
                          {s.signal_type}
                        </span>
                      </td>
                      <td style={{ padding: '10px', fontWeight: 600 }}>₹{s.entry_price.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#EF4444' }}>₹{s.stop_loss.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#10B981' }}>₹{s.target_1.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#34D399' }}>₹{s.target_2.toLocaleString()}</td>
                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '3px 8px',
                            backgroundColor: badge.bg,
                            color: badge.color,
                            borderRadius: '4px',
                            fontSize: '10px',
                            fontWeight: 700,
                          }}
                        >
                          {badge.label}
                        </span>
                      </td>
                      <td style={{ padding: '10px', fontWeight: 700, color: s.outcome_pnl_pct >= 0 ? '#10B981' : '#EF4444' }}>
                        {s.outcome_pnl_pct ? `${s.outcome_pnl_pct >= 0 ? '+' : ''}${s.outcome_pnl_pct.toFixed(2)}%` : '--'}
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
                            padding: '4px 10px',
                            backgroundColor: '#374151',
                            border: 'none',
                            borderRadius: '4px',
                            color: '#F9FAFB',
                            fontSize: '11px',
                            cursor: 'pointer',
                          }}
                        >
                          View Rationale
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={11} style={{ textAlign: 'center', padding: '30px', color: '#9CA3AF' }}>
                    {loading ? 'Loading signal history...' : 'No historical signals logged yet.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Signal Detail Modal */}
      <SignalDetailModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />

      {/* Stock Fundamentals Slide-over Drawer */}
      <StockDetailDrawer symbol={drawerSymbol} onClose={() => setDrawerSymbol(null)} />
    </div>
  );
};
