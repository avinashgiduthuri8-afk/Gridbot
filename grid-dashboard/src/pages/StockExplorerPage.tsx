import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import type { StockInfoResponse, StockSearchResult, StockTechnicalHealthResponse, NavigationTab } from '../types/dashboard';
import {
  Search,
  ExternalLink,
  RefreshCw,
  TrendingUp,
  ShieldCheck,
  Activity,
  PlaySquare,
  Building2,
  PieChart,
  CheckCircle2,
} from 'lucide-react';

const TRENDING_PRESETS = [
  'TATAMOTORS',
  'RELIANCE',
  'TCS',
  'INFY',
  'HDFCBANK',
  'ICICIBANK',
  'LT',
  'BHARTIARTL',
  'ZOMATO',
  'IRFC',
  'SUZLON',
];

interface StockExplorerPageProps {
  initialSymbol?: string;
  onNavigate?: (tab: NavigationTab, prefillSymbol?: string) => void;
}

export const StockExplorerPage: React.FC<StockExplorerPageProps> = ({
  initialSymbol = 'TATAMOTORS',
  onNavigate,
}) => {
  const [query, setQuery] = useState<string>(initialSymbol);
  const [activeSymbol, setActiveSymbol] = useState<string>(initialSymbol);
  const [suggestions, setSuggestions] = useState<StockSearchResult[]>([]);
  const [showSuggestions, setShowSuggestions] = useState<boolean>(false);

  const [stockInfo, setStockInfo] = useState<StockInfoResponse | null>(null);
  const [techHealth, setTechHealth] = useState<StockTechnicalHealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Load stock details whenever activeSymbol changes
  useEffect(() => {
    if (!activeSymbol) return;

    const fetchStockData = async () => {
      setLoading(true);
      setError(null);
      try {
        const cleanSym = activeSymbol.replace('.NS', '').replace('.BO', '');
        const [info, health] = await Promise.all([
          api.getStockInfo(cleanSym),
          api.getStockTechnicalHealth(cleanSym).catch(() => null),
        ]);
        setStockInfo(info);
        setTechHealth(health);
      } catch (err: any) {
        setError(err.message || 'Failed to load stock data');
      } finally {
        setLoading(false);
      }
    };

    fetchStockData();
  }, [activeSymbol]);

  // Autocomplete search suggestions
  useEffect(() => {
    if (!query || query.trim().length === 0) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const results = await api.searchStocks(query, 8);
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  // Close suggestions on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleSelectSymbol = (sym: string) => {
    const cleanSym = sym.replace('.NS', '').replace('.BO', '').toUpperCase();
    setActiveSymbol(cleanSym);
    setQuery(cleanSym);
    setShowSuggestions(false);
  };

  const handleForceRefresh = async () => {
    if (!activeSymbol) return;
    setRefreshing(true);
    try {
      const cleanSym = activeSymbol.replace('.NS', '').replace('.BO', '');
      const [info, health] = await Promise.all([
        api.getStockInfo(cleanSym, true),
        api.getStockTechnicalHealth(cleanSym).catch(() => null),
      ]);
      setStockInfo(info);
      setTechHealth(health);
    } catch (err: any) {
      console.error('Refresh error:', err);
    } finally {
      setRefreshing(false);
    }
  };

  const cleanSym = activeSymbol.replace('.NS', '').replace('.BO', '').toUpperCase();

  // 52-Week Range position percentage
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 1. Hero Search & Autocomplete Toolbar */}
      <div
        style={{
          backgroundColor: '#111827',
          padding: '20px 24px',
          borderRadius: '12px',
          border: '1px solid #1F2937',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ maxWidth: '700px', margin: '0 auto', position: 'relative' }} ref={searchContainerRef}>
          <label style={{ fontSize: '12px', color: '#9CA3AF', fontWeight: 700, display: 'block', marginBottom: '6px' }}>
            UNIVERSAL NSE STOCK EXPLORER
          </label>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={18} color="#60A5FA" style={{ position: 'absolute', left: '14px' }} />
            <input
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
              placeholder="Search any NSE stock (e.g. RELIANCE, TATAMOTORS, ZOMATO, IRFC)..."
              style={{
                width: '100%',
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                padding: '12px 14px 12px 42px',
                color: '#F9FAFB',
                fontSize: '14px',
                fontWeight: 600,
                outline: 'none',
                boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.3)',
              }}
            />
            {query && (
              <button
                onClick={() => handleSelectSymbol(query)}
                style={{
                  position: 'absolute',
                  right: '8px',
                  backgroundColor: '#2563EB',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 14px',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Search
              </button>
            )}
          </div>

          {/* Autocomplete Suggestions Dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <div
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                right: 0,
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                marginTop: '4px',
                zIndex: 1000,
                boxShadow: '0 10px 25px rgba(0, 0, 0, 0.6)',
                maxHeight: '280px',
                overflowY: 'auto',
              }}
            >
              {suggestions.map((item, idx) => (
                <div
                  key={idx}
                  onClick={() => handleSelectSymbol(item.symbol)}
                  style={{
                    padding: '10px 16px',
                    borderBottom: idx < suggestions.length - 1 ? '1px solid #374151' : 'none',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#111827')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <div>
                    <strong style={{ color: '#60A5FA', fontSize: '13px' }}>{item.symbol}</strong>
                    <span style={{ color: '#9CA3AF', fontSize: '12px', marginLeft: '8px' }}>
                      {item.company_name}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <span style={{ fontSize: '11px', color: '#34D399', backgroundColor: '#064E3B', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                      {item.sector}
                    </span>
                    <span style={{ fontSize: '11px', color: '#93C5FD', backgroundColor: '#1E3A8A', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                      {item.market_cap_category}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick Trending Stock Chips */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', flexWrap: 'wrap', marginTop: '16px' }}>
          <span style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 700 }}>TRENDING:</span>
          {TRENDING_PRESETS.map((sym) => (
            <button
              key={sym}
              onClick={() => handleSelectSymbol(sym)}
              style={{
                backgroundColor: activeSymbol === sym ? '#2563EB' : '#1F2937',
                color: activeSymbol === sym ? '#FFFFFF' : '#D1D5DB',
                border: '1px solid #374151',
                borderRadius: '6px',
                padding: '3px 9px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '80px 0', color: '#9CA3AF', backgroundColor: '#111827', borderRadius: '12px' }}>
          <RefreshCw size={28} className="spin" style={{ margin: '0 auto 12px auto', color: '#3B82F6' }} />
          <p style={{ fontSize: '14px', fontWeight: 600 }}>Retrieving institutional data from NSE India, Screener.in &amp; Yahoo...</p>
        </div>
      ) : error ? (
        <div style={{ padding: '16px', backgroundColor: '#450A0A', border: '1px solid #7F1D1D', borderRadius: '12px', color: '#FCA5A5', fontSize: '13px' }}>
          <strong>Stock Analysis Error:</strong> {error}
        </div>
      ) : stockInfo ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* 2. Stock Header & External Action Links */}
          <div
            style={{
              backgroundColor: '#111827',
              padding: '20px 24px',
              borderRadius: '12px',
              border: '1px solid #1F2937',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              flexWrap: 'wrap',
              gap: '16px',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <h1 style={{ fontSize: '26px', fontWeight: 900, color: '#F9FAFB', margin: 0 }}>
                  {stockInfo.company_name} ({cleanSym}.NS)
                </h1>
                <span
                  style={{
                    fontSize: '11px',
                    padding: '3px 8px',
                    backgroundColor: '#1E3A8A',
                    color: '#93C5FD',
                    borderRadius: '6px',
                    fontWeight: 700,
                  }}
                >
                  {stockInfo.sector}
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
                  {stockInfo.market_cap_category}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', marginTop: '8px' }}>
                <div style={{ fontSize: '28px', fontWeight: 900, color: '#F9FAFB', fontFamily: 'monospace' }}>
                  ₹{stockInfo.current_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: '13px', color: '#9CA3AF' }}>
                  Market Cap: <strong style={{ color: '#60A5FA' }}>₹{stockInfo.market_cap_cr.toLocaleString('en-IN')} Cr</strong>
                </div>
                {stockInfo.isin && (
                  <div style={{ fontSize: '11px', color: '#6B7280' }}>
                    ISIN: {stockInfo.isin}
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                onClick={handleForceRefresh}
                disabled={refreshing}
                style={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#D1D5DB',
                  padding: '8px 12px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '12px',
                  fontWeight: 600,
                }}
                title="Force Refresh Latest Data"
              >
                <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
                Refresh
              </button>

              <button
                onClick={() => onNavigate && onNavigate('backtest', cleanSym)}
                style={{
                  backgroundColor: '#2563EB',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '8px 16px',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: '0 4px 6px -1px rgba(37, 99, 235, 0.4)',
                }}
              >
                <PlaySquare size={14} /> ⚡ Run Strategy Backtest
              </button>

              <a
                href={`https://www.screener.in/company/${cleanSym}/consolidated/`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  backgroundColor: '#1F2937',
                  color: '#93C5FD',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  textDecoration: 'none',
                  fontSize: '12px',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                Screener.in <ExternalLink size={12} />
              </a>

              <a
                href={`https://www.tradingview.com/chart/?symbol=NSE%3A${cleanSym}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  backgroundColor: '#1F2937',
                  color: '#34D399',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  textDecoration: 'none',
                  fontSize: '12px',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                TradingView <ExternalLink size={12} />
              </a>
            </div>
          </div>

          {/* 3. 52-Week Range Visual Slider Bar */}
          <div
            style={{
              backgroundColor: '#111827',
              padding: '16px 24px',
              borderRadius: '12px',
              border: '1px solid #1F2937',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#9CA3AF', marginBottom: '8px' }}>
              <span>52-Week Low: <strong style={{ color: '#F9FAFB' }}>₹{stockInfo.low_52w.toLocaleString('en-IN')}</strong></span>
              <span>Range Position: <strong style={{ color: '#60A5FA' }}>{range52Pct.toFixed(0)}%</strong></span>
              <span>52-Week High: <strong style={{ color: '#F9FAFB' }}>₹{stockInfo.high_52w.toLocaleString('en-IN')}</strong></span>
            </div>
            <div
              style={{
                position: 'relative',
                height: '8px',
                backgroundColor: '#1F2937',
                borderRadius: '4px',
                overflow: 'visible',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${range52Pct}%`,
                  background: 'linear-gradient(90deg, #3B82F6, #10B981)',
                  borderRadius: '4px',
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: '-4px',
                  left: `${range52Pct}%`,
                  transform: 'translateX(-50%)',
                  width: '16px',
                  height: '16px',
                  backgroundColor: '#FFFFFF',
                  border: '3px solid #10B981',
                  borderRadius: '50%',
                  boxShadow: '0 0 8px rgba(16, 185, 129, 0.8)',
                }}
              />
            </div>
          </div>

          {/* 4. 4-Quadrant Institutional Fundamentals Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            {/* Quadrant 1: Valuation & Financial Ratios */}
            <div style={{ backgroundColor: '#111827', padding: '20px', borderRadius: '12px', border: '1px solid #1F2937' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 800, color: '#F9FAFB', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <PieChart size={17} color="#60A5FA" /> Valuation &amp; Financial Ratios
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Stock P/E:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.stock_pe ? `${stockInfo.stock_pe.toFixed(1)}x` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Industry P/E:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#60A5FA', marginTop: '2px' }}>
                    {stockInfo.industry_pe ? `${stockInfo.industry_pe.toFixed(1)}x` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Price-to-Book (P/B):</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.price_to_book ? `${stockInfo.price_to_book.toFixed(2)}x` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Book Value:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.book_value ? `₹${stockInfo.book_value.toFixed(2)}` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Dividend Yield:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#10B981', marginTop: '2px' }}>
                    {stockInfo.dividend_yield_pct ? `${stockInfo.dividend_yield_pct.toFixed(2)}%` : '0.00%'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>EPS (TTM):</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.eps_ttm ? `₹${stockInfo.eps_ttm.toFixed(2)}` : '--'}
                  </div>
                </div>
              </div>
            </div>

            {/* Quadrant 2: Profitability & Health */}
            <div style={{ backgroundColor: '#111827', padding: '20px', borderRadius: '12px', border: '1px solid #1F2937' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 800, color: '#F9FAFB', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <TrendingUp size={17} color="#10B981" /> Profitability &amp; Balance Sheet Health
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>ROCE:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: stockInfo.roce_pct >= 15 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
                    {stockInfo.roce_pct ? `${stockInfo.roce_pct.toFixed(1)}%` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>ROE:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: stockInfo.roe_pct >= 15 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
                    {stockInfo.roe_pct ? `${stockInfo.roe_pct.toFixed(1)}%` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Debt to Equity:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: stockInfo.debt_to_equity <= 1.0 ? '#10B981' : '#EF4444', marginTop: '2px' }}>
                    {stockInfo.debt_to_equity ? stockInfo.debt_to_equity.toFixed(2) : '0.00'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Interest Coverage:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.interest_coverage ? `${stockInfo.interest_coverage.toFixed(1)}x` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px', gridColumn: 'span 2' }}>
                  <span style={{ color: '#9CA3AF' }}>Free Cash Flow (FCF):</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: stockInfo.free_cash_flow_cr >= 0 ? '#10B981' : '#EF4444', marginTop: '2px' }}>
                    ₹{stockInfo.free_cash_flow_cr.toLocaleString('en-IN')} Cr
                  </div>
                </div>
              </div>
            </div>

            {/* Quadrant 3: NSE Live Delivery & Circuits */}
            <div style={{ backgroundColor: '#111827', padding: '20px', borderRadius: '12px', border: '1px solid #1F2937' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 800, color: '#F9FAFB', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={17} color="#F59E0B" /> NSE Live Delivery &amp; Circuit Limits
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Delivery %:</span>
                  <div style={{ fontWeight: 800, fontSize: '16px', color: stockInfo.delivery_pct >= 50 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
                    {stockInfo.delivery_pct ? `${stockInfo.delivery_pct.toFixed(1)}%` : '--'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Circuit Band:</span>
                  <div style={{ fontWeight: 800, fontSize: '16px', color: '#60A5FA', marginTop: '2px' }}>
                    ±{stockInfo.circuit_band_pct.toFixed(0)}%
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Upper Circuit:</span>
                  <div style={{ fontWeight: 800, fontSize: '14px', color: '#10B981', marginTop: '2px' }}>
                    ₹{stockInfo.upper_circuit.toFixed(2)}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Lower Circuit:</span>
                  <div style={{ fontWeight: 800, fontSize: '14px', color: '#EF4444', marginTop: '2px' }}>
                    ₹{stockInfo.lower_circuit.toFixed(2)}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px', gridColumn: 'span 2' }}>
                  <span style={{ color: '#9CA3AF' }}>Traded Volume (Shares):</span>
                  <div style={{ fontWeight: 800, fontSize: '14px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.traded_volume ? stockInfo.traded_volume.toLocaleString('en-IN') : '--'}
                  </div>
                </div>
              </div>
            </div>

            {/* Quadrant 4: Shareholding Distribution */}
            <div style={{ backgroundColor: '#111827', padding: '20px', borderRadius: '12px', border: '1px solid #1F2937' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 800, color: '#F9FAFB', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Building2 size={17} color="#A78BFA" /> Shareholding Distribution (QoQ)
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Promoter Holding:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#F9FAFB', marginTop: '2px' }}>
                    {stockInfo.promoter_holding_pct.toFixed(2)}%
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>Pledged Shares:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: stockInfo.pledged_pct === 0 ? '#10B981' : '#EF4444', marginTop: '2px' }}>
                    {stockInfo.pledged_pct.toFixed(2)}% {stockInfo.pledged_pct === 0 ? '🟢' : '⚠️'}
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>FII / FPI Holding:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#60A5FA', marginTop: '2px' }}>
                    {stockInfo.fii_holding_pct.toFixed(2)}%
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px' }}>
                  <span style={{ color: '#9CA3AF' }}>DII / Mutual Funds:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#34D399', marginTop: '2px' }}>
                    {stockInfo.dii_holding_pct.toFixed(2)}%
                  </div>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '10px', borderRadius: '6px', gridColumn: 'span 2' }}>
                  <span style={{ color: '#9CA3AF' }}>Public &amp; Retail:</span>
                  <div style={{ fontWeight: 800, fontSize: '15px', color: '#9CA3AF', marginTop: '2px' }}>
                    {stockInfo.public_holding_pct.toFixed(2)}% (Promoter Trend: 🟢 STABLE)
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 5. Technical Health & Setup Confluence Diagnostic */}
          {techHealth && (
            <div style={{ backgroundColor: '#111827', padding: '20px', borderRadius: '12px', border: '1px solid #1F2937' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 800, color: '#F9FAFB', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldCheck size={18} color="#10B981" /> Technical Health &amp; Confluence Checklist
                </h3>
                <span
                  style={{
                    padding: '3px 10px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 700,
                    backgroundColor: techHealth.trend_baseline.includes('UPTREND') ? '#064E3B' : '#1F2937',
                    color: techHealth.trend_baseline.includes('UPTREND') ? '#34D399' : '#9CA3AF',
                  }}
                >
                  {techHealth.trend_baseline.replace('_', ' ')}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', fontSize: '12px' }}>
                <div style={{ backgroundColor: '#1F2937', padding: '12px', borderRadius: '8px' }}>
                  <div style={{ color: '#9CA3AF' }}>Mansfield RS Alpha:</div>
                  <strong style={{ color: techHealth.rs_alpha >= 0 ? '#10B981' : '#EF4444', fontSize: '16px' }}>
                    {techHealth.rs_alpha >= 0 ? '+' : ''}{techHealth.rs_alpha.toFixed(2)} vs NIFTY 500
                  </strong>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '12px', borderRadius: '8px' }}>
                  <div style={{ color: '#9CA3AF' }}>20 EMA Extension:</div>
                  <strong style={{ color: techHealth.extension_from_20_ema_pct <= 4.5 ? '#10B981' : '#EF4444', fontSize: '16px' }}>
                    {techHealth.extension_from_20_ema_pct.toFixed(1)}% (Safe &le; 4.5%)
                  </strong>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '12px', borderRadius: '8px' }}>
                  <div style={{ color: '#9CA3AF' }}>Detected Setup:</div>
                  <strong style={{ color: '#60A5FA', fontSize: '14px' }}>
                    {techHealth.detected_setup} (Score: {techHealth.setup_quality_score.toFixed(0)})
                  </strong>
                </div>

                <div style={{ backgroundColor: '#1F2937', padding: '12px', borderRadius: '8px' }}>
                  <div style={{ color: '#9CA3AF' }}>Circuit Proximity Buffer:</div>
                  <strong style={{ color: techHealth.circuit_proximity_pct >= 2.0 ? '#10B981' : '#F59E0B', fontSize: '16px' }}>
                    {techHealth.circuit_proximity_pct.toFixed(1)}% Buffer
                  </strong>
                </div>
              </div>

              {techHealth.reasons && techHealth.reasons.length > 0 && (
                <div style={{ marginTop: '14px', backgroundColor: '#1F2937', padding: '12px 16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '11px', color: '#9CA3AF', fontWeight: 700, marginBottom: '6px' }}>
                    CONFLUENCE DIAGNOSTIC LOGS:
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', color: '#D1D5DB' }}>
                    {techHealth.reasons.map((r, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <CheckCircle2 size={13} color="#10B981" /> {r}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 6. Company Business Summary */}
          {stockInfo.business_summary && (
            <div style={{ backgroundColor: '#111827', padding: '20px', borderRadius: '12px', border: '1px solid #1F2937' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 800, color: '#F9FAFB', marginBottom: '10px' }}>
                About {stockInfo.company_name}
              </h3>
              <p style={{ fontSize: '13px', color: '#9CA3AF', lineHeight: 1.6, margin: 0 }}>
                {stockInfo.business_summary}
              </p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
};
