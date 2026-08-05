import type { TradeResponse } from "@workspace/api-client-react";

/**
 * Chart-data aggregation helpers.
 *
 * No FastAPI endpoint aggregates P&L by day/month or exposes a running P&L
 * curve — /trade-history only returns individual trades. These functions
 * GROUP and SUM the `pnl` field /trade-history already returns per trade;
 * they never re-derive what a trade's P&L *is* (that number always comes
 * verbatim from the backend). This is the same disclosed exception as
 * "Today's P&L" on the Dashboard Home page — see Phase 4 delivery notes.
 */

export interface DailyProfitPoint {
  date: string; // YYYY-MM-DD
  profit: number;
}

export function aggregateDailyProfit(trades: TradeResponse[], days = 14): DailyProfitPoint[] {
  const byDay = new Map<string, number>();
  for (const t of trades) {
    const day = t.executed_at.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + t.pnl);
  }
  const sortedDays = [...byDay.keys()].sort();
  const lastN = sortedDays.slice(-days);
  return lastN.map((date) => ({ date, profit: byDay.get(date)! }));
}

export interface MonthlyProfitPoint {
  month: string; // YYYY-MM
  profit: number;
}

export function aggregateMonthlyProfit(trades: TradeResponse[]): MonthlyProfitPoint[] {
  const byMonth = new Map<string, number>();
  for (const t of trades) {
    const month = t.executed_at.slice(0, 7);
    byMonth.set(month, (byMonth.get(month) ?? 0) + t.pnl);
  }
  return [...byMonth.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([month, profit]) => ({ month, profit }));
}

export interface PnlCurvePoint {
  date: string;
  cumulative: number;
}

export function buildPnlCurve(trades: TradeResponse[]): PnlCurvePoint[] {
  const sorted = [...trades].sort((a, b) => a.executed_at.localeCompare(b.executed_at));
  let running = 0;
  return sorted.map((t) => {
    running += t.pnl;
    return { date: t.executed_at.slice(0, 10), cumulative: running };
  });
}
