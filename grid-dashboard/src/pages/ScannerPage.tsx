import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { ScanResponse, ScoredSignalResponse } from '../types/dashboard';
import { MarketRegimeBar } from '../components/common/MarketRegimeBar';
import { SignalCard } from '../components/common/SignalCard';
import { SignalDetailModal } from '../components/common/SignalDetailModal';

export const ScannerPage: React.FC = () => {
  const [universe, setUniverse] = useState<string>('NIFTY_100');
  const [maxSignals, setMaxSignals] = useState<number>(3);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [scanning, setScanning] = useState<boolean>(false);
  const [selectedSignal, setSelectedSignal] = useState<ScoredSignalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load initial cached scan on mount
  useEffect(() => {
    const fetchInitialScan = async () => {
      try {
        const res = await api.getLatestScan();
        if (res && res.top_signals) {
          setScanResult(res);
        }
      } catch {
        // Silent fallback
      }
    };
    fetchInitialScan();
  }, []);

  const handleRunScan = async () => {
    setScanning(true);
    setError(null);
    try {
      const res = await api.triggerScan(universe, maxSignals);
      setScanResult(res);
    } catch (err: any) {
      setError(err.message || 'Scan execution failed');
    } finally {
      setScanning(false);
    }
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
              <option value={3}>Top 3 Signals</option>
              <option value={5}>Top 5 Signals</option>
            </select>
          </div>

          {/* Scan Action Button */}
          <button
            onClick={handleRunScan}
            disabled={scanning}
            style={{
              padding: '10px 22px',
              backgroundColor: scanning ? '#4B5563' : '#10B981',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '14px',
              cursor: scanning ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 14px rgba(16, 185, 129, 0.4)',
              transition: 'all 0.2s ease',
              marginTop: '14px',
            }}
          >
            {scanning ? '⏳ Scanning Market...' : '⚡ Scan Indian Market'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', backgroundColor: '#7F1D1D', color: '#FCA5A5', borderRadius: '8px' }}>
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

      {/* WATCHLIST & SCREENED CANDIDATES TABLE */}
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
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', margin: 0 }}>
              📋 Screened Watchlist Candidates
            </h3>
            <span style={{ fontSize: '12px', color: '#9CA3AF' }}>
              Showing setups scoring 60 - 79 pts
            </span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                  <th style={{ padding: '10px' }}>SYMBOL</th>
                  <th style={{ padding: '10px' }}>SECTOR</th>
                  <th style={{ padding: '10px' }}>SETUP</th>
                  <th style={{ padding: '10px' }}>SCORE</th>
                  <th style={{ padding: '10px' }}>ENTRY</th>
                  <th style={{ padding: '10px' }}>STOP LOSS</th>
                  <th style={{ padding: '10px' }}>TARGET 1</th>
                  <th style={{ padding: '10px' }}>R:R</th>
                  <th style={{ padding: '10px' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {scanResult.watchlist.map((w, i) => (
                  <tr
                    key={i}
                    style={{
                      borderBottom: '1px solid #1F2937',
                      color: '#E5E7EB',
                      backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.1)',
                    }}
                  >
                    <td style={{ padding: '10px', fontWeight: 700 }}>{w.symbol.replace('.NS', '')}</td>
                    <td style={{ padding: '10px', color: '#9CA3AF' }}>{w.sector}</td>
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
                    <td style={{ padding: '10px', fontWeight: 700, color: '#60A5FA' }}>
                      {w.total_score}
                    </td>
                    <td style={{ padding: '10px' }}>₹{w.risk_reward.entry_price.toLocaleString()}</td>
                    <td style={{ padding: '10px', color: '#EF4444' }}>₹{w.risk_reward.stop_loss.toLocaleString()}</td>
                    <td style={{ padding: '10px', color: '#10B981' }}>₹{w.risk_reward.target_1.toLocaleString()}</td>
                    <td style={{ padding: '10px', fontWeight: 600 }}>{w.risk_reward.rr_ratio}x</td>
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
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rationale & Score Breakdown Modal */}
      <SignalDetailModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
    </div>
  );
};
