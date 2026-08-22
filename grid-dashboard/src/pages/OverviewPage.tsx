import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { MarketRegimeBar } from '../components/common/MarketRegimeBar';
import { SignalCard } from '../components/common/SignalCard';
import { SignalDetailModal } from '../components/common/SignalDetailModal';
import { SectorHeatmap } from '../components/common/SectorHeatmap';
import type { NavigationTab, ScanResponse, SectorMatrixResponse, ScoredSignalResponse } from '../types/dashboard';
import type { DashboardData } from '../hooks/useDashboardData';
import { Search, Compass, PieChart, Target, PlaySquare } from 'lucide-react';

interface OverviewPageProps {
  data: DashboardData;
  loading: boolean;
  onNavigate: (tab: NavigationTab, prefillSymbol?: string) => void;
  onRefresh?: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  data: _data,
  loading: _loading,
  onNavigate,
  onRefresh: _onRefresh,
}) => {
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [sectorMatrix, setSectorMatrix] = useState<SectorMatrixResponse | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<ScoredSignalResponse | null>(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    const fetchMarketState = async () => {
      try {
        const [scanRes, secRes] = await Promise.all([
          api.getLatestScan(),
          api.getSectorMatrix(),
        ]);
        if (scanRes && scanRes.top_signals) setScanResult(scanRes);
        if (secRes) setSectorMatrix(secRes);
      } catch {
        // Fallback
      }
    };
    fetchMarketState();
  }, []);

  const handleQuickScan = async () => {
    setScanning(true);
    try {
      const res = await api.triggerScan('NIFTY_100', 3);
      setScanResult(res);
    } catch (err) {
      console.error('Scan error:', err);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 1. Market Regime & IST Session Banner */}
      <MarketRegimeBar regime={scanResult?.regime} session={scanResult?.session_info} />

      {/* 2. Executive Quick Action Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
        <div
          onClick={() => onNavigate('scanner')}
          style={{
            backgroundColor: '#1F2937',
            padding: '16px',
            borderRadius: '10px',
            border: '1px solid #374151',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#10B981')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#374151')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#10B981', marginBottom: '8px' }}>
            <Search size={20} />
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#F9FAFB' }}>Stock Scanner</span>
          </div>
          <p style={{ fontSize: '12px', color: '#9CA3AF', margin: 0 }}>
            Run multi-timeframe scans across NIFTY 50/100/200/500
          </p>
        </div>

        <div
          onClick={() => onNavigate('stocks')}
          style={{
            backgroundColor: '#1F2937',
            padding: '16px',
            borderRadius: '10px',
            border: '1px solid #374151',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#3B82F6')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#374151')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#3B82F6', marginBottom: '8px' }}>
            <Compass size={20} />
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#F9FAFB' }}>Stock Explorer</span>
          </div>
          <p style={{ fontSize: '12px', color: '#9CA3AF', margin: 0 }}>
            Deep fundamentals, NSE delivery &amp; technical health
          </p>
        </div>

        <div
          onClick={() => onNavigate('sectors')}
          style={{
            backgroundColor: '#1F2937',
            padding: '16px',
            borderRadius: '10px',
            border: '1px solid #374151',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#60A5FA')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#374151')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#60A5FA', marginBottom: '8px' }}>
            <PieChart size={20} />
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#F9FAFB' }}>Sector Momentum</span>
          </div>
          <p style={{ fontSize: '12px', color: '#9CA3AF', margin: 0 }}>
            Track 11 NSE sectors and alpha leaders vs NIFTY
          </p>
        </div>

        <div
          onClick={() => onNavigate('signals')}
          style={{
            backgroundColor: '#1F2937',
            padding: '16px',
            borderRadius: '10px',
            border: '1px solid #374151',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#F59E0B')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#374151')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#F59E0B', marginBottom: '8px' }}>
            <Target size={20} />
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#F9FAFB' }}>Signals & Excursions</span>
          </div>
          <p style={{ fontSize: '12px', color: '#9CA3AF', margin: 0 }}>
            MFE / MAE tracking and historical win rate analytics
          </p>
        </div>

        <div
          onClick={() => onNavigate('backtest')}
          style={{
            backgroundColor: '#1F2937',
            padding: '16px',
            borderRadius: '10px',
            border: '1px solid #374151',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#EC4899')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#374151')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#EC4899', marginBottom: '8px' }}>
            <PlaySquare size={20} />
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#F9FAFB' }}>Backtest Simulator</span>
          </div>
          <p style={{ fontSize: '12px', color: '#9CA3AF', margin: 0 }}>
            Simulate forward signals across historical market regimes
          </p>
        </div>
      </div>

      {/* 3. Top High-Conviction Signals Carousel */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
              🌟 High-Conviction Setups (Top Signals)
            </h3>
            <span style={{ fontSize: '12px', color: '#9CA3AF' }}>
              Filtered for 1–2 institutional quality setups (Score &gt;= 80, R:R &gt;= 2.0)
            </span>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={handleQuickScan}
              disabled={scanning}
              style={{
                padding: '8px 16px',
                backgroundColor: scanning ? '#4B5563' : '#10B981',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                fontWeight: 700,
                fontSize: '13px',
                cursor: scanning ? 'not-allowed' : 'pointer',
              }}
            >
              {scanning ? '⏳ Scanning...' : '⚡ Quick Scan NIFTY 100'}
            </button>
            <button
              onClick={() => onNavigate('scanner')}
              style={{
                padding: '8px 14px',
                backgroundColor: '#374151',
                color: '#E5E7EB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              Open Full Scanner →
            </button>
          </div>
        </div>

        {scanResult && scanResult.top_signals.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
            {scanResult.top_signals.map((sig, idx) => (
              <SignalCard key={idx} signal={sig} onViewDetails={setSelectedSignal} />
            ))}
          </div>
        ) : (
          <div style={{ padding: '30px', textAlign: 'center', color: '#9CA3AF', backgroundColor: '#111827', borderRadius: '8px' }}>
            {scanning
              ? 'Analyzing Indian equities across 1D, 1H, and 15M timeframes...'
              : 'No signals cached yet. Click "Quick Scan NIFTY 100" to run the 12-stage screening engine.'}
          </div>
        )}
      </div>

      {/* 4. Sector Strength Matrix Snapshot */}
      <SectorHeatmap sectorMatrix={sectorMatrix} />

      {/* Modal View */}
      <SignalDetailModal signal={selectedSignal} onClose={() => setSelectedSignal(null)} />
    </div>
  );
};
