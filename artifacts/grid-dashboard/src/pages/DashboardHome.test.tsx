import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, mockQueryResult } from "@/test/test-utils";
import DashboardHome from "@/pages/DashboardHome";

const hoisted = vi.hoisted(() => ({
  health: vi.fn(),
  portfolio: vi.fn(),
  positions: vi.fn(),
  trades: vi.fn(),
}));

vi.mock("@workspace/api-client-react", () => ({
  useHealthCheckApiHealthGet: hoisted.health,
  useGetPortfolioApiPortfolioGet: hoisted.portfolio,
  useListPositionsApiPositionsGet: hoisted.positions,
  useListTradeHistoryApiTradeHistoryGet: hoisted.trades,
}));

const PORTFOLIO_DATA = {
  total_realized: 500,
  total_unrealized: 250,
  total_invested: 10000,
  combined_total: 750,
  portfolio_return_pct: 7.5,
  active_grid_count: 3,
  paused_grid_count: 1,
  completed_grid_count: 2,
  stopped_grid_count: 0,
};

describe("DashboardHome", () => {
  it("renders every required stat once data loads", () => {
    hoisted.health.mockReturnValue(mockQueryResult({ data: { status: "ok", database_connected: true } }));
    hoisted.portfolio.mockReturnValue(mockQueryResult({ data: PORTFOLIO_DATA }));
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: [], count: 2 } }));
    hoisted.trades.mockReturnValue(mockQueryResult({ data: { trades: [], count: 0 } }));

    renderWithProviders(<DashboardHome />);

    expect(screen.getByTestId("badge-bot-status")).toHaveTextContent("Online");
    expect(screen.getByTestId("stat-total-pnl")).toBeInTheDocument();
    expect(screen.getByTestId("stat-active-grids")).toHaveTextContent("3");
    expect(screen.getByTestId("stat-active-positions")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-total-investment")).toBeInTheDocument();
    expect(screen.getByTestId("stat-unrealized-profit")).toBeInTheDocument();
    expect(screen.getByTestId("stat-realized-profit")).toBeInTheDocument();
  });

  it("shows a loading skeleton while the portfolio query is pending", () => {
    hoisted.health.mockReturnValue(mockQueryResult({ isLoading: true }));
    hoisted.portfolio.mockReturnValue(mockQueryResult({ isLoading: true }));
    hoisted.positions.mockReturnValue(mockQueryResult({ isLoading: true }));
    hoisted.trades.mockReturnValue(mockQueryResult({ isLoading: true }));

    renderWithProviders(<DashboardHome />);
    expect(screen.getAllByTestId("state-loading").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("stat-total-pnl")).not.toBeInTheDocument();
  });

  it("shows an error state when the portfolio API call fails", () => {
    hoisted.health.mockReturnValue(mockQueryResult({ data: { status: "degraded", database_connected: false } }));
    hoisted.portfolio.mockReturnValue(
      mockQueryResult({ isError: true, error: new Error("Failed to fetch portfolio") }),
    );
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: [], count: 0 } }));
    hoisted.trades.mockReturnValue(mockQueryResult({ data: { trades: [], count: 0 } }));

    renderWithProviders(<DashboardHome />);
    expect(screen.getByTestId("state-error")).toBeInTheDocument();
    expect(screen.getByText("Failed to fetch portfolio")).toBeInTheDocument();
    expect(screen.getByTestId("badge-bot-status")).toHaveTextContent("Degraded");
  });
});
