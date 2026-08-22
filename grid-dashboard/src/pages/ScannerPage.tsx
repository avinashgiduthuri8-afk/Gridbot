import React, { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';
import type { ScanResponse, ScoredSignalResponse, StockInfoResponse } from '../types/dashboard';
import { MarketRegimeBar } from '../components/common/MarketRegimeBar';
import { SignalCard } from '../components/common/SignalCard';
import { SignalDetailModal } from '../components/common/SignalDetailModal';
import { StockDetailDrawer } from '../components/common/StockDetailDrawer';
import { Info, ExternalLink, Zap, Filter, Award } from 'lucide-react';

export const ScannerPage: React.FC = () => {
  const [universe, setUniverse] = useState<string>('NIFTY_100');
  const [maxSignals, setMaxSignals] = useState<number>(3);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [batchInfoMap, setBatchInfoMap] = useState<Record<string, StockInfoResponse>>({});
  const [scanning, setScanning] = useState<boolean>(false);
  const [selectedSignal, setSelectedSignal] = useState<ScoredSignalResponse | null>(null);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filters state
  const [selectedSetupFilter, setSelectedSetupFilter] = useState<string>('ALL');
  const [selectedCapFilter, setSelectedCapFilter] = useState<string>('ALL');
  const [topOnlyFilter, setTopOnlyFilter] = useState<boolean>(false);

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

  // Combine signals and apply filters
  const displayedSignals = useMemo(() => {
    if (!scanResult) return [];
    let list = topOnlyFilter ? [...scanResult.top_signals] : [...scanResult.top_signals, ...scanResult.watchlist];

    // Deduplicate by symbol
    const seen = new Set<string>();
    list = list.filter((s) => {
      if (seen.has(s.symbol)) return false;
      seen.add(s.symbol);
      return true;
    });

    // Setup filter
    if (selectedSetupFilter !== 'ALL') {
      list = list.filter((s) => {
        const stype = String(s.signal_type).toUpperCase();
        if (selectedSetupFilter === 'VCP') return stype.includes('VCP');
        if (selectedSetupFilter === 'POCKET') return stype.includes('POCKET');
        if (selectedSetupFilter === 'NR7') return stype.includes('NR7');
        if (selectedSetupFilter === 'DELIVERY') return stype.includes('DELIVERY');
        return true;
      });
    }

    // Market cap filter
    if (selectedCapFilter !== 'ALL') {
      list = list.filter((s) => {
        const cleanSym = s.symbol.replace('.NS', '').replace('.BO', '');
        const info = batchInfoMap[cleanSym];
        if (!info) return true;
        const cat = (info.market_cap_category || '').toLowerCase();
        if (selectedCapFilter === 'LARGE') return cat.includes('large');
        if (selectedCapFilter === 'MID') return cat.includes('mid');
        if (selectedCapFilter === 'SMALL') return cat.includes('small');
        return true;
      });
    }

    return list;
  }, [scanResult, topOnlyFilter, selectedSetupFilter, selectedCapFilter, batchInfoMap]);

  const getDeliveryBadge = (pct?: number) => {
    if (pct === undefined || pct === null) return <span style={{ color: '#6B7280' }}>--</span>;
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
          padding: '2px 7px',
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
          padding: '18px 22px',
          borderRadius: '12px',
          border: '1px solid #374151',
          gap: '14px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Zap size={22} color="#10B981" /> Institutional Indian Stock Scanner
          </h2>
          <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
            12-Stage multi-timeframe confluence engine (1D Base Structure + 1H Setup + 15M Trigger)
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {/* Universe Selector */}
          <div>
            <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '2px', fontWeight: 700 }}>
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
                padding: '7px 12px',
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
            <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '2px', fontWeight: 700 }}>
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
                padding: '7px 12px',
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
                padding: '8px 22px',
                fontSize: '13px',
                fontWeight: 700,
                cursor: scanning ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: '0 4px 6px -1px rgba(16, 185, 129, 0.4)',
              }}
            >
              {scanning ? '⏳ Scanning Market...' : '⚡ Scan Indian Market'}
            </button>
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: '#1F2937',
          padding: '12px 20px',
          borderRadius: '10px',
          border: '1px solid #374151',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', color: '#9CA3AF', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Filter size={14} /> SETUPS:
          </span>
          {[
            { id: 'ALL', label: 'All Setups' },
            { id: 'VCP', label: 'Minervini VCP' },
            { id: 'POCKET', label: 'Pocket Pivot' },
            { id: 'NR7', label: 'NR7 Squeeze' },
            { id: 'DELIVERY', label: 'High Delivery' },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedSetupFilter(f.id)}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                border: 'none',
                backgroundColor: selectedSetupFilter === f.id ? '#2563EB' : '#111827',
                color: selectedSetupFilter === f.id ? '#FFFFFF' : '#9CA3AF',
                cursor: 'pointer',
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <select
            value={selectedCapFilter}
            onChange={(e) => setSelectedCapFilter(e.target.value)}
            style={{
              backgroundColor: '#111827',
              color: '#F9FAFB',
              border: '1px solid #4B5563',
              borderRadius: '6px',
              padding: '4px 10px',
              fontSize: '12px',
            }}
          >
            <option value="ALL">All Market Caps</option>
            <option value="LARGE">Large Cap (&gt;₹20k Cr)</option>
            <option value="MID">Mid Cap</option>
            <option value="SMALL">Small Cap</option>
          </select>

          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '12px', color: '#E5E7EB' }}>
            <input
              type="checkbox"
              checked={topOnlyFilter}
              onChange={(e) => setTopOnlyFilter(e.target.checked)}
              style={{ width: '14px', height: '14px', accentColor: '#10B981' }}
            />
            <span style={{ fontWeight: 600 }}>Top 1–3 Picks Only</span>
          </label>
        </div>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', backgroundColor: '#450A0A', border: '1px solid #7F1D1D', borderRadius: '8px', color: '#FCA5A5', fontSize: '13px' }}>
          <strong>Scanner Notice:</strong> {error}
        </div>
      )}

      {/* Top Flash Cards Grid (Top 3 Signals) */}
      {scanResult && scanResult.top_signals.length > 0 && (
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: 800, color: '#F9FAFB', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Award size={18} color="#F59E0B" /> Top High-Conviction Institutional Opportunities
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
            {scanResult.top_signals.map((sig, idx) => (
              <SignalCard key={idx} signal={sig} onViewDetails={setSelectedSignal} />
            ))}
          </div>
        </div>
      )}

      {/* Enriched Live Scanner DataTable */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 800, color: '#F9FAFB', marginBottom: '14px' }}>
          Live Stock Setup &amp; Fundamental Matrix ({displayedSignals.length} candidates)
        </h3>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                <th style={{ padding: '10px' }}>SYMBOL &amp; SECTOR</th>
                <th style={{ padding: '10px' }}>SETUP</th>
                <th style={{ padding: '10px' }}>IEI SCORE</th>
                <th style={{ padding: '10px' }}>CMP (₹)</th>
                <th style={{ padding: '10px' }}>ENTRY / SL</th>
                <th style={{ padding: '10px' }}>TARGET 1 / 2</th>
                <th style={{ padding: '10px' }}>DELIVERY %</th>
                <th style={{ padding: '10px' }}>ROCE %</th>
                <th style={{ padding: '10px' }}>P/E vs IND</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>RESEARCH &amp; LINKS</th>
              </tr>
            </thead>
            <tbody>
              {displayedSignals.length > 0 ? (
                displayedSignals.map((sig, idx) => {
                  const cleanSym = sig.symbol.replace('.NS', '').replace('.BO', '');
                  const info = batchInfoMap[cleanSym];
                  const iei = sig.iei_score || sig.total_score;

                  return (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: '1px solid #1F2937',
                        color: '#E5E7EB',
                        cursor: 'pointer',
                        transition: 'background-color 0.15s',
                      }}
                      onClick={() => setDrawerSymbol(sig.symbol)}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#111827')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <td style={{ padding: '10px' }}>
                        <div style={{ fontWeight: 800, color: '#60A5FA', fontSize: '13px' }}>{sig.symbol}</div>
                        <span style={{ fontSize: '10px', color: '#9CA3AF' }}>{sig.sector || 'Equities'}</span>
                      </td>

                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            padding: '2px 7px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            fontWeight: 700,
                            backgroundColor: '#1E3A8A',
                            color: '#93C5FD',
                          }}
                        >
                          {String(sig.signal_type).replace('_', ' ')}
                        </span>
                      </td>

                      <td style={{ padding: '10px' }}>
                        <strong style={{ color: iei >= 80 ? '#10B981' : '#F59E0B', fontSize: '13px' }}>
                          {iei.toFixed(1)}
                        </strong>
                      </td>

                      <td style={{ padding: '10px', fontWeight: 700, fontFamily: 'monospace' }}>
                        ₹{sig.risk_reward.entry_price.toFixed(2)}
                      </td>

                      <td style={{ padding: '10px', fontFamily: 'monospace' }}>
                        <div style={{ color: '#10B981', fontWeight: 600 }}>E: ₹{sig.risk_reward.entry_price.toFixed(2)}</div>
                        <div style={{ color: '#EF4444', fontSize: '11px' }}>SL: ₹{sig.risk_reward.stop_loss.toFixed(2)}</div>
                      </td>

                      <td style={{ padding: '10px', fontFamily: 'monospace' }}>
                        <div style={{ color: '#34D399', fontWeight: 600 }}>T1: ₹{sig.risk_reward.target_1.toFixed(2)}</div>
                        <div style={{ color: '#60A5FA', fontSize: '11px' }}>T2: ₹{sig.risk_reward.target_2.toFixed(2)}</div>
                      </td>

                      <td style={{ padding: '10px' }}>
                        {getDeliveryBadge(info?.delivery_pct)}
                      </td>

                      <td style={{ padding: '10px', fontFamily: 'monospace' }}>
                        {info?.roce_pct ? `${info.roce_pct.toFixed(1)}%` : '--'}
                      </td>

                      <td style={{ padding: '10px', fontSize: '11px', fontFamily: 'monospace' }}>
                        {info?.stock_pe ? `${info.stock_pe.toFixed(1)}x / ${info.industry_pe?.toFixed(1) || '--'}x` : '--'}
                      </td>

                      <td style={{ padding: '10px', textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                        <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
                          <button
                            onClick={() => setDrawerSymbol(sig.symbol)}
                            style={{
                              backgroundColor: '#374151',
                              border: 'none',
                              borderRadius: '4px',
                              padding: '4px 8px',
                              color: '#F9FAFB',
                              fontSize: '11px',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                            title="View Fundamentals & Ratios"
                          >
                            <Info size={12} /> Details
                          </button>

                          <a
                            href={`https://www.screener.in/company/${cleanSym}/consolidated/`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              backgroundColor: '#1E3A8A',
                              color: '#93C5FD',
                              padding: '4px 6px',
                              borderRadius: '4px',
                              textDecoration: 'none',
                              fontSize: '11px',
                              display: 'flex',
                              alignItems: 'center',
                            }}
                            title="View on Screener.in"
                          >
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: '30px', color: '#9CA3AF' }}>
                    {scanning ? 'Analyzing Indian stock universe...' : 'No setups matching the selected criteria.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modals & Detail Drawers */}
      <SignalDetailModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
      <StockDetailDrawer symbol={drawerSymbol} onClose={() => setDrawerSymbol(null)} />
    </div>
  );
};
