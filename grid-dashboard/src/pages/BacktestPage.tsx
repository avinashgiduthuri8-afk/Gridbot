import React, { useState } from 'react';
import { api } from '../services/api';
import type { BacktestReportResponse } from '../types/dashboard';

export const BacktestPage: React.FC = () => {
  const [universe, setUniverse] = useState<string>('NIFTY_50');
  const [lookbackBars, setLookbackBars] = useState<number>(60);
  const [report, setReport] = useState<BacktestReportResponse | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleRunBacktest = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.runBacktest(universe, lookbackBars);
      setReport(res);
    } catch (err: any) {
      setError(err.message || 'Backtest simulation failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ backgroundColor: '#1F2937', padding: '16px 20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
          Scanner Backtesting & Evaluation Simulator
        </h2>
        <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
          Simulates forward price action across Bull, Bear, and Sideways regimes to measure win rate, profit factor, and drawdowns.
        </p>
      </div>

      {/* Simulator Control Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: '#1F2937',
          padding: '16px 20px',
          borderRadius: '12px',
          border: '1px solid #374151',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '2px' }}>
              SIMULATION UNIVERSE
            </label>
            <select
              value={universe}
              onChange={(e) => setUniverse(e.target.value)}
              style={{
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              <option value="NIFTY_50">NIFTY 50 (Core Benchmarks)</option>
              <option value="NIFTY_100">NIFTY 100</option>
              <option value="NIFTY_200">NIFTY 200</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '2px' }}>
              LOOKBACK WINDOW
            </label>
            <select
              value={lookbackBars}
              onChange={(e) => setLookbackBars(Number(e.target.value))}
              style={{
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              <option value={30}>30 Days (Short Term)</option>
              <option value={60}>60 Days (Intermediate)</option>
              <option value={90}>90 Days (Quarterly)</option>
              <option value={120}>120 Days (Multi-Regime)</option>
            </select>
          </div>
        </div>

        <button
          onClick={handleRunBacktest}
          disabled={running}
          style={{
            padding: '10px 22px',
            backgroundColor: running ? '#4B5563' : '#3B82F6',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '8px',
            fontWeight: 700,
            fontSize: '14px',
            cursor: running ? 'not-allowed' : 'pointer',
            boxShadow: '0 4px 14px rgba(59, 130, 246, 0.4)',
          }}
        >
          {running ? '⏳ Simulating Trades...' : '▶ Run Historical Backtest'}
        </button>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', backgroundColor: '#7F1D1D', color: '#FCA5A5', borderRadius: '8px' }}>
          <strong>Backtest Notice:</strong> {error}
        </div>
      )}

      {/* Results Section */}
      {report && (
        <>
          {/* Executive Performance Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
            <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TOTAL SIGNALS TESTED</div>
              <div style={{ fontSize: '22px', fontWeight: 800, color: '#F9FAFB' }}>{report.total_signals}</div>
            </div>
            <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>SIMULATED WIN RATE</div>
              <div style={{ fontSize: '22px', fontWeight: 800, color: '#10B981' }}>{report.win_rate_pct}%</div>
            </div>
            <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>PROFIT FACTOR</div>
              <div style={{ fontSize: '22px', fontWeight: 800, color: '#60A5FA' }}>{report.profit_factor}</div>
            </div>
            <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>AVERAGE RETURN</div>
              <div style={{ fontSize: '22px', fontWeight: 800, color: '#34D399' }}>+{report.avg_return_pct}%</div>
            </div>
            <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
              <div style={{ fontSize: '11px', color: '#9CA3AF' }}>MAX DRAWDOWN</div>
              <div style={{ fontSize: '22px', fontWeight: 800, color: '#EF4444' }}>-{report.max_drawdown_pct}%</div>
            </div>
          </div>

          {/* Regime Breakdown */}
          {Object.keys(report.by_regime).length > 0 && (
            <div style={{ backgroundColor: '#1F2937', padding: '18px', borderRadius: '12px', border: '1px solid #374151' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#F9FAFB', marginBottom: '12px' }}>
                Performance Across Market Regimes
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                {Object.entries(report.by_regime).map(([regimeName, data], i) => (
                  <div key={i} style={{ backgroundColor: '#111827', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ fontSize: '12px', fontWeight: 700, color: '#60A5FA' }}>{regimeName.replace('_', ' ')}</div>
                    <div style={{ fontSize: '11px', color: '#9CA3AF', marginTop: '4px' }}>
                      Signals: <strong>{data.count}</strong> | Win Rate: <strong style={{ color: '#10B981' }}>{data.win_rate}%</strong>
                    </div>
                    <div style={{ fontSize: '11px', color: '#9CA3AF' }}>
                      Avg Return: <strong>{data.avg_return}%</strong>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Simulated Outcomes Log */}
          <div style={{ backgroundColor: '#1F2937', padding: '18px', borderRadius: '12px', border: '1px solid #374151' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#F9FAFB', marginBottom: '12px' }}>
              Simulated Trade Outcomes
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                    <th style={{ padding: '8px' }}>SYMBOL</th>
                    <th style={{ padding: '8px' }}>SETUP</th>
                    <th style={{ padding: '8px' }}>SCORE</th>
                    <th style={{ padding: '8px' }}>ENTRY</th>
                    <th style={{ padding: '8px' }}>EXIT</th>
                    <th style={{ padding: '8px' }}>STATUS</th>
                    <th style={{ padding: '8px' }}>MFE (UP)</th>
                    <th style={{ padding: '8px' }}>MAE (DOWN)</th>
                    <th style={{ padding: '8px' }}>REALIZED PNL</th>
                    <th style={{ padding: '8px' }}>HOLDING</th>
                  </tr>
                </thead>
                <tbody>
                  {report.outcomes.map((o, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #1F2937', color: '#E5E7EB' }}>
                      <td style={{ padding: '8px', fontWeight: 700 }}>{o.symbol.replace('.NS', '')}</td>
                      <td style={{ padding: '8px', color: '#9CA3AF' }}>{o.signal_type}</td>
                      <td style={{ padding: '8px', fontWeight: 700 }}>{o.score}</td>
                      <td style={{ padding: '8px' }}>₹{o.entry_price.toLocaleString()}</td>
                      <td style={{ padding: '8px' }}>₹{o.exit_price.toLocaleString()}</td>
                      <td style={{ padding: '8px' }}>
                        <span
                          style={{
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontWeight: 700,
                            fontSize: '10px',
                            backgroundColor: o.status.startsWith('HIT') ? '#064E3B' : o.status === 'STOPPED_OUT' ? '#450A0A' : '#78350F',
                            color: o.status.startsWith('HIT') ? '#34D399' : o.status === 'STOPPED_OUT' ? '#F87171' : '#FBBF24',
                          }}
                        >
                          {o.status}
                        </span>
                      </td>
                      <td style={{ padding: '8px', color: '#10B981' }}>+{o.mfe_pct}%</td>
                      <td style={{ padding: '8px', color: '#EF4444' }}>-{o.mae_pct}%</td>
                      <td style={{ padding: '8px', fontWeight: 700, color: o.realized_pnl_pct >= 0 ? '#10B981' : '#EF4444' }}>
                        {o.realized_pnl_pct >= 0 ? '+' : ''}{o.realized_pnl_pct}%
                      </td>
                      <td style={{ padding: '8px', color: '#9CA3AF' }}>{o.holding_bars} bars</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
