import React, { useState } from 'react';
import { X, Play, ShieldAlert } from 'lucide-react';
import { api } from '../../services/api';
import { formatInr } from '../../utils/formatters';
import type { CreateGridRequest } from '../../types/dashboard';

interface CreateGridModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const CreateGridModal: React.FC<CreateGridModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [symbol, setSymbol] = useState('BTCINR');
  const [entryPrice, setEntryPrice] = useState('0');
  const [baseInvestment, setBaseInvestment] = useState('6000');
  const [dipBuyAmount, setDipBuyAmount] = useState('6000');
  const [dipPercentage, setDipPercentage] = useState('2.0');
  const [profitSellAmount, setProfitSellAmount] = useState('6000');
  const [profitPercentage, setProfitPercentage] = useState('3.0');
  const [maxLevels, setMaxLevels] = useState('5');
  const [stopLossPercentage, setStopLossPercentage] = useState('10.0');
  const [mode, setMode] = useState<'paper' | 'real'>('paper');

  const [isConfirmingReal, setIsConfirmingReal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const baseInv = parseFloat(baseInvestment) || 0;
  const dipAmt = parseFloat(dipBuyAmount) || 0;
  const levels = parseInt(maxLevels, 10) || 1;
  const totalCommitment = baseInv + dipAmt * (levels - 1);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (mode === 'real' && !isConfirmingReal) {
      setIsConfirmingReal(true);
      return;
    }

    setLoading(true);
    try {
      const payload: CreateGridRequest = {
        symbol: symbol.trim().toUpperCase(),
        entry_price: parseFloat(entryPrice) || 0,
        base_investment: baseInv,
        dip_buy_amount: dipAmt,
        dip_percentage: parseFloat(dipPercentage) || 0,
        profit_sell_amount: parseFloat(profitSellAmount) || 0,
        profit_percentage: parseFloat(profitPercentage) || 0,
        max_levels: levels,
        stop_loss_percentage: parseFloat(stopLossPercentage) || 0,
        mode,
      };

      await api.createGrid(payload);
      setIsConfirmingReal(false);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to create grid');
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
          maxWidth: '560px',
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
            <Play size={18} color="var(--accent-cyan)" />
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>
              Create New DCA Grid
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
        <form onSubmit={handleSubmit} style={{ padding: '1.5rem', overflowY: 'auto' }}>
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

          {isConfirmingReal ? (
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
                You are about to start a grid in <strong>REAL LIVE TRADING MODE</strong>. Real funds on CoinDCX will be deployed.
              </p>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-main)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div>Symbol: <strong>{symbol}</strong></div>
                <div>Mode: <strong style={{ color: 'var(--danger)' }}>REAL</strong></div>
                <div>Base Investment: <strong>{formatInr(baseInv)}</strong></div>
                <div>Max Ladder Commitment: <strong>{formatInr(totalCommitment)}</strong></div>
              </div>
            </div>
          ) : (
            <>
              {/* Mode Selector */}
              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>
                  Trading Mode
                </label>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <label
                    style={{
                      flex: 1,
                      padding: '0.6rem',
                      borderRadius: '8px',
                      border: mode === 'paper' ? '1px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                      backgroundColor: mode === 'paper' ? 'rgba(6, 182, 212, 0.1)' : 'transparent',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.85rem',
                      color: mode === 'paper' ? '#fff' : 'var(--text-muted)',
                    }}
                  >
                    <input
                      type="radio"
                      name="mode"
                      value="paper"
                      checked={mode === 'paper'}
                      onChange={() => setMode('paper')}
                    />
                    PAPER (Simulation)
                  </label>
                  <label
                    style={{
                      flex: 1,
                      padding: '0.6rem',
                      borderRadius: '8px',
                      border: mode === 'real' ? '1px solid var(--danger)' : '1px solid var(--border-color)',
                      backgroundColor: mode === 'real' ? 'rgba(239, 68, 68, 0.1)' : 'transparent',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.85rem',
                      color: mode === 'real' ? '#fff' : 'var(--text-muted)',
                    }}
                  >
                    <input
                      type="radio"
                      name="mode"
                      value="real"
                      checked={mode === 'real'}
                      onChange={() => setMode('real')}
                    />
                    REAL (CoinDCX Live)
                  </label>
                </div>
              </div>

              {/* Grid Inputs */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Symbol / Pair
                  </label>
                  <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
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
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Entry Price (0 for Market)
                  </label>
                  <input
                    type="number"
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.5rem 0.75rem',
                      backgroundColor: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      color: '#fff',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Base Investment (INR)
                  </label>
                  <input
                    type="number"
                    value={baseInvestment}
                    onChange={(e) => setBaseInvestment(e.target.value)}
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
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Dip Buy Amount (INR)
                  </label>
                  <input
                    type="number"
                    value={dipBuyAmount}
                    onChange={(e) => setDipBuyAmount(e.target.value)}
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
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Dip Percentage (%)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={dipPercentage}
                    onChange={(e) => setDipPercentage(e.target.value)}
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
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Profit Sell Amount (INR)
                  </label>
                  <input
                    type="number"
                    value={profitSellAmount}
                    onChange={(e) => setProfitSellAmount(e.target.value)}
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
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Profit Percentage (%)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={profitPercentage}
                    onChange={(e) => setProfitPercentage(e.target.value)}
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
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Max DCA Levels
                  </label>
                  <input
                    type="number"
                    value={maxLevels}
                    onChange={(e) => setMaxLevels(e.target.value)}
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
              </div>

              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                  Stop Loss Percentage (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={stopLossPercentage}
                  onChange={(e) => setStopLossPercentage(e.target.value)}
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

              {/* Total Commitment Summary */}
              <div
                style={{
                  padding: '0.8rem 1rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: '1.25rem',
                  fontSize: '0.85rem',
                }}
              >
                <span style={{ color: 'var(--text-muted)' }}>Total Ladder Commitment:</span>
                <span style={{ fontWeight: 700, color: 'var(--accent-cyan)' }}>
                  {formatInr(totalCommitment)}
                </span>
              </div>
            </>
          )}

          {/* Action Buttons */}
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
                backgroundColor: mode === 'real' ? 'var(--danger)' : 'var(--accent-cyan)',
                color: mode === 'real' ? '#fff' : '#000',
                fontWeight: 700,
              }}
              disabled={loading}
            >
              {loading
                ? 'Submitting...'
                : isConfirmingReal
                ? 'Confirm & Place REAL Order'
                : mode === 'real'
                ? 'Proceed to REAL Confirmation'
                : 'Start PAPER Grid'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
