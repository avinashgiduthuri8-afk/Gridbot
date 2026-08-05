import { useMemo } from "react";
import {
  Activity,
  TrendingUp,
  CalendarClock,
  Grid3x3,
  Wallet,
  Landmark,
  LineChart,
  PiggyBank,
} from "lucide-react";
import {
  useHealthCheckApiHealthGet,
  useGetPortfolioApiPortfolioGet,
  useListPositionsApiPositionsGet,
  useListTradeHistoryApiTradeHistoryGet,
} from "@workspace/api-client-react";
import { StatCard } from "@/components/StatCard";
import { QueryState } from "@/components/QueryState";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatSignedCurrency, pnlColorClass } from "@/lib/format";

/**
 * "Today's P&L" has no dedicated backend field (no endpoint aggregates P&L
 * by date). Rather than re-deriving P&L itself client-side, this sums the
 * `pnl` field /trade-history ALREADY returns per trade, filtered to today's
 * date — a date filter over backend-computed numbers, not a recalculation
 * of P&L. See Phase 4 delivery notes for why this is the one exception to
 * "portfolio/P&L must come from the backend" in this dashboard.
 */
function useTodaysPnl() {
  const query = useListTradeHistoryApiTradeHistoryGet({ limit: 1000 });
  const todaysPnl = useMemo(() => {
    if (!query.data) return null;
    const todayKey = new Date().toDateString();
    return query.data.trades
      .filter((t) => new Date(t.executed_at).toDateString() === todayKey)
      .reduce((sum, t) => sum + t.pnl, 0);
  }, [query.data]);
  return { ...query, todaysPnl };
}

export default function DashboardHome() {
  const health = useHealthCheckApiHealthGet();
  const portfolio = useGetPortfolioApiPortfolioGet();
  const positions = useListPositionsApiPositionsGet();
  const todaysPnlQuery = useTodaysPnl();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <QueryState
          isLoading={health.isLoading}
          isError={health.isError}
          error={health.error}
          data={health.data}
        >
          {(data) => (
            <Badge
              variant={data.status === "ok" ? "default" : "destructive"}
              data-testid="badge-bot-status"
            >
              <Activity className="mr-1 h-3 w-3" />
              {data.status === "ok" ? "Online" : "Degraded"}
            </Badge>
          )}
        </QueryState>
      </div>

      <QueryState
        isLoading={portfolio.isLoading}
        isError={portfolio.isError}
        error={portfolio.error}
        data={portfolio.data}
        onRetry={() => portfolio.refetch()}
      >
        {(p) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total P&L"
              value={formatSignedCurrency(p.combined_total)}
              icon={TrendingUp}
              valueClassName={pnlColorClass(p.combined_total)}
              testId="stat-total-pnl"
            />
            <StatCard
              label="Today's P&L"
              value={
                todaysPnlQuery.isLoading
                  ? "…"
                  : formatSignedCurrency(todaysPnlQuery.todaysPnl ?? 0)
              }
              icon={CalendarClock}
              valueClassName={pnlColorClass(todaysPnlQuery.todaysPnl ?? 0)}
              testId="stat-todays-pnl"
            />
            <StatCard
              label="Active Grids"
              value={String(p.active_grid_count)}
              icon={Grid3x3}
              testId="stat-active-grids"
            />
            <StatCard
              label="Active Positions"
              value={positions.data ? String(positions.data.count) : "…"}
              icon={Wallet}
              testId="stat-active-positions"
            />
            <StatCard
              label="Total Investment"
              value={formatCurrency(p.total_invested)}
              icon={Landmark}
              testId="stat-total-investment"
            />
            <StatCard
              label="Unrealized Profit"
              value={formatSignedCurrency(p.total_unrealized)}
              icon={LineChart}
              valueClassName={pnlColorClass(p.total_unrealized)}
              testId="stat-unrealized-profit"
            />
            <StatCard
              label="Realized Profit"
              value={formatSignedCurrency(p.total_realized)}
              icon={PiggyBank}
              valueClassName={pnlColorClass(p.total_realized)}
              testId="stat-realized-profit"
            />
          </div>
        )}
      </QueryState>
    </div>
  );
}
