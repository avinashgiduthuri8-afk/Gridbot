import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { ScanResponse, ScoredSignalResponse, StockInfoResponse } from '../types/dashboard';
import { MarketRegimeBar } from '../components/common/MarketRegimeBar';
import { SignalCard } from '../components/common/SignalCard';
import { SignalDetailModal } from '../components/common/SignalDetailModal';
import { StockDetailDrawer } from '../components/common/StockDetailDrawer';
import { Info } from 'lucide-react';

export const ScannerPage: React.FC = () => {
  const [universe, setUniverse] = useState<string>('NIFTY_100');
  const [maxSignals, setMaxSignals] = useState<number>(3);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [batchInfoMap, setBatchInfoMap] = useState<Record<string, StockInfoResponse>>({});
  const [scanning, setScanning] = useState<boolean>(false);
  const [selectedSignal, setSelectedSignal] = useState<ScoredSignalResponse | null>(null);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load initial cached scan on mount
  useEffect(() => {
    const fetchInitialScan = async () => {
      try {
        const res = await api.getLatestScan();
        if (res && res.top_signals) {
          setScanResult(res);
          loadBatchInfo(res);
        }
      } catch {
        // Silent fallback
      }
    };
    fetchInitialScan();
  }, []);

  const loadBatchInfo = async (scan: ScanResponse) => {
    try {
      const symbols = [
        ...scan.top_signals.map((s) => s.symbol),
        ...scan.watchlist.map((s) => s.symbol),
      ];
      if (symbols.length > 0) {
        const infoMap = await api.getBatchStockInfo(symbols);
        setBatchInfoMap(infoMap);
      }
    } catch (err) {
      console.error('Failed loading batch stock info:', err);
    }
  };

  const handleRunScan = async () => {
    setScanning(true);
    setError(null);
    try {
      const res = await api.triggerScan(universe, maxSignals);
      setScanResult(res);
      await loadBatchInfo(res);
    } catch (err: any) {
      setError(err.message || 'Scan execution failed');
    } finally {
      setScanning(false);
    }
  };

  const getDeliveryBadge = (pct?: number) => {
    if (pct === undefined || pct === null) return null;
    let bg = '#374151';
    let color = '#9CA3AF';
    if (pct >= 50) {
      bg = '#064E3B';
      color = '#34D399';
    } else if (pct >= 35) {
      bg = '#78350F';
      color = '#FBBF24';
    }
    return (
      <span
        style={{
          padding: '2px 6px',
          borderRadius: '4px',
          fontSize: '11px',
          fontWeight: 700,
          backgroundColor: bg,
          color: color,
        }}
      >
        {pct.toFixed(0)}%
      </span>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Market Regime & Session Clock Bar */}
      <MarketRegimeBar regime={scanResult?.regime} session={scanResult?.session_info} />

      {/* Control Header & Scan Trigger */}
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
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
            Institutional Indian Stock Scanner
          </h2>
          <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
            12-Stage multi-timeframe confluence engine (1D Structure + 1H Setup + 15M Trigger)
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {/* Universe Selector */}
          <div>
            <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '2px' }}>
              STOCK UNIVERSE
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
                cursor: 'pointer',
              }}
            >
              <option value="NIFTY_50">NIFTY 50 (Large Cap Core)</option>
              <option value="NIFTY_100">NIFTY 100 (Standard)</option>
              <option value="NIFTY_200">NIFTY 200 (Large + Mid)</option>
              <option value="NIFTY_500">NIFTY 500 (Broad Equities)</option>
            </select>
          </div>

          {/* Max Final Signals */}
          <div>
            <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '2px' }}>
              MAX SIGNALS
            </label>
            <select
              value={maxSignals}
              onChange={(e) => setMaxSignals(Number(e.target.value))}
              style={{
                backgroundColor: '#111827',
                color: '#F9FAFB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <option value={1}>Top 1 Signal</option>
              <option value={2}>Top 2 Signals</option>
              <option value={3}>Top 3 Signals (Standard)</option>
              <option value={5}>Top 5 Signals</option>
            </select>
          </div>

          {/* Scan Action Button */}
          <div style={{ alignSelf: 'flex-end' }}>
            <button
              onClick={handleRunScan}
              disabled={scanning}
              style={{
                backgroundColor: scanning ? '#4B5563' : '#10B981',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: '6px',
                padding: '8px 20px',
                fontSize: '14px',
                fontWeight: 700,
                cursor: scanning ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              {scanning ? '⏳ Scanning Market...' : '⚡ Scan Indian Market'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid #7F1D1D',
            borderRadius: '8px',
            color: '#FCA5A5',
            fontSize: '13px',
          }}
        >
          <strong>Scanner Notice:</strong> {error}
        </div>
      )}

      {/* Metrics Banner */}
      {scanResult && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: '12px',
          }}
        >
          <div style={{ backgroundColor: '#1F2937', padding: '12px 16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TOTAL CANDIDATES</div>
            <div style={{ fontSize: '18px', fontWeight: 800, color: '#F9FAFB' }}>{scanResult.total_scanned}</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '12px 16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>PASSED LIQUIDITY</div>
            <div style={{ fontSize: '18px', fontWeight: 800, color: '#60A5FA' }}>{scanResult.total_passed_liquidity}</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '12px 16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>TOP CONVICTION SETUPS</div>
            <div style={{ fontSize: '18px', fontWeight: 800, color: '#10B981' }}>{scanResult.top_signals.length}</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '12px 16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>WATCHLIST CANDIDATES</div>
            <div style={{ fontSize: '18px', fontWeight: 800, color: '#F59E0B' }}>{scanResult.watchlist.length}</div>
          </div>
          <div style={{ backgroundColor: '#1F2937', padding: '12px 16px', borderRadius: '8px', border: '1px solid #374151' }}>
            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>SCAN DURATION</div>
            <div style={{ fontSize: '18px', fontWeight: 800, color: '#D1D5DB' }}>{scanResult.scan_duration_seconds}s</div>
          </div>
        </div>
      )}

      {/* TOP 1 - 3 HIGH-CONVICTION SIGNALS SECTION */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
            🌟 High-Conviction Signals (Quality &gt; Quantity)
          </h3>
          <span style={{ fontSize: '12px', color: '#9CA3AF' }}>
            Strictly gated by Score &gt;= 80 &amp; R:R &gt;= 2.0
          </span>
        </div>

        {scanResult && scanResult.top_signals.length > 0 ? (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '16px',
            }}
          >
            {scanResult.top_signals.map((sig, idx) => (
              <SignalCard key={idx} signal={sig} onViewDetails={setSelectedSignal} />
            ))}
          </div>
        ) : (
          <div
            style={{
              padding: '30px',
              backgroundColor: '#1F2937',
              border: '1px dashed #4B5563',
              borderRadius: '12px',
              textAlign: 'center',
              color: '#9CA3AF',
            }}
          >
            {scanning
              ? 'Analyzing price action, multi-timeframe confluence, and sector momentum...'
              : 'No scans run yet or no setup met the strict 80+ conviction threshold. Click "Scan Indian Market" above.'}
          </div>
        )}
      </div>

      {/* ENHANCED WATCHLIST & SCREENED CANDIDATES TABLE WITH FUNDAMENTALS */}
      {scanResult && scanResult.watchlist.length > 0 && (
        <div
          style={{
            backgroundColor: '#1F2937',
            border: '1px solid #374151',
            borderRadius: '12px',
            padding: '18px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div>
              <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', margin: 0 }}>
                📋 Screened Watchlist Candidates &amp; Fundamental Snapshot
              </h3>
              <span style={{ fontSize: '12px', color: '#9CA3AF' }}>
                Click any symbol for complete Screener.in &amp; NSE delivery profile
              </span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                  <th style={{ padding: '10px' }}>SYMBOL</th>
                  <th style={{ padding: '10px' }}>SECTOR</th>
                  <th style={{ padding: '10px' }}>MKT CAP (₹ CR)</th>
                  <th style={{ padding: '10px' }}>P/E (IND P/E)</th>
                  <th style={{ padding: '10px' }}>ROCE / ROE</th>
                  <th style={{ padding: '10px' }}>DELIVERY %</th>
                  <th style={{ padding: '10px' }}>SETUP</th>
                  <th style={{ padding: '10px' }}>ENTRY</th>
                  <th style={{ padding: '10px' }}>STOP LOSS</th>
                  <th style={{ padding: '10px' }}>TARGET 1</th>
                  <th style={{ padding: '10px' }}>R:R</th>
                  <th style={{ padding: '10px' }}>LINKS</th>
                  <th style={{ padding: '10px' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {scanResult.watchlist.map((w, i) => {
                  const cleanSym = w.symbol.replace('.NS', '');
                  const info = batchInfoMap[cleanSym];
                  return (
                    <tr
                      key={i}
                      style={{
                        borderBottom: '1px solid #1F2937',
                        color: '#E5E7EB',
                        backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.1)',
                      }}
                    >
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
                          title="Open Stock Fundamentals Drawer"
                        >
                          {cleanSym} <Info size={12} />
                        </button>
                      </td>

                      <td style={{ padding: '10px', color: '#9CA3AF' }}>{w.sector}</td>

                      <td style={{ padding: '10px' }}>
                        {info ? (
                          <div>
                            <span style={{ fontWeight: 600 }}>₹{info.market_cap_cr.toLocaleString('en-IN')}</span>
                            <span style={{ fontSize: '10px', color: '#9CA3AF', marginLeft: '4px' }}>
                              ({info.market_cap_category.split(' ')[0]})
                            </span>
                          </div>
                        ) : (
                          '--'
                        )}
                      </td>

                      <td style={{ padding: '10px' }}>
                        {info ? (
                          <span>
                            <strong style={{ color: info.stock_pe <= info.industry_pe ? '#10B981' : '#F59E0B' }}>
                              {info.stock_pe > 0 ? `${info.stock_pe.toFixed(1)}x` : 'N/A'}
                            </strong>{' '}
                            <span style={{ color: '#9CA3AF', fontSize: '11px' }}>({info.industry_pe}x)</span>
                          </span>
                        ) : (
                          '--'
                        )}
                      </td>

                      <td style={{ padding: '10px' }}>
                        {info ? (
                          <span>
                            <span style={{ color: '#10B981', fontWeight: 600 }}>{info.roce_pct.toFixed(0)}%</span> /{' '}
                            <span style={{ color: '#60A5FA' }}>{info.roe_pct.toFixed(0)}%</span>
                          </span>
                        ) : (
                          '--'
                        )}
                      </td>

                      <td style={{ padding: '10px' }}>{getDeliveryBadge(info?.delivery_pct)}</td>

                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            padding: '2px 6px',
                            backgroundColor: '#374151',
                            borderRadius: '4px',
                            fontSize: '11px',
                          }}
                        >
                          {w.signal_type}
                        </span>
                      </td>

                      <td style={{ padding: '10px' }}>₹{w.risk_reward.entry_price.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#EF4444' }}>₹{w.risk_reward.stop_loss.toLocaleString()}</td>
                      <td style={{ padding: '10px', color: '#10B981' }}>₹{w.risk_reward.target_1.toLocaleString()}</td>
                      <td style={{ padding: '10px', fontWeight: 600 }}>{w.risk_reward.rr_ratio}x</td>

                      {/* Direct External Links */}
                      <td style={{ padding: '10px' }}>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <a
                            href={`https://www.nseindia.com/get-quotes/equity?symbol=${cleanSym}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ color: '#93C5FD', textDecoration: 'none', fontSize: '11px', fontWeight: 700 }}
                            title="NSE India"
                          >
                            NSE
                          </a>
                          <span style={{ color: '#4B5563' }}>|</span>
                          <a
                            href={`https://www.screener.in/company/${cleanSym}/consolidated/`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ color: '#34D399', textDecoration: 'none', fontSize: '11px', fontWeight: 700 }}
                            title="Screener.in"
                          >
                            SCR
                          </a>
                          <span style={{ color: '#4B5563' }}>|</span>
                          <a
                            href={`https://in.tradingview.com/chart/?symbol=NSE:${cleanSym}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ color: '#E5E7EB', textDecoration: 'none', fontSize: '11px', fontWeight: 700 }}
                            title="TradingView"
                          >
                            TV
                          </a>
                        </div>
                      </td>

                      <td style={{ padding: '10px' }}>
                        <button
                          onClick={() => setSelectedSignal(w)}
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
                          View Breakdown
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rationale & Score Breakdown Modal */}
      <SignalDetailModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />

      {/* Stock Fundamentals & Profile Slide-over Drawer */}
      <StockDetailDrawer symbol={drawerSymbol} onClose={() => setDrawerSymbol(null)} />
    </div>
  );
};
