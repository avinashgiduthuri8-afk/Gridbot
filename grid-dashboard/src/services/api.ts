import type {
  HealthResponse,
  GridListResponse,
  GridResponse,
  PositionListResponse,
  OrderListResponse,
  TradeHistoryResponse,
  PortfolioResponse,
  AnalyticsResponse,
  SettingsResponse,
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
        // Ignore json parse error for non-json responses
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

  getGrids: () => fetchApi<GridListResponse>('/grids'),

  getGrid: (gridId: string) => fetchApi<GridResponse>(`/grids/${encodeURIComponent(gridId)}`),

  getPositions: (prices?: string) => {
    const query = prices ? `?prices=${encodeURIComponent(prices)}` : '';
    return fetchApi<PositionListResponse>(`/positions${query}`);
  },

  getOrders: (gridId?: string, limit = 200) => {
    const params = new URLSearchParams();
    if (gridId) params.append('grid_id', gridId);
    if (limit) params.append('limit', limit.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return fetchApi<OrderListResponse>(`/orders${query}`);
  },

  getTradeHistory: (gridId?: string, limit = 200) => {
    const params = new URLSearchParams();
    if (gridId) params.append('grid_id', gridId);
    if (limit) params.append('limit', limit.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return fetchApi<TradeHistoryResponse>(`/trade-history${query}`);
  },

  getPortfolio: (prices?: string) => {
    const query = prices ? `?prices=${encodeURIComponent(prices)}` : '';
    return fetchApi<PortfolioResponse>(`/portfolio${query}`);
  },

  getAnalytics: () => fetchApi<AnalyticsResponse>('/analytics'),

  getSettings: () => fetchApi<SettingsResponse>('/settings'),
};
