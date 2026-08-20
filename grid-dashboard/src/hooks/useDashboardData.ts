import { useState, useEffect, useCallback, useRef } from 'react';
import { api, ApiError } from '../services/api';
import type {
  HealthResponse,
  GridResponse,
  PositionResponse,
  OrderResponse,
  TradeResponse,
  PortfolioResponse,
  AnalyticsResponse,
  SettingsResponse,
} from '../types/dashboard';

export interface DashboardData {
  health: HealthResponse | null;
  portfolio: PortfolioResponse | null;
  analytics: AnalyticsResponse | null;
  settings: SettingsResponse | null;
  grids: GridResponse[];
  positions: PositionResponse[];
  orders: OrderResponse[];
  trades: TradeResponse[];
}

export interface UseDashboardDataResult {
  data: DashboardData;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refetch: () => Promise<void>;
}

export function useDashboardData(pollIntervalMs = 15000): UseDashboardDataResult {
  const [data, setData] = useState<DashboardData>({
    health: null,
    portfolio: null,
    analytics: null,
    settings: null,
    grids: [],
    positions: [],
    orders: [],
    trades: [],
  });

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const isInitialMount = useRef(true);

  const fetchAllData = useCallback(async () => {
    if (isInitialMount.current) {
      setLoading(true);
    }
    setError(null);

    try {
      // Execute read-only API requests in parallel
      const [
        healthRes,
        portfolioRes,
        analyticsRes,
        settingsRes,
        gridsRes,
        positionsRes,
        ordersRes,
        tradesRes,
      ] = await Promise.allSettled([
        api.getHealth(),
        api.getPortfolio(),
        api.getAnalytics(),
        api.getSettings(),
        api.getGrids(),
        api.getPositions(),
        api.getOrders(undefined, 50),
        api.getTradeHistory(undefined, 50),
      ]);

      let hasFatalError = false;
      let errorMessage = '';

      // Health check result
      let health: HealthResponse | null = null;
      if (healthRes.status === 'fulfilled') {
        health = healthRes.value;
      } else {
        hasFatalError = true;
        errorMessage =
          healthRes.reason instanceof ApiError
            ? healthRes.reason.message
            : 'Failed to connect to backend server';
      }

      setData({
        health,
        portfolio: portfolioRes.status === 'fulfilled' ? portfolioRes.value : null,
        analytics: analyticsRes.status === 'fulfilled' ? analyticsRes.value : null,
        settings: settingsRes.status === 'fulfilled' ? settingsRes.value : null,
        grids: gridsRes.status === 'fulfilled' ? gridsRes.value.grids : [],
        positions: positionsRes.status === 'fulfilled' ? positionsRes.value.positions : [],
        orders: ordersRes.status === 'fulfilled' ? ordersRes.value.orders : [],
        trades: tradesRes.status === 'fulfilled' ? tradesRes.value.trades : [],
      });

      if (hasFatalError) {
        setError(errorMessage);
      } else {
        setError(null);
        setLastUpdated(new Date());
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'An unexpected error occurred',
      );
    } finally {
      setLoading(false);
      isInitialMount.current = false;
    }
  }, []);

  useEffect(() => {
    fetchAllData();

    if (pollIntervalMs > 0) {
      const interval = setInterval(() => {
        fetchAllData();
      }, pollIntervalMs);
      return () => clearInterval(interval);
    }
  }, [fetchAllData, pollIntervalMs]);

  return {
    data,
    loading,
    error,
    lastUpdated,
    refetch: fetchAllData,
  };
}
