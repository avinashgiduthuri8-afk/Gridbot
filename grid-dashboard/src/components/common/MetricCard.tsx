import React from 'react';
import { Card } from './Card';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { MetricData } from '../../types/dashboard';

interface MetricCardProps extends MetricData {
  icon?: React.ReactNode;
  loading?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  change,
  trend,
  subtext,
  accentColor,
  icon,
  loading = false,
}) => {
  return (
    <Card
      hoverable
      className="metric-card"
      style={accentColor ? ({ '--accent-color': accentColor } as React.CSSProperties) : undefined}
    >
      <div className="metric-header">
        <span className="metric-title">{title}</span>
        {icon && <div className="metric-icon-box">{icon}</div>}
      </div>

      {loading ? (
        <div style={{ height: '38px', opacity: 0.5, display: 'flex', alignItems: 'center' }}>
          Loading...
        </div>
      ) : (
        <div className="metric-value">{value}</div>
      )}

      {(change || subtext) && (
        <div className="metric-footer">
          {change && (
            <span className={`metric-trend ${trend || 'neutral'}`}>
              {trend === 'up' && <TrendingUp size={12} />}
              {trend === 'down' && <TrendingDown size={12} />}
              {trend === 'neutral' && <Minus size={12} />}
              {change}
            </span>
          )}
          {subtext && <span className="metric-subtext">{subtext}</span>}
        </div>
      )}
    </Card>
  );
};
