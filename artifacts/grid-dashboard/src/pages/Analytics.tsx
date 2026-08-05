import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  PolarGrid,
  PolarRadiusAxis,
  Label as RechartsLabel,
  XAxis,
} from "recharts";
import {
  useGetAnalyticsApiAnalyticsGet,
  useGetPortfolioApiPortfolioGet,
  useListTradeHistoryApiTradeHistoryGet,
} from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { QueryState } from "@/components/QueryState";
import { StatCard } from "@/components/StatCard";
import { Target } from "lucide-react";
import { aggregateDailyProfit, aggregateMonthlyProfit, buildPnlCurve } from "@/lib/chartData";
import { formatPercent } from "@/lib/format";

const profitConfig: ChartConfig = { profit: { label: "Profit", color: "var(--chart-1)" } };
const cumulativeConfig: ChartConfig = { cumulative: { label: "Cumulative P&L", color: "var(--chart-2)" } };
const winRateConfig: ChartConfig = { winRate: { label: "Win Rate", color: "var(--chart-1)" } };
const tradeCountConfig: ChartConfig = {
  buys: { label: "Buys", color: "var(--chart-1)" },
  sells: { label: "Sells", color: "var(--chart-2)" },
};
const gridDistConfig: ChartConfig = {
  active: { label: "Active", color: "var(--chart-1)" },
  paused: { label: "Paused", color: "var(--chart-2)" },
  completed: { label: "Completed", color: "var(--chart-3)" },
  stopped: { label: "Stopped", color: "var(--chart-4)" },
};

