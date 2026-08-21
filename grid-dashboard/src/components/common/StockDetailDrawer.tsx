import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import type { StockInfoResponse } from '../../types/dashboard';
import {
  X,
  ExternalLink,
  RefreshCw,
  TrendingUp,
  PieChart,
  Zap,
} from 'lucide-react';

interface StockDetailDrawerProps {
  symbol: string | null;
  onClose: () => void;
}

export const StockDetailDrawer: React.FC<StockDetailDrawerProps> = ({ symbol, onClose }) => {
  const [stockInfo, setStockInfo] = useState<StockInfoResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) {
      setStockInfo(null);
      return;
    }

    const fetchInfo = async () => {
      setLoading(true);
      setError(null);
      try {
        const cleanSym = symbol.replace('.NS', '').replace('.BO', '');
        const data = await api.getStockInfo(cleanSym);
        setStockInfo(data);
      } catch (err: any) {
        setError(err.message || 'Failed to load stock fundamentals');
      } finally {
        setLoading(false);
      }
    };

    fetchInfo();
  }, [symbol]);

  const handleForceRefresh = async () => {
    if (!symbol) return;
    setRefreshing(true);
    try {
      const cleanSym = symbol.replace('.NS', '').replace('.BO', '');
      const data = await api.getStockInfo(cleanSym, true);
      setStockInfo(data);
    } catch (err: any) {
      console.error('Refresh error:', err);
    } finally {
      setRefreshing(false);
    }
  };

  if (!symbol) return null;

  const cleanSym = symbol.replace('.NS', '').replace('.BO', '');

  // 52-Week Range position calculation
  let range52Pct = 50;
  if (stockInfo && stockInfo.high_52w > stockInfo.low_52w) {
    range52Pct = Math.max(
      0,
      Math.min(
        100,
        ((stockInfo.current_price - stockInfo.low_52w) /
          (stockInfo.high_52w - stockInfo.low_52w)) *
          100
      )
    );
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(5px)',
        zIndex: 99999,
        display: 'flex',
        justifyContent: 'flex-end',
        transition: 'all 0.3s ease',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          height: '100%',
          backgroundColor: '#111827',
          borderLeft: '1px solid #374151',
          boxShadow: '-10px 0 25px rgba(0, 0, 0, 0.6)',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          padding: '24px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            borderBottom: '1px solid #1F2937',
            paddingBottom: '16px',
            marginBottom: '20px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: '24px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
                {cleanSym}
              </h2>
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  backgroundColor: '#1F2937',
                  color: '#60A5FA',
                  borderRadius: '6px',
                  fontWeight: 700,
                }}
              >
                {stockInfo?.sector || 'General'}
              </span>
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  backgroundColor: '#064E3B',
                  color: '#34D399',
                  borderRadius: '6px',
                  fontWeight: 700,
                }}
              >
                {stockInfo?.market_cap_category || 'Large Cap'}
              </span>
            </div>
            <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
              {stockInfo?.company_name || `${cleanSym} Limited`}
            </p>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleForceRefresh}
              disabled={refreshing || loading}
              style={{
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                color: '#D1D5DB',
                padding: '6px 10px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '12px',
              }}
              title="Force Refresh Data"
            >
              <RefreshCw size={13} className={refreshing ? 'spin' : ''} />
            </button>
            <button
              onClick={onClose}
              style={{
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                color: '#9CA3AF',
                padding: '6px 10px',
                cursor: 'pointer',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#9CA3AF' }}>
            <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px auto' }} />
            <p>Fetching institutional fundamentals from NSE, Screener & Yahoo...</p>
          </div>
        ) : error ? (
          <div
            style={{
              padding: '16px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid #7F1D1D',
              borderRadius: '8px',
              color: '#FCA5A5',
              fontSize: '13px',
            }}
          >
            {error}
          </div>
        ) : stockInfo ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
            {/* 1. Price & 52-Week Range Visual Slider */}
            <div
              style={{
                backgroundColor: '#1F2937',
                padding: '16px',
                borderRadius: '12px',
                border: '1px solid #374151',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
                <div>
                  <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 600 }}>CURRENT MARKET PRICE</div>
                  <div style={{ fontSize: '26px', fontWeight: 900, color: '#F9FAFB', marginTop: '2px' }}>
                    ₹{stockInfo.current_price.toLocaleString('en-IN')}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '11px', color: '#9CA3AF' }}>MARKET CAP</div>
                  <div style={{ fontSize: '16px', fontWeight: 800, color: '#60A5FA', marginTop: '2px' }}>
                    ₹{stockInfo.market_cap_cr.toLocaleString('en-IN')} Cr
                  </div>
                </div>
              </div>

              {/* 52W Range Bar */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#9CA3AF', marginBottom: '6px' }}>
                  <span>52W Low: <strong>₹{stockInfo.low_52w.toLocaleString('en-IN')}</strong></span>
                  <span>52W Range: <strong>{range52Pct.toFixed(0)}%</strong></span>
                  <span>52W High: <strong>₹{stockInfo.high_52w.toLocaleString('en-IN')}</strong></span>
                </div>
                <div
                  style={{
                    position: 'relative',
                    height: '8px',
                    backgroundColor: '#111827',
                    borderRadius: '4px',
                    overflow: 'visible',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${range52Pct}%`,
                      background: 'linear-gradient(90deg, #EF4444 0%, #F59E0B 50%, #10B981 100%)',
                      borderRadius: '4px',
                    }}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      top: '-4px',
                      left: `calc(${range52Pct}% - 8px)`,
                      width: '16px',
                      height: '16px',
                      borderRadius: '50%',
                      backgroundColor: '#60A5FA',
                      border: '2px solid #FFFFFF',
                      boxShadow: '0 0 8px rgba(96, 165, 250, 0.8)',
                    }}
                    title={`Current: ₹${stockInfo.current_price}`}
                  />
                </div>
              </div>
            </div>

            {/* 2. Key Financial Ratios (Screener.in Matrix) */}
            <div>
              <h4
                style={{
                  fontSize: '12px',
                  color: '#9CA3AF',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  marginBottom: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Zap size={14} color="#F59E0B" /> Key Fundamental Ratios
              </h4>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '10px',
                }}
              >
                <div style={{ backgroundColor: '#1F2937', padding: '10px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '10px', color: '#9CA3AF' }}>STOCK P/E</div>
                  <div style={{ fontSize: '15px', fontWeight: 800, color: stockInfo.stock_pe <= stockInfo.industry_pe ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
                    {stockInfo.stock_pe > 0 ? `${stockInfo.stock_pe}x` : 'N/A'}
                  </div>
                  <div style={{ fontSize: '9px', color: '#9CA3AF' }}>Ind P/E: {stockInfo.industry_pe}x</div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '10px', color: '#9CA3AF' }}>ROCE</div>
                  <div style={{ fontSize: '15px', fontWeight: 800, color: stockInfo.roce_pct >= 15 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
                    {stockInfo.roce_pct.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '9px', color: '#9CA3AF' }}>Capital Efficiency</div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '10px', color: '#9CA3AF' }}>ROE</div>
                  <div style={{ fontSize: '15px', fontWeight: 800, color: stockInfo.roe_pct >= 15 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
                    {stockInfo.roe_pct.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '9px', color: '#9CA3AF' }}>Equity Return</div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '10px', color: '#9CA3AF' }}>DEBT TO EQUITY</div>
                  <div style={{ fontSize: '15px', fontWeight: 800, color: stockInfo.debt_to_equity < 0.5 ? '#10B981' : stockInfo.debt_to_equity < 1.0 ? '#F59E0B' : '#EF4444', marginTop: '2px' }}>
                    {stockInfo.debt_to_equity.toFixed(2)}
                  </div>
                  <div style={{ fontSize: '9px', color: '#9CA3AF' }}>{stockInfo.debt_to_equity < 0.5 ? 'Low Leverage' : 'Moderate'}</div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '10px', color: '#9CA3AF' }}>DIVIDEND YIELD</div>
                  <div style={{ fontSize: '15px', fontWeight: 800, color: '#60A5FA', marginTop: '2px' }}>
                    {stockInfo.dividend_yield_pct.toFixed(2)}%
                  </div>
                  <div style={{ fontSize: '9px', color: '#9CA3AF' }}>Annualized</div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '10px', color: '#9CA3AF' }}>FREE CASH FLOW</div>
                  <div style={{ fontSize: '15px', fontWeight: 800, color: stockInfo.free_cash_flow_cr > 0 ? '#10B981' : '#EF4444', marginTop: '2px' }}>
                    ₹{stockInfo.free_cash_flow_cr.toFixed(0)} Cr
                  </div>
                  <div style={{ fontSize: '9px', color: '#9CA3AF' }}>Annual FCF</div>
                </div>
              </div>
            </div>

            {/* 3. NSE Live Trading & Delivery Insights */}
            <div>
              <h4
                style={{
                  fontSize: '12px',
                  color: '#9CA3AF',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  marginBottom: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <TrendingUp size={14} color="#10B981" /> NSE Delivery & Circuit Limits
              </h4>
              <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', color: '#D1D5DB' }}>Delivery Percentage</span>
                  <span
                    style={{
                      fontSize: '13px',
                      fontWeight: 800,
                      color:
                        stockInfo.delivery_pct >= 50
                          ? '#10B981'
                          : stockInfo.delivery_pct >= 35
                          ? '#F59E0B'
                          : '#9CA3AF',
                    }}
                  >
                    {stockInfo.delivery_pct.toFixed(1)}% ({stockInfo.delivery_quantity.toLocaleString()} Shares)
                  </span>
                </div>
                <div style={{ height: '6px', backgroundColor: '#111827', borderRadius: '3px', overflow: 'hidden', marginBottom: '12px' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${stockInfo.delivery_pct}%`,
                      backgroundColor: stockInfo.delivery_pct >= 50 ? '#10B981' : stockInfo.delivery_pct >= 35 ? '#F59E0B' : '#6B7280',
                    }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', paddingTop: '8px', borderTop: '1px solid #374151' }}>
                  <div>
                    <span style={{ fontSize: '10px', color: '#9CA3AF' }}>LOWER CIRCUIT (20%)</span>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: '#EF4444' }}>
                      ₹{stockInfo.lower_circuit.toLocaleString()}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '10px', color: '#9CA3AF' }}>UPPER CIRCUIT (20%)</span>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: '#10B981' }}>
                      ₹{stockInfo.upper_circuit.toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 4. Shareholding Pattern Bar */}
            <div>
              <h4
                style={{
                  fontSize: '12px',
                  color: '#9CA3AF',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  marginBottom: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <PieChart size={14} color="#8B5CF6" /> Shareholding Distribution
              </h4>
              <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '10px' }}>
                <div style={{ display: 'flex', height: '14px', borderRadius: '6px', overflow: 'hidden', marginBottom: '10px' }}>
                  <div style={{ width: `${stockInfo.promoter_holding_pct}%`, backgroundColor: '#3B82F6' }} title={`Promoter: ${stockInfo.promoter_holding_pct}%`} />
                  <div style={{ width: `${stockInfo.fii_holding_pct}%`, backgroundColor: '#06B6D4' }} title={`FII: ${stockInfo.fii_holding_pct}%`} />
                  <div style={{ width: `${stockInfo.dii_holding_pct}%`, backgroundColor: '#10B981' }} title={`DII: ${stockInfo.dii_holding_pct}%`} />
                  <div style={{ width: `${stockInfo.public_holding_pct}%`, backgroundColor: '#6B7280' }} title={`Public: ${stockInfo.public_holding_pct}%`} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px', fontSize: '11px', textAlign: 'center' }}>
                  <div>
                    <span style={{ color: '#3B82F6', fontWeight: 700 }}>Promoter</span>
                    <div style={{ fontWeight: 600, color: '#F9FAFB' }}>{stockInfo.promoter_holding_pct.toFixed(1)}%</div>
                  </div>
                  <div>
                    <span style={{ color: '#06B6D4', fontWeight: 700 }}>FII</span>
                    <div style={{ fontWeight: 600, color: '#F9FAFB' }}>{stockInfo.fii_holding_pct.toFixed(1)}%</div>
                  </div>
                  <div>
                    <span style={{ color: '#10B981', fontWeight: 700 }}>DII</span>
                    <div style={{ fontWeight: 600, color: '#F9FAFB' }}>{stockInfo.dii_holding_pct.toFixed(1)}%</div>
                  </div>
                  <div>
                    <span style={{ color: '#9CA3AF', fontWeight: 700 }}>Public</span>
                    <div style={{ fontWeight: 600, color: '#F9FAFB' }}>{stockInfo.public_holding_pct.toFixed(1)}%</div>
                  </div>
                </div>
              </div>
            </div>

            {/* 5. Direct External Links Action Bar */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
              <a
                href={`https://www.nseindia.com/get-quotes/equity?symbol=${cleanSym}`}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                  padding: '10px',
                  backgroundColor: '#1E3A8A',
                  color: '#93C5FD',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  textDecoration: 'none',
                  border: '1px solid #2563EB',
                }}
              >
                NSE India <ExternalLink size={12} />
              </a>

              <a
                href={`https://www.screener.in/company/${cleanSym}/consolidated/`}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                  padding: '10px',
                  backgroundColor: '#064E3B',
                  color: '#34D399',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  textDecoration: 'none',
                  border: '1px solid #059669',
                }}
              >
                Screener.in <ExternalLink size={12} />
              </a>

              <a
                href={`https://in.tradingview.com/chart/?symbol=NSE:${cleanSym}`}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                  padding: '10px',
                  backgroundColor: '#374151',
                  color: '#F9FAFB',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  textDecoration: 'none',
                  border: '1px solid #4B5563',
                }}
              >
                TradingView <ExternalLink size={12} />
              </a>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
