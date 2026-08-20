import React from 'react';
import type { StatusType } from '../../types/dashboard';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  showDot?: boolean;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  showDot = true,
  className = '',
}) => {
  const displayLabel = label || status;

  return (
    <span className={`status-badge ${status.toLowerCase()} ${className}`}>
      {showDot && <span className="dot" />}
      {displayLabel}
    </span>
  );
};
