import type {
  HealthResponse,
  MarketRegimeResponse,
  SectorMatrixResponse,
  ScanResponse,
  SignalPerformanceStats,
  SessionInfo,
  ScoredSignalResponse,
} from '../types/dashboard';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function fetchApi<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const response = await fetch(url, {
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...init?.headers,
      },
      ...init,
    });

    if (!response.ok) {
      let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorMessage = errorJson.detail;
        }
      } catch {
        // Ignore json parse error
      }
      throw new ApiError(response.status, errorMessage);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      0,
      error instanceof Error ? error.message : 'Network failure or server offline',
    );
  }
}

export const api = {
  getHealth: () => fetchApi<HealthResponse>('/health'),

  // Indian Stock Scanner APIs (PROJECT-BETA)
  triggerScan: (universe = 'NIFTY_100', maxSignals = 3) =>
    fetchApi<ScanResponse>('/scanner/scan', {
      method: 'POST',
      body: JSON.stringify({ universe, max_signals: maxSignals }),
    }),

  getLatestScan: () => fetchApi<ScanResponse>('/scanner/latest'),

  getSessionStatus: () => fetchApi<SessionInfo>('/scanner/session'),

  getMarketRegime: () => fetchApi<MarketRegimeResponse>('/regime'),

  getSectorMatrix: () => fetchApi<SectorMatrixResponse>('/sectors'),

  getSignals: (limit = 50, status?: string, minScore?: number) => {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (status) params.append('status', status);
    if (minScore !== undefined) params.append('min_score', minScore.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return fetchApi<ScoredSignalResponse[]>(`/signals${query}`);
  },

  getSignalsHistory: (limit = 50, status?: string, minScore?: number) => {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (status) params.append('status', status);
    if (minScore !== undefined) params.append('min_score', minScore.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return fetchApi<any[]>(`/signals${query}`);
  },

  getSignalDetail: (signalId: string) =>
    fetchApi<any>(`/signals/${encodeURIComponent(signalId)}`),

  getSignalPerformance: () =>
    fetchApi<SignalPerformanceStats>('/signals/performance'),

  getStrategies: () =>
    fetchApi<any[]>('/backtest/strategies'),

  runBacktest: (params: any = {}) =>
    fetchApi<any>('/backtest/run', {
      method: 'POST',
      body: JSON.stringify(typeof params === 'string' ? { universe: params } : params),
    }),

  // Stock Fundamentals & NSE Delivery APIs
  getStockInfo: (symbol: string, forceRefresh = false) =>
    fetchApi<any>(`/stocks/${encodeURIComponent(symbol)}/info${forceRefresh ? '?force_refresh=true' : ''}`),

  getStockRatios: (symbol: string) =>
    fetchApi<any>(`/stocks/${encodeURIComponent(symbol)}/ratios`),

  getStockDelivery: (symbol: string) =>
    fetchApi<any>(`/stocks/${encodeURIComponent(symbol)}/delivery`),

  getBatchStockInfo: (symbols: string[]) =>
    fetchApi<Record<string, any>>(`/stocks/batch-info?symbols=${encodeURIComponent(symbols.join(','))}`),

  // Signal Ledger & R-Multiple APIs
  getLedgerStats: () =>
    fetchApi<any>('/ledger/stats'),

  getActiveLedgerSignals: () =>
    fetchApi<any[]>('/ledger/active'),

  evaluateLedger: (quotes: Record<string, number>) =>
    fetchApi<any>('/ledger/evaluate', {
      method: 'POST',
      body: JSON.stringify(quotes),
    }),

  // Execution Bots & Webhook Dispatch APIs
  getRegisteredBots: (activeOnly = false) =>
    fetchApi<any[]>(`/dispatch/bots${activeOnly ? '?active_only=true' : ''}`),

  registerBot: (bot: any) =>
    fetchApi<any>('/dispatch/bots', {
      method: 'POST',
      body: JSON.stringify(bot),
    }),

  deleteBot: (botId: string) =>
    fetchApi<any>(`/dispatch/bots/${encodeURIComponent(botId)}`, {
      method: 'DELETE',
    }),

  testPingBot: (botId: string) =>
    fetchApi<any>(`/dispatch/test-ping/${encodeURIComponent(botId)}`, {
      method: 'POST',
    }),

  getDispatchLogs: (limit = 50) =>
    fetchApi<any[]>(`/dispatch/logs?limit=${limit}`),
};
