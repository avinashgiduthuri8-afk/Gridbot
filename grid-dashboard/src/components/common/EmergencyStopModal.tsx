import React, { useState } from 'react';
import { X, ShieldAlert } from 'lucide-react';
import { api } from '../../services/api';

interface EmergencyStopModalProps {
  isOpen: boolean;
  currentState: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const EmergencyStopModal: React.FC<EmergencyStopModalProps> = ({
  isOpen,
  currentState,
  onClose,
  onSuccess,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const targetState = !currentState;

  const handleToggle = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.setEmergencyStop(targetState);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to toggle Emergency Stop');
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
          maxWidth: '460px',
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
            <ShieldAlert size={20} color={targetState ? 'var(--danger)' : 'var(--success)'} />
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>
              {targetState ? 'Activate Emergency Stop' : 'Clear Emergency Stop'}
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

        <div style={{ padding: '1.5rem' }}>
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

          <p style={{ fontSize: '0.9rem', color: 'var(--text-main)', margin: '0 0 1.25rem 0', lineHeight: 1.5 }}>
            {targetState ? (
              <>
                Activating Emergency Stop will <strong>IMMEDIATELY HALT</strong> all automated dip buys,
                new grid creation, and manual buy orders across all trading pairs.
              </>
            ) : (
              <>
                Clearing Emergency Stop will <strong>RE-ENABLE</strong> trading triggers and order placement.
                Please ensure market conditions and balances are verified.
              </>
            )}
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button className="action-btn" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button
              className="action-btn"
              onClick={handleToggle}
              style={{
                backgroundColor: targetState ? 'var(--danger)' : 'var(--success)',
                color: '#fff',
                fontWeight: 700,
              }}
              disabled={loading}
            >
              {loading
                ? 'Updating...'
                : targetState
                ? 'ACTIVATE EMERGENCY STOP'
                : 'CLEAR EMERGENCY STOP'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