export default function Analytics() {
  const analytics = useGetAnalyticsApiAnalyticsGet();
  const portfolio = useGetPortfolioApiPortfolioGet();
  const trades = useListTradeHistoryApiTradeHistoryGet({ limit: 1000 });

  const dailyProfit = useMemo(() => aggregateDailyProfit(trades.data?.trades ?? []), [trades.data]);
  const monthlyProfit = useMemo(() => aggregateMonthlyProfit(trades.data?.trades ?? []), [trades.data]);
  const pnlCurve = useMemo(() => buildPnlCurve(trades.data?.trades ?? []), [trades.data]);

  const gridDistData = portfolio.data
    ? [
        { status: "active", count: portfolio.data.active_grid_count, fill: "var(--color-active)" },
        { status: "paused", count: portfolio.data.paused_grid_count, fill: "var(--color-paused)" },
        { status: "completed", count: portfolio.data.completed_grid_count, fill: "var(--color-completed)" },
        { status: "stopped", count: portfolio.data.stopped_grid_count, fill: "var(--color-stopped)" },
      ].filter((d) => d.count > 0)
    : [];

  const tradeCountData = analytics.data
    ? [{ name: "trades", buys: analytics.data.total_buys, sells: analytics.data.total_sells }]
    : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analytics</h1>

      <QueryState isLoading={analytics.isLoading} isError={analytics.isError} error={analytics.error} data={analytics.data} onRetry={() => analytics.refetch()}>
        {(a) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label="Win Rate" value={formatPercent(a.win_rate_pct)} icon={Target} testId="stat-win-rate" />
            <StatCard label="Profit Factor" value={a.profit_factor !== null && a.profit_factor !== undefined ? a.profit_factor.toFixed(2) : "n/a"} icon={Target} testId="stat-profit-factor" />
            <StatCard label="Max Drawdown" value={formatPercent(a.max_drawdown_pct)} icon={Target} testId="stat-max-drawdown" />
          </div>
        )}
      </QueryState>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Daily Profit (last 14 days)</CardTitle></CardHeader>
          <CardContent>
            <QueryState isLoading={trades.isLoading} isError={trades.isError} error={trades.error} data={dailyProfit} isEmpty={(d) => d.length === 0} emptyMessage="No trades yet.">
              {(data) => (
                <ChartContainer config={profitConfig} data-testid="chart-daily-profit">
                  <BarChart data={data}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={(v) => v.slice(5)} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="profit" fill="var(--color-profit)" radius={4} />
                  </BarChart>
                </ChartContainer>
              )}
            </QueryState>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Monthly Profit</CardTitle></CardHeader>
          <CardContent>
            <QueryState isLoading={trades.isLoading} isError={trades.isError} error={trades.error} data={monthlyProfit} isEmpty={(d) => d.length === 0} emptyMessage="No trades yet.">
              {(data) => (
                <ChartContainer config={profitConfig} data-testid="chart-monthly-profit">
                  <BarChart data={data}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="month" tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="profit" fill="var(--color-profit)" radius={4} />
                  </BarChart>
                </ChartContainer>
              )}
            </QueryState>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">P&L Curve</CardTitle></CardHeader>
          <CardContent>
            <QueryState isLoading={trades.isLoading} isError={trades.isError} error={trades.error} data={pnlCurve} isEmpty={(d) => d.length === 0} emptyMessage="No trades yet.">
              {(data) => (
                <ChartContainer config={cumulativeConfig} data-testid="chart-pnl-curve">
                  <LineChart data={data}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={(v) => v.slice(5)} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Line type="monotone" dataKey="cumulative" stroke="var(--color-cumulative)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ChartContainer>
              )}
            </QueryState>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Grid Distribution</CardTitle></CardHeader>
          <CardContent>
            <QueryState isLoading={portfolio.isLoading} isError={portfolio.isError} error={portfolio.error} data={gridDistData} isEmpty={(d) => d.length === 0} emptyMessage="No grids yet.">
              {(data) => (
                <ChartContainer config={gridDistConfig} data-testid="chart-grid-distribution">
                  <PieChart>
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Pie data={data} dataKey="count" nameKey="status" innerRadius={50}>
                      {data.map((d) => (
                        <Cell key={d.status} fill={d.fill} />
                      ))}
                    </Pie>
                  </PieChart>
                </ChartContainer>
              )}
            </QueryState>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Trade Count</CardTitle></CardHeader>
          <CardContent>
            <QueryState isLoading={analytics.isLoading} isError={analytics.isError} error={analytics.error} data={tradeCountData} isEmpty={(d) => d.length === 0} emptyMessage="No trades yet.">
              {(data) => (
                <ChartContainer config={tradeCountConfig} data-testid="chart-trade-count">
                  <BarChart data={data} layout="vertical">
                    <CartesianGrid horizontal={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="buys" fill="var(--color-buys)" radius={4} />
                    <Bar dataKey="sells" fill="var(--color-sells)" radius={4} />
                  </BarChart>
                </ChartContainer>
              )}
            </QueryState>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Win Rate</CardTitle></CardHeader>
          <CardContent>
            <QueryState isLoading={analytics.isLoading} isError={analytics.isError} error={analytics.error} data={analytics.data}>
              {(a) => (
                <ChartContainer config={winRateConfig} className="mx-auto aspect-square max-h-60" data-testid="chart-win-rate">
                  <RadialBarChart
                    data={[{ winRate: a.win_rate_pct, fill: "var(--color-winRate)" }]}
                    startAngle={90}
                    endAngle={90 - (360 * Math.min(Math.max(a.win_rate_pct, 0), 100)) / 100}
                    innerRadius={70}
                    outerRadius={110}
                  >
                    <PolarGrid gridType="circle" radialLines={false} stroke="none" />
                    <RadialBar dataKey="winRate" background cornerRadius={10} />
                    <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
                      <RechartsLabel
                        content={({ viewBox }) => {
                          if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                            return (
                              <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                                <tspan x={viewBox.cx} y={viewBox.cy} className="fill-foreground text-2xl font-bold">
                                  {a.win_rate_pct.toFixed(1)}%
                                </tspan>
                              </text>
                            );
                          }
                          return null;
                        }}
                      />
                    </PolarRadiusAxis>
                  </RadialBarChart>
                </ChartContainer>
              )}
            </QueryState>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
