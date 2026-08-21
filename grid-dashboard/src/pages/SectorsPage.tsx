import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { SectorMatrixResponse, MarketRegimeResponse } from '../types/dashboard';
import { MarketRegimeBar } from '../components/common/MarketRegimeBar';
import { SectorHeatmap } from '../components/common/SectorHeatmap';

export const SectorsPage: React.FC = () => {
  const [matrix, setMatrix] = useState<SectorMatrixResponse | null>(null);
  const [regime, setRegime] = useState<MarketRegimeResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [m, r] = await Promise.all([api.getSectorMatrix(), api.getMarketRegime()]);
        setMatrix(m);
        setRegime(r);
      } catch (err) {
        console.error('Failed to load sector data', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <MarketRegimeBar regime={regime} />

      <div style={{ backgroundColor: '#1F2937', padding: '16px 20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
          NSE Sector Strength & Momentum Matrix
        </h2>
        <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
          Real-time tracking of 11 key industry sectors relative to NIFTY 50 benchmark
        </p>
      </div>

      <SectorHeatmap sectorMatrix={matrix} loading={loading} />

      {matrix && (
        <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '14px' }}>
            Detailed Sector Performance Breakdown
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                  <th style={{ padding: '10px' }}>RANK</th>
                  <th style={{ padding: '10px' }}>SECTOR</th>
                  <th style={{ padding: '10px' }}>INDEX SYMBOL</th>
                  <th style={{ padding: '10px' }}>1D RETURN</th>
                  <th style={{ padding: '10px' }}>5D RETURN</th>
                  <th style={{ padding: '10px' }}>20D RETURN</th>
                  <th style={{ padding: '10px' }}>ALPHA VS NIFTY</th>
                  <th style={{ padding: '10px' }}>STATUS</th>
                </tr>
              </thead>
              <tbody>
                {matrix.sectors.map((s, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #1F2937', color: '#E5E7EB' }}>
                    <td style={{ padding: '10px', fontWeight: 700, color: '#60A5FA' }}>#{s.momentum_rank}</td>
                    <td style={{ padding: '10px', fontWeight: 600 }}>{s.sector}</td>
                    <td style={{ padding: '10px', color: '#9CA3AF' }}>{s.index_symbol}</td>
                    <td style={{ padding: '10px', color: s.change_pct_1d >= 0 ? '#10B981' : '#EF4444' }}>
                      {s.change_pct_1d >= 0 ? '+' : ''}{s.change_pct_1d.toFixed(2)}%
                    </td>
                    <td style={{ padding: '10px', color: s.change_pct_5d >= 0 ? '#10B981' : '#EF4444' }}>
                      {s.change_pct_5d >= 0 ? '+' : ''}{s.change_pct_5d.toFixed(2)}%
                    </td>
                    <td style={{ padding: '10px', color: s.change_pct_20d >= 0 ? '#10B981' : '#EF4444' }}>
                      {s.change_pct_20d >= 0 ? '+' : ''}{s.change_pct_20d.toFixed(2)}%
                    </td>
                    <td style={{ padding: '10px', fontWeight: 700, color: s.relative_strength >= 0 ? '#10B981' : '#EF4444' }}>
                      {s.relative_strength >= 0 ? '+' : ''}{s.relative_strength.toFixed(2)}%
                    </td>
                    <td style={{ padding: '10px' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor:
                            s.status === 'LEADING'
                              ? '#064E3B'
                              : s.status === 'IMPROVING'
                              ? '#065F46'
                              : s.status === 'WEAKENING'
                              ? '#78350F'
                              : '#450A0A',
                          color:
                            s.status === 'LEADING'
                              ? '#34D399'
                              : s.status === 'IMPROVING'
                              ? '#10B981'
                              : s.status === 'WEAKENING'
                              ? '#FBBF24'
                              : '#F87171',
                        }}
                      >
                        {s.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
