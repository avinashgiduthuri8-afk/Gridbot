import React from 'react';

interface ProgressBarProps {
  value: number; // Percentage 0 - 100
  color?: string;
  height?: number;
  showLabel?: boolean;
  className?: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  color = 'var(--primary)',
  height = 8,
  showLabel = false,
  className = '',
}) => {
  const clampedValue = Math.min(100, Math.max(0, isNaN(value) ? 0 : value));

  return (
    <div className={`progress-bar-container ${className}`} style={{ width: '100%' }}>
      {showLabel && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '0.75rem',
            color: 'var(--text-muted)',
            marginBottom: '0.25rem',
          }}
        >
          <span>Utilization</span>
          <span>{clampedValue.toFixed(1)}%</span>
        </div>
      )}
      <div
        style={{
          width: '100%',
          height: `${height}px`,
          backgroundColor: 'rgba(255, 255, 255, 0.08)',
          borderRadius: `${height / 2}px`,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${clampedValue}%`,
            height: '100%',
            backgroundColor: color,
            borderRadius: `${height / 2}px`,
            transition: 'width 0.4s ease',
          }}
        />
      </div>
    </div>
  );
};
