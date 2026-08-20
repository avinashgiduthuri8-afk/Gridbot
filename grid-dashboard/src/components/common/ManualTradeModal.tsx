import React, { useState } from 'react';
import { X, ArrowDownRight, ArrowUpRight, ShieldAlert } from 'lucide-react';
import { api } from '../../services/api';
import { formatInr } from '../../utils/formatters';
import type { GridResponse } from '../../types/dashboard';

interface ManualTradeModalProps {
  grid: GridResponse | null;
  side: 'buy' | 'sell';
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ManualTradeModal: React.FC<ManualTradeModalProps> = ({
  grid,
  side,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [inrAmount, setInrAmount] = useState('6000');
  const [sellAll, setSellAll] = useState(false);
  const [isConfirmingReal, setIsConfirmingReal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !grid) return null;

  const isReal = grid.mode.toLowerCase() === 'real';
  const isBuy = side === 'buy';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isReal && !isConfirmingReal) {
      setIsConfirmingReal(true);
      return;
    }

    setLoading(true);
    try {
      if (isBuy) {
        await api.manualBuy(grid.grid_id, parseFloat(inrAmount));
      } else {
        await api.manualSell(grid.grid_id, sellAll ? null : parseFloat(inrAmount));
      }
      setIsConfirmingReal(false);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || `Failed to place manual ${side} order`);
    } finally {
      setLoading(false);
    }
  };

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
          maxWidth: '480px',
          backgroundColor: '#0d1322',
          border: '1px solid var(--border-color)',
          borderRadius: '16px',
          boxShadow: 'var(--shadow-glow)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {isBuy ? (
              <ArrowDownRight size={20} color="var(--success)" />
            ) : (
              <ArrowUpRight size={20} color="var(--accent-cyan)" />
            )}
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>
              Manual {isBuy ? 'BUY' : 'SELL'} — {grid.symbol}
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '1.5rem' }}>
          {error && (
            <div
              style={{
                padding: '0.8rem 1rem',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid var(--danger)',
                borderRadius: '8px',
                color: '#fca5a5',
                fontSize: '0.85rem',
                marginBottom: '1.25rem',
              }}
            >
              {error}
            </div>
          )}

          {isReal && isConfirmingReal ? (
            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.12)',
                border: '2px solid var(--danger)',
                borderRadius: '12px',
                padding: '1.25rem',
                marginBottom: '1.5rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.8rem' }}>
                <ShieldAlert size={22} color="var(--danger)" />
                <span style={{ fontWeight: 700, color: '#fff', fontSize: '1rem' }}>
                  REAL LIVE-ORDER CONFIRMATION
                </span>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#fca5a5', margin: '0 0 1rem 0' }}>
                You are about to execute a <strong>REAL LIVE {side.toUpperCase()} ORDER</strong> on CoinDCX.
              </p>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-main)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div>Symbol: <strong>{grid.symbol}</strong></div>
                <div>Side: <strong style={{ color: isBuy ? 'var(--success)' : 'var(--accent-cyan)' }}>{side.toUpperCase()}</strong></div>
                <div>Amount: <strong>{isBuy ? formatInr(parseFloat(inrAmount)) : (sellAll ? '100% (Entire Holding)' : formatInr(parseFloat(inrAmount)))}</strong></div>
                <div>Mode: <strong style={{ color: 'var(--danger)' }}>REAL</strong></div>
              </div>
            </div>
          ) : (
            <>
              <div style={{ marginBottom: '1.25rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                <div>Grid ID: <code style={{ color: 'var(--accent-cyan)' }}>{grid.grid_id}</code></div>
                <div>Mode: <strong style={{ color: isReal ? 'var(--danger)' : 'var(--accent-cyan)' }}>{grid.mode.toUpperCase()}</strong></div>
                {!isBuy && <div>Current Holding: <strong>{grid.total_quantity.toFixed(6)} {grid.symbol.replace('INR', '')}</strong> ({formatInr(grid.total_investment)})</div>}
              </div>

              {!isBuy && (
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: '#fff', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={sellAll}
                      onChange={(e) => setSellAll(e.target.checked)}
                    />
                    Sell entire remaining position (100%)
                  </label>
                </div>
              )}

              {(!sellAll || isBuy) && (
                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    INR Amount to {isBuy ? 'Buy' : 'Sell'}
                  </label>
                  <input
                    type="number"
                    value={inrAmount}
                    onChange={(e) => setInrAmount(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.5rem 0.75rem',
                      backgroundColor: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      color: '#fff',
                    }}
                    required
                  />
                </div>
              )}
            </>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button
              type="button"
              className="action-btn"
              onClick={() => {
                if (isConfirmingReal) {
                  setIsConfirmingReal(false);
                } else {
                  onClose();
                }
              }}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="action-btn"
              style={{
                backgroundColor: isReal ? 'var(--danger)' : isBuy ? 'var(--success)' : 'var(--accent-cyan)',
                color: isReal ? '#fff' : '#000',
                fontWeight: 700,
              }}
              disabled={loading}
            >
              {loading
                ? 'Placing Order...'
                : isReal && isConfirmingReal
                ? `Confirm & Place Real ${side.toUpperCase()}`
                : isReal
                ? `Proceed to Real ${side.toUpperCase()}`
                : `Execute Paper ${side.toUpperCase()}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
