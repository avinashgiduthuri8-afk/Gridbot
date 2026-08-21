import React from 'react';
import type { SectorMatrixResponse } from '../../types/dashboard';

interface SectorHeatmapProps {
  sectorMatrix: SectorMatrixResponse | null;
  loading?: boolean;
}

export const SectorHeatmap: React.FC<SectorHeatmapProps> = ({ sectorMatrix, loading = false }) => {
  if (loading || !sectorMatrix) {
    return (
      <div style={{ padding: '20px', textAlign: 'center', color: '#9CA3AF', backgroundColor: '#1F2937', borderRadius: '10px' }}>
        Loading Sector Strength Matrix...
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'LEADING':
        return { label: '🔥 LEADING', bg: '#064E3B', color: '#34D399' };
      case 'IMPROVING':
        return { label: '📈 IMPROVING', bg: '#065F46', color: '#10B981' };
      case 'WEAKENING':
        return { label: '⚠️ WEAKENING', bg: '#78350F', color: '#FBBF24' };
      case 'LAGGING':
        return { label: '❄️ LAGGING', bg: '#450A0A', color: '#F87171' };
      default:
        return { label: status, bg: '#1F2937', color: '#9CA3AF' };
    }
  };

  return (
    <div
      style={{
        backgroundColor: '#1F2937',
        border: '1px solid #374151',
        borderRadius: '12px',
        padding: '18px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB' }}>
          NSE Sector Momentum & Relative Strength Matrix
        </h3>
        <div style={{ fontSize: '12px', color: '#9CA3AF' }}>
          Leading: <strong>{sectorMatrix.leading_sectors.join(', ') || 'None'}</strong>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: '12px',
        }}
      >
        {sectorMatrix.sectors.map((s, idx) => {
          const badge = getStatusBadge(s.status);
          const isPositive = s.change_pct_1d >= 0;
          return (
            <div
              key={idx}
              style={{
                backgroundColor: '#111827',
                border: '1px solid #374151',
                borderRadius: '8px',
                padding: '12px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <span style={{ fontWeight: 700, fontSize: '14px', color: '#F9FAFB' }}>{s.sector}</span>
                <span
                  style={{
                    fontSize: '10px',
                    fontWeight: 700,
                    padding: '2px 6px',
                    backgroundColor: badge.bg,
                    color: badge.color,
                    borderRadius: '4px',
                  }}
                >
                  {badge.label}
                </span>
              </div>

              <div style={{ margin: '8px 0', fontSize: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9CA3AF' }}>
                  <span>1D Return:</span>
                  <strong style={{ color: isPositive ? '#10B981' : '#EF4444' }}>
                    {isPositive ? '+' : ''}
                    {s.change_pct_1d.toFixed(2)}%
                  </strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9CA3AF', marginTop: '2px' }}>
                  <span>Alpha vs Nifty:</span>
                  <strong style={{ color: s.relative_strength >= 0 ? '#60A5FA' : '#F87171' }}>
                    {s.relative_strength >= 0 ? '+' : ''}
                    {s.relative_strength.toFixed(2)}%
                  </strong>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: '#6B7280', textAlign: 'right' }}>
                Rank #{s.momentum_rank}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
