import React, { useEffect } from 'react';
import type { GridResponse, StatusType } from '../../types/dashboard';
import { StatusBadge } from './StatusBadge';
import { formatInr, formatDate } from '../../utils/formatters';
import { X, Lock, Activity, ShieldAlert, Sliders } from 'lucide-react';

interface GridDetailModalProps {
  grid: GridResponse | null;
  onClose: () => void;
}

export const GridDetailModal: React.FC<GridDetailModalProps> = ({
  grid,
  onClose,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (grid) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [grid, onClose]);

  if (!grid) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        backgroundColor: 'rgba(9, 13, 22, 0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '680px',
          backgroundColor: '#0d1322',
          border: '1px solid var(--border-color)',
          borderRadius: '16px',
          boxShadow: 'var(--shadow-glow)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '90vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(18, 26, 44, 0.8)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fff' }}>
              {grid.symbol}
            </h2>
            <StatusBadge status={grid.status.toLowerCase() as StatusType} />
            <StatusBadge
              status={grid.mode.toLowerCase() as StatusType}
              label={grid.mode.toUpperCase()}
              showDot={false}
            />
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0.25rem',
              borderRadius: '6px',
            }}
            title="Close (Esc)"
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Read-Only Notice */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              background: 'rgba(255, 255, 255, 0.03)',
              padding: '0.5rem 0.85rem',
              borderRadius: '6px',
              border: '1px solid rgba(255, 255, 255, 0.06)',
            }}
          >
            <Lock size={14} color="var(--accent-cyan)" />
            <span>Read-Only Grid Inspection - No backend mutation controls</span>
          </div>

          {/* Section 1: Core Performance */}
          <div>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Activity size={14} color="var(--primary)" />
              <span>PERFORMANCE & POSITION SUMMARY</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Realized Profit</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: grid.realized_profit >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                  {formatInr(grid.realized_profit)}
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Invested Capital</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>
                  {formatInr(grid.total_investment)}
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Current Grid Level</div>
                <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                  Level {grid.current_level} of {grid.max_levels}
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Completed Cycles</div>
                <div style={{ fontSize: '1rem', fontWeight: 600, color: '#fff' }}>
                  {grid.completed_cycles} Cycles
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Trigger & Price Targets */}
          <div>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Sliders size={14} color="var(--accent-cyan)" />
              <span>PRICE TRIGGERS & LEVELS</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Entry Price</div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff' }}>{formatInr(grid.entry_price)}</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Next Buy Trigger</div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--success)' }}>{formatInr(grid.next_buy_price)}</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Next Sell Trigger</div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>{formatInr(grid.next_sell_price)}</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Avg Entry Price</div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff' }}>{formatInr(grid.average_entry_price)}</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Last Buy Price</div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff' }}>{formatInr(grid.last_buy_price)}</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Total Quantity</div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff', fontFamily: 'monospace' }}>
                  {grid.total_quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                </div>
              </div>
            </div>
          </div>

          {/* Section 3: Risk & Trailing Parameters */}
          <div>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <ShieldAlert size={14} color="var(--warning)" />
              <span>PARAMETERS & TIMESTAMPS</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.8rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Dip Buy Step</span>
                <span>{grid.dip_percentage}% ({formatInr(grid.dip_buy_amount)})</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Profit Target</span>
                <span>{grid.profit_percentage}% ({formatInr(grid.profit_sell_amount)})</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Stop Loss Threshold</span>
                <span>{grid.stop_loss_percentage}%</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Trailing Take-Profit</span>
                <span>{grid.trailing_enabled ? `Enabled (${grid.trailing_percentage ?? 0}%)` : 'Disabled'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', gridColumn: 'span 2' }}>
                <span style={{ color: 'var(--text-muted)' }}>Grid Created At</span>
                <span>{formatDate(grid.created_at)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'flex-end',
            background: 'rgba(18, 26, 44, 0.8)',
          }}
        >
          <button className="action-btn" onClick={onClose}>
            Close Inspection
          </button>
        </div>
      </div>
    </div>
  );
};
