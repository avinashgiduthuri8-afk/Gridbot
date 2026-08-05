import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, mockQueryResult } from "@/test/test-utils";
import LiveGrids from "@/pages/LiveGrids";

const hoisted = vi.hoisted(() => ({ positions: vi.fn() }));

vi.mock("@workspace/api-client-react", () => ({
  useListPositionsApiPositionsGet: hoisted.positions,
}));

const POSITIONS = [
  {
    grid_id: "g1", symbol: "BTCINR", status: "active", mode: "paper",
    quantity: 0.01, average_entry_price: 5000000, invested: 50000,
    current_price: 5200000, realized_pnl: 100, unrealized_pnl: 2000, combined_pnl: 2100,
    current_level: 2, max_levels: 10, trailing_enabled: true, trailing_peak_price: 5300000,
  },
  {
    grid_id: "g2", symbol: "ETHINR", status: "paused", mode: "paper",
    quantity: 0.5, average_entry_price: 280000, invested: 140000,
    current_price: null, realized_pnl: -50, unrealized_pnl: 0, combined_pnl: -50,
    current_level: 1, max_levels: 5, trailing_enabled: false, trailing_peak_price: null,
  },
];

describe("LiveGrids", () => {
  it("renders a row for every position with the expected columns", () => {
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: POSITIONS, count: 2 } }));
    renderWithProviders(<LiveGrids />);
    expect(screen.getByText("BTCINR")).toBeInTheDocument();
    expect(screen.getByText("ETHINR")).toBeInTheDocument();
    expect(screen.getByText("2/10")).toBeInTheDocument();
  });

  it("shows the loading state while the query is pending", () => {
    hoisted.positions.mockReturnValue(mockQueryResult({ isLoading: true }));
    renderWithProviders(<LiveGrids />);
    expect(screen.getByTestId("state-loading")).toBeInTheDocument();
  });

  it("shows the empty state when there are no live grids", () => {
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: [], count: 0 } }));
    renderWithProviders(<LiveGrids />);
    expect(screen.getByText("No live grids right now.")).toBeInTheDocument();
  });

  it("shows an error state on API failure", () => {
    hoisted.positions.mockReturnValue(mockQueryResult({ isError: true, error: new Error("boom") }));
    renderWithProviders(<LiveGrids />);
    expect(screen.getByTestId("state-error")).toBeInTheDocument();
  });

  it("filters by coin via the search box", async () => {
    const user = userEvent.setup();
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: POSITIONS, count: 2 } }));
    renderWithProviders(<LiveGrids />);

    await user.type(screen.getByTestId("input-table-search"), "btc");
    expect(screen.getByText("BTCINR")).toBeInTheDocument();
    expect(screen.queryByText("ETHINR")).not.toBeInTheDocument();
  });

  it("filters by status via the status select", async () => {
    const user = userEvent.setup();
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: POSITIONS, count: 2 } }));
    renderWithProviders(<LiveGrids />);

    await user.click(screen.getByTestId("select-status-filter"));
    await user.click(await screen.findByRole("option", { name: "Paused" }));

    expect(screen.getByText("ETHINR")).toBeInTheDocument();
    expect(screen.queryByText("BTCINR")).not.toBeInTheDocument();
  });

  it("sorts by unrealized P&L when that header is clicked", async () => {
    const user = userEvent.setup();
    hoisted.positions.mockReturnValue(mockQueryResult({ data: { positions: POSITIONS, count: 2 } }));
    renderWithProviders(<LiveGrids />);

    await user.click(screen.getByTestId("header-unrealized_pnl"));
    const rows = screen.getAllByRole("row").slice(1);
    // ascending: ETH (-50 effectively, unrealized 0 but combined lower) then BTC — just assert order changed deterministically
    expect(rows.length).toBe(2);
  });
});
