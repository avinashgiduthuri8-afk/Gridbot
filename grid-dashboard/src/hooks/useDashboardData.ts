import { useState, useEffect, useCallback, useRef } from 'react';
import { api, ApiError } from '../services/api';
import type {
  HealthResponse,
  MarketRegimeResponse,
  SectorMatrixResponse,
  ScoredSignalResponse,
} from '../types/dashboard';

export interface DashboardData {
  health: HealthResponse | null;
  regime: MarketRegimeResponse | null;
  sectors: SectorMatrixResponse | null;
  topSignals: ScoredSignalResponse[];
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
    regime: null,
    sectors: null,
    topSignals: [],
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
      const [healthRes, regimeRes, sectorsRes, signalsRes] = await Promise.allSettled([
        api.getHealth(),
        api.getMarketRegime(),
        api.getSectorMatrix(),
        api.getSignals(10),
      ]);

      let hasFatalError = false;
      let errorMessage = '';

      let health: HealthResponse | null = null;
      if (healthRes.status === 'fulfilled') {
        health = healthRes.value;
      } else {
        hasFatalError = true;
        errorMessage =
          healthRes.reason instanceof ApiError
            ? healthRes.reason.message
            : 'Failed to connect to backend scanner server';
      }

      setData({
        health,
        regime: regimeRes.status === 'fulfilled' ? regimeRes.value : null,
        sectors: sectorsRes.status === 'fulfilled' ? sectorsRes.value : null,
        topSignals: signalsRes.status === 'fulfilled' ? signalsRes.value : [],
      });

      if (hasFatalError) {
        setError(errorMessage);
      } else {
        setError(null);
        setLastUpdated(new Date());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred');
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
