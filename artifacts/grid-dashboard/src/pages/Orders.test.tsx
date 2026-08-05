import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, mockQueryResult } from "@/test/test-utils";
import Orders from "@/pages/Orders";

const hoisted = vi.hoisted(() => ({ orders: vi.fn() }));

vi.mock("@workspace/api-client-react", () => ({
  useListOrdersApiOrdersGet: hoisted.orders,
}));

const ORDERS = [
  {
    order_id: "o1", grid_id: "g1", exchange_order_id: "e1", symbol: "BTCINR", side: "buy",
    order_type: "market_order", price: 5000000, quantity: 0.01, filled_quantity: 0.01,
    filled_price: 5000000, status: "filled", fee: 5, reconciliation_status: "not_needed",
    created_at: "2026-01-15T10:00:00Z", updated_at: "2026-01-15T10:00:01Z",
  },
  {
    order_id: "o2", grid_id: "g2", exchange_order_id: "e2", symbol: "ETHINR", side: "sell",
    order_type: "market_order", price: 280000, quantity: 0.5, filled_quantity: 0,
    filled_price: 0, status: "open", fee: 0, reconciliation_status: "not_needed",
    created_at: "2026-02-20T09:00:00Z", updated_at: "2026-02-20T09:00:00Z",
  },
];

describe("Orders", () => {
  it("renders every order", () => {
    hoisted.orders.mockReturnValue(mockQueryResult({ data: { orders: ORDERS, count: 2 } }));
    renderWithProviders(<Orders />);
    expect(screen.getByText("BTCINR")).toBeInTheDocument();
    expect(screen.getByText("ETHINR")).toBeInTheDocument();
  });

  it("shows the empty state with no orders", () => {
    hoisted.orders.mockReturnValue(mockQueryResult({ data: { orders: [], count: 0 } }));
    renderWithProviders(<Orders />);
    expect(screen.getByText("No orders recorded yet.")).toBeInTheDocument();
  });

  it("shows an error state on API failure", () => {
    hoisted.orders.mockReturnValue(mockQueryResult({ isError: true, error: new Error("network error") }));
    renderWithProviders(<Orders />);
    expect(screen.getByTestId("state-error")).toBeInTheDocument();
    expect(screen.getByText("network error")).toBeInTheDocument();
  });

  it("filters by symbol", async () => {
    const user = userEvent.setup();
    hoisted.orders.mockReturnValue(mockQueryResult({ data: { orders: ORDERS, count: 2 } }));
    renderWithProviders(<Orders />);

    await user.type(screen.getByTestId("input-symbol-filter"), "eth");
    expect(screen.getByText("ETHINR")).toBeInTheDocument();
    expect(screen.queryByText("BTCINR")).not.toBeInTheDocument();
  });

  it("filters by status", async () => {
    const user = userEvent.setup();
    hoisted.orders.mockReturnValue(mockQueryResult({ data: { orders: ORDERS, count: 2 } }));
    renderWithProviders(<Orders />);

    await user.click(screen.getByTestId("select-status-filter"));
    await user.click(await screen.findByRole("option", { name: "open" }));

    expect(screen.getByText("ETHINR")).toBeInTheDocument();
    expect(screen.queryByText("BTCINR")).not.toBeInTheDocument();
  });

  it("filters by date", async () => {
    const user = userEvent.setup();
    hoisted.orders.mockReturnValue(mockQueryResult({ data: { orders: ORDERS, count: 2 } }));
    renderWithProviders(<Orders />);

    const dateInput = screen.getByTestId("input-date-filter");
    await user.type(dateInput, "2026-01-15");
    expect(screen.getByText("BTCINR")).toBeInTheDocument();
    expect(screen.queryByText("ETHINR")).not.toBeInTheDocument();
  });
});
