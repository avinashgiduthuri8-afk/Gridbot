import { Landmark, LineChart, PiggyBank, TrendingUp, Wallet } from "lucide-react";
import { useGetPortfolioApiPortfolioGet } from "@workspace/api-client-react";
import { StatCard } from "@/components/StatCard";
import { QueryState } from "@/components/QueryState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatPercent, formatSignedCurrency, pnlColorClass } from "@/lib/format";

export default function Portfolio() {
  const query = useGetPortfolioApiPortfolioGet();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Portfolio</h1>
      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        data={query.data}
        onRetry={() => query.refetch()}
      >
        {(p) => {
          // Total Value = cost basis + unrealized gain/loss — a display sum
          // of two backend-provided numbers (total_invested, total_unrealized),
          // not a re-derivation of P&L. portfolio_return_pct below IS a
          // direct backend field (trading.portfolio_metrics.portfolio_totals).
          const totalValue = p.total_invested + p.total_unrealized;
          return (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <StatCard label="Total Value" value={formatCurrency(totalValue)} icon={Wallet} testId="stat-total-value" />
                <StatCard
                  label="Total Investment"
                  value={formatCurrency(p.total_invested)}
                  icon={Landmark}
                  testId="stat-total-investment"
                />
                <StatCard
                  label="Realized Profit"
                  value={formatSignedCurrency(p.total_realized)}
                  icon={PiggyBank}
                  valueClassName={pnlColorClass(p.total_realized)}
                  testId="stat-realized-profit"
                />
                <StatCard
                  label="Unrealized Profit"
                  value={formatSignedCurrency(p.total_unrealized)}
                  icon={LineChart}
                  valueClassName={pnlColorClass(p.total_unrealized)}
                  testId="stat-unrealized-profit"
                />
                <StatCard
                  label="ROI"
                  value={formatPercent(p.portfolio_return_pct, { signed: true })}
                  icon={TrendingUp}
                  valueClassName={pnlColorClass(p.portfolio_return_pct)}
                  testId="stat-roi"
                />
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Grid Status Breakdown</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <div className="text-sm text-muted-foreground">Active</div>
                    <div className="text-xl font-semibold">{p.active_grid_count}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Paused</div>
                    <div className="text-xl font-semibold">{p.paused_grid_count}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Completed</div>
                    <div className="text-xl font-semibold">{p.completed_grid_count}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Stopped</div>
                    <div className="text-xl font-semibold">{p.stopped_grid_count}</div>
                  </div>
                </CardContent>
              </Card>
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
