import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/DataTable";
import { renderWithProviders } from "@/test/test-utils";

interface Row {
  name: string;
  amount: number;
}

const columns: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "amount", header: "Amount" },
];

const data: Row[] = [
  { name: "Bravo", amount: 20 },
  { name: "Alpha", amount: 30 },
  { name: "Charlie", amount: 10 },
];

function bodyRowTexts() {
  const rows = screen.getAllByRole("row").slice(1); // skip header row
  return rows.map((r) => within(r).getAllByRole("cell")[0].textContent);
}

describe("DataTable", () => {
  it("renders every row by default", () => {
    renderWithProviders(<DataTable columns={columns} data={data} />);
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Charlie")).toBeInTheDocument();
  });

  it("shows the empty message when data is empty", () => {
    renderWithProviders(<DataTable columns={columns} data={[]} emptyMessage="No rows here" />);
    expect(screen.getByText("No rows here")).toBeInTheDocument();
  });

  it("sorts rows ascending/descending when a sortable header is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DataTable columns={columns} data={data} />);

    const nameHeader = screen.getByTestId("header-name");
    await user.click(nameHeader);
    expect(bodyRowTexts()).toEqual(["Alpha", "Bravo", "Charlie"]);

    await user.click(nameHeader);
    expect(bodyRowTexts()).toEqual(["Charlie", "Bravo", "Alpha"]);
  });

  it("filters rows via the search box", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DataTable columns={columns} data={data} searchPlaceholder="Search..." />);

    await user.type(screen.getByTestId("input-table-search"), "alpha");
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Bravo")).not.toBeInTheDocument();
    expect(screen.queryByText("Charlie")).not.toBeInTheDocument();
  });

  it("supports a custom globalFilterFn", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <DataTable
        columns={columns}
        data={data}
        globalFilterFn={(row, search) => row.amount > Number(search)}
      />,
    );
    await user.type(screen.getByTestId("input-table-search"), "15");
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Charlie")).not.toBeInTheDocument();
  });
});
