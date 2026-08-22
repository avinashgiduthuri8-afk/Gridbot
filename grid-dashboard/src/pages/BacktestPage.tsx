import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { StrategyBacktestResponse, StrategyMetadata } from '../types/dashboard';
import {
  PlaySquare,
  TrendingUp,
  Activity,
  Zap,
  RotateCcw,
} from 'lucide-react';

const PRESET_STOCKS = [
  { symbol: 'TATAMOTORS.NS', label: 'Tata Motors (TATAMOTORS)' },
  { symbol: 'RELIANCE.NS', label: 'Reliance Industries (RELIANCE)' },
  { symbol: 'TCS.NS', label: 'Tata Consultancy (TCS)' },
  { symbol: 'INFY.NS', label: 'Infosys (INFY)' },
  { symbol: 'HDFCBANK.NS', label: 'HDFC Bank (HDFCBANK)' },
  { symbol: 'ICICIBANK.NS', label: 'ICICI Bank (ICICIBANK)' },
  { symbol: 'LT.NS', label: 'Larsen & Toubro (LT)' },
  { symbol: 'BHARTIARTL.NS', label: 'Bharti Airtel (BHARTIARTL)' },
];

export const BacktestPage: React.FC = () => {
  const [symbol, setSymbol] = useState<string>('TATAMOTORS.NS');
  const [strategy, setStrategy] = useState<string>('VCP_BREAKOUT');
  const [lookbackBars, setLookbackBars] = useState<number>(250);
  const [initialCapital, setInitialCapital] = useState<number>(500000);
  const [riskPct, setRiskPct] = useState<number>(1.0);
  const [target1RR, setTarget1RR] = useState<number>(2.0);
  const [target2RR, setTarget2RR] = useState<number>(3.5);
  const [useTrailingSL, setUseTrailingSL] = useState<boolean>(true);

  const [strategies, setStrategies] = useState<StrategyMetadata[]>([]);
  const [result, setResult] = useState<StrategyBacktestResponse | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadStrategies = async () => {
      try {
        const strats = await api.getStrategies();
        if (strats && strats.length > 0) {
          setStrategies(strats);
        }
      } catch (err) {
        console.error('Failed to fetch strategy catalogue:', err);
      }
    };
    loadStrategies();
    handleRunSimulation();
  }, []);

  const handleRunSimulation = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.runBacktest({
        symbol,
        strategy,
        lookback_bars: lookbackBars,
        initial_capital: initialCapital,
        risk_pct_per_trade: riskPct,
        target_1_rr: target1RR,
        target_2_rr: target2RR,
        use_trailing_sl: useTrailingSL,
      });
      setResult(res);
    } catch (err: any) {
      setError(err.message || 'Backtest simulation failed');
    } finally {
      setRunning(false);
    }
  };

  const activeStrategyMeta = strategies.find((s) => s.id === strategy);

  // SVG Equity Curve points generator
  const renderEquityChart = () => {
    if (!result || !result.equity_curve || result.equity_curve.length < 2) {
      return (
        <div style={{ height: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9CA3AF' }}>
          No equity curve data available for this simulation.
        </div>
      );
    }

    const curve = result.equity_curve;
    const width = 800;
    const height = 220;
    const padding = 35;

    const values = curve.map((p) => p.portfolio_value);
    const benchValues = curve.map((p) => p.benchmark_value);
    const allValues = [...values, ...benchValues];

    const minVal = Math.min(...allValues) * 0.98;
    const maxVal = Math.max(...allValues) * 1.02;
    const range = maxVal - minVal || 1;

    const getX = (idx: number) => padding + (idx / (curve.length - 1)) * (width - padding * 2);
    const getY = (val: number) => height - padding - ((val - minVal) / range) * (height - padding * 2);

    const portfolioPoints = curve.map((p, idx) => `${getX(idx)},${getY(p.portfolio_value)}`).join(' ');
    const benchmarkPoints = curve.map((p, idx) => `${getX(idx)},${getY(p.benchmark_value)}`).join(' ');

    const areaPoints = `${getX(0)},${height - padding} ${portfolioPoints} ${getX(curve.length - 1)},${height - padding}`;

    return (
      <div style={{ width: '100%', overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: '220px' }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#3B82F6" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="#374151" strokeDasharray="3,3" />
          <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke="#374151" strokeDasharray="3,3" />
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#374151" />

          {/* Fill Area */}
          <polygon points={areaPoints} fill="url(#equityGradient)" />

          {/* Benchmark Line */}
          <polyline points={benchmarkPoints} fill="none" stroke="#6B7280" strokeWidth="1.5" strokeDasharray="4,4" />

          {/* Portfolio Equity Line */}
          <polyline points={portfolioPoints} fill="none" stroke="#3B82F6" strokeWidth="2.5" />

          {/* Axis Labels */}
          <text x={padding} y={height - 12} fill="#9CA3AF" fontSize="11">
            {curve[0].date}
          </text>
          <text x={width - padding - 60} y={height - 12} fill="#9CA3AF" fontSize="11">
            {curve[curve.length - 1].date}
          </text>
          <text x={padding} y={padding - 8} fill="#9CA3AF" fontSize="11">
            ₹{(maxVal / 100000).toFixed(2)}L
          </text>
          <text x={padding} y={height - padding - 6} fill="#9CA3AF" fontSize="11">
            ₹{(minVal / 100000).toFixed(2)}L
          </text>
        </svg>

        <div style={{ display: 'flex', justifyContent: 'center', gap: '20px', fontSize: '12px', marginTop: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '3px', backgroundColor: '#3B82F6', display: 'inline-block' }} />
            <span style={{ color: '#E5E7EB', fontWeight: 600 }}>Strategy Portfolio Equity</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '2px', backgroundColor: '#6B7280', display: 'inline-block' }} />
            <span style={{ color: '#9CA3AF' }}>Buy &amp; Hold Benchmark</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: '#1F2937',
          padding: '18px 24px',
          borderRadius: '12px',
          border: '1px solid #374151',
          gap: '12px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PlaySquare size={22} color="#3B82F6" /> Multi-Strategy Stock Backtesting &amp; Simulation Engine
          </h2>
          <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
            Simulate institutional setups candle-by-candle with dynamic R-multiples, trailing exits, and equity curve compounding
          </p>
        </div>

        <button
          onClick={handleRunSimulation}
          disabled={running}
          style={{
            backgroundColor: '#2563EB',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '8px',
            padding: '10px 20px',
            fontSize: '13px',
            fontWeight: 700,
            cursor: running ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 4px 6px -1px rgba(37, 99, 235, 0.4)',
          }}
        >
          {running ? <RotateCcw size={16} className="spin" /> : <Zap size={16} />}
          {running ? 'Running Simulation...' : '⚡ Run Simulation'}
        </button>
      </div>

      {/* Interactive Control Panel */}
      <div
        style={{
          backgroundColor: '#1F2937',
          padding: '20px',
          borderRadius: '12px',
          border: '1px solid #374151',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px',
        }}
      >
        {/* Stock Symbol Selection */}
        <div>
          <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px', fontWeight: 700 }}>
            STOCK SYMBOL / PRESETS
          </label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            style={{
              width: '100%',
              backgroundColor: '#111827',
              color: '#F9FAFB',
              border: '1px solid #4B5563',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            {PRESET_STOCKS.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {/* Strategy Selector */}
        <div>
          <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px', fontWeight: 700 }}>
            INSTITUTIONAL STRATEGY
          </label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            style={{
              width: '100%',
              backgroundColor: '#111827',
              color: '#F9FAFB',
              border: '1px solid #4B5563',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            <option value="VCP_BREAKOUT">Minervini VCP Breakout</option>
            <option value="POCKET_PIVOT">Pocket Pivot Momentum (10/20 EMA)</option>
            <option value="NR7_COMPRESSION">NR7 Volatility Squeeze</option>
            <option value="HIGH_DELIVERY_BREAKOUT">High-Delivery Institutional Breakout</option>
            <option value="COMBINED_CONFLUENCE">Combined Confluence (Grade-A)</option>
          </select>
        </div>

        {/* Lookback Period */}
        <div>
          <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px', fontWeight: 700 }}>
            HISTORICAL HORIZON
          </label>
          <select
            value={lookbackBars}
            onChange={(e) => setLookbackBars(Number(e.target.value))}
            style={{
              width: '100%',
              backgroundColor: '#111827',
              color: '#F9FAFB',
              border: '1px solid #4B5563',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            <option value={250}>1 Year (250 Daily Sessions)</option>
            <option value={500}>2 Years (500 Daily Sessions)</option>
            <option value={750}>3 Years (750 Daily Sessions)</option>
            <option value={1250}>5 Years (1250 Daily Sessions)</option>
          </select>
        </div>

        {/* Capital & Risk Sizing */}
        <div>
          <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px', fontWeight: 700 }}>
            STARTING CAPITAL &amp; RISK (%)
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value))}
              style={{
                width: '65%',
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '8px 12px',
                fontSize: '13px',
              }}
            />
            <input
              type="number"
              step="0.1"
              value={riskPct}
              title="Risk % per Trade"
              onChange={(e) => setRiskPct(Number(e.target.value))}
              style={{
                width: '35%',
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '8px 10px',
                fontSize: '13px',
              }}
            />
          </div>
        </div>

        {/* Risk / Reward T1 & T2 Multipliers */}
        <div>
          <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px', fontWeight: 700 }}>
            TARGET 1 &amp; 2 MULTIPLIERS
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="number"
              step="0.1"
              value={target1RR}
              title="Target 1 R-Multiple"
              onChange={(e) => setTarget1RR(Number(e.target.value))}
              style={{
                width: '50%',
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '8px 10px',
                fontSize: '13px',
              }}
            />
            <input
              type="number"
              step="0.1"
              value={target2RR}
              title="Target 2 R-Multiple"
              onChange={(e) => setTarget2RR(Number(e.target.value))}
              style={{
                width: '50%',
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '8px 10px',
                fontSize: '13px',
              }}
            />
          </div>
        </div>

        {/* Trailing SL Checkbox */}
        <div style={{ display: 'flex', alignItems: 'center', marginTop: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', color: '#E5E7EB' }}>
            <input
              type="checkbox"
              checked={useTrailingSL}
              onChange={(e) => setUseTrailingSL(e.target.checked)}
              style={{ width: '16px', height: '16px', accentColor: '#2563EB' }}
            />
            <span>Enable 20 EMA Trailing Exit</span>
          </label>
        </div>
      </div>

      {/* Strategy Description Callout */}
      {activeStrategyMeta && (
        <div
          style={{
            backgroundColor: 'rgba(59, 130, 246, 0.08)',
            borderLeft: '4px solid #3B82F6',
            padding: '12px 16px',
            borderRadius: '0 8px 8px 0',
            fontSize: '13px',
            color: '#D1D5DB',
          }}
        >
          <strong style={{ color: '#60A5FA' }}>{activeStrategyMeta.name}:</strong> {activeStrategyMeta.description}
        </div>
      )}

      {error && (
        <div style={{ backgroundColor: '#450A0A', color: '#F87171', padding: '12px 16px', borderRadius: '8px', border: '1px solid #7F1D1D' }}>
          <strong>Simulation Error:</strong> {error}
        </div>
      )}

      {/* KPI Performance Scorecard Grid */}
      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>WIN RATE (%)</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: result.win_rate_pct >= 50 ? '#10B981' : '#F59E0B', marginTop: '4px' }}>
              {result.win_rate_pct.toFixed(1)}%
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>
              {result.winning_trades} Wins / {result.losing_trades} Losses
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>PROFIT FACTOR</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: result.profit_factor >= 1.5 ? '#10B981' : '#E5E7EB', marginTop: '4px' }}>
              {result.profit_factor.toFixed(2)}
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>Gross Win/Loss ratio</div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>NET PROFIT / ROI</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: result.net_pnl_pct >= 0 ? '#10B981' : '#EF4444', marginTop: '4px' }}>
              {result.net_pnl_pct >= 0 ? '+' : ''}{result.net_pnl_pct.toFixed(1)}%
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>
              ₹{result.net_pnl_amount.toLocaleString('en-IN')}
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>EXPECTANCY (R)</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: result.expectancy_r >= 0.5 ? '#10B981' : '#E5E7EB', marginTop: '4px' }}>
              +{result.expectancy_r.toFixed(2)}R
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>Avg R-multiple per trade</div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>MAX DRAWDOWN</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: result.max_drawdown_pct <= 12 ? '#10B981' : '#EF4444', marginTop: '4px' }}>
              {result.max_drawdown_pct.toFixed(1)}%
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>Peak to valley drop</div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>SHARPE RATIO</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: result.sharpe_ratio >= 1.0 ? '#60A5FA' : '#9CA3AF', marginTop: '4px' }}>
              {result.sharpe_ratio.toFixed(2)}
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>Annualized risk-adj return</div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>TOTAL TRADES</div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: '#F9FAFB', marginTop: '4px' }}>
              {result.total_trades}
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>
              Avg hold: {result.avg_holding_days.toFixed(1)} days
            </div>
          </div>

          <div style={{ backgroundColor: '#1F2937', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>WIN / LOSS STREAK</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', marginTop: '6px' }}>
              W: {result.max_win_streak} / L: {result.max_loss_streak}
            </div>
            <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>Consecutive trades</div>
          </div>
        </div>
      )}

      {/* Equity Curve Chart */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TrendingUp size={18} color="#3B82F6" /> Historical Cumulative Equity Growth vs Benchmark
        </h3>
        {renderEquityChart()}
      </div>

      {/* Detailed Trade Journal Table */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={18} color="#10B981" /> Simulated Trade Journal &amp; R-Multiple Ledger
        </h3>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                <th style={{ padding: '10px' }}>TRADE ID</th>
                <th style={{ padding: '10px' }}>ENTRY DATE</th>
                <th style={{ padding: '10px' }}>ENTRY PRICE</th>
                <th style={{ padding: '10px' }}>EXIT DATE</th>
                <th style={{ padding: '10px' }}>EXIT PRICE</th>
                <th style={{ padding: '10px' }}>OUTCOME / REASON</th>
                <th style={{ padding: '10px' }}>NET P&amp;L (₹)</th>
                <th style={{ padding: '10px' }}>R-MULTIPLE</th>
                <th style={{ padding: '10px' }}>HOLD (DAYS)</th>
              </tr>
            </thead>
            <tbody>
              {result && result.trades && result.trades.length > 0 ? (
                result.trades.map((t) => (
                  <tr key={t.trade_id} style={{ borderBottom: '1px solid #1F2937', color: '#E5E7EB' }}>
                    <td style={{ padding: '10px', fontWeight: 700, color: '#60A5FA' }}>{t.trade_id}</td>
                    <td style={{ padding: '10px', color: '#9CA3AF' }}>{t.entry_date}</td>
                    <td style={{ padding: '10px', fontWeight: 600 }}>₹{t.entry_price.toFixed(2)}</td>
                    <td style={{ padding: '10px', color: '#9CA3AF' }}>{t.exit_date}</td>
                    <td style={{ padding: '10px', fontWeight: 600 }}>₹{t.exit_price.toFixed(2)}</td>
                    <td style={{ padding: '10px' }}>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: 700,
                          backgroundColor:
                            t.exit_reason === 'HIT_T2'
                              ? '#064E3B'
                              : t.exit_reason === 'HIT_T1'
                              ? '#065F46'
                              : t.exit_reason === 'TRAILING_SL'
                              ? '#1E3A8A'
                              : '#450A0A',
                          color:
                            t.exit_reason.includes('HIT')
                              ? '#34D399'
                              : t.exit_reason === 'TRAILING_SL'
                              ? '#93C5FD'
                              : '#F87171',
                        }}
                      >
                        {t.exit_reason}
                      </span>
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        fontWeight: 700,
                        color: t.pnl_amount >= 0 ? '#10B981' : '#EF4444',
                      }}
                    >
                      {t.pnl_amount >= 0 ? '+' : ''}₹{t.pnl_amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        fontWeight: 700,
                        color: t.r_multiple >= 0 ? '#10B981' : '#EF4444',
                      }}
                    >
                      {t.r_multiple >= 0 ? '+' : ''}{t.r_multiple.toFixed(2)}R
                    </td>
                    <td style={{ padding: '10px', color: '#D1D5DB' }}>{t.holding_days}d</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '24px', color: '#9CA3AF' }}>
                    {running ? 'Running simulation...' : 'No historical trades generated for the selected parameters.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
