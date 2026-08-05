import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useListPositionsApiPositionsGet, type PositionResponse } from "@workspace/api-client-react";
import { DataTable } from "@/components/DataTable";
import { QueryState } from "@/components/QueryState";
import { computeRoiPct, formatCurrency, formatPercent, formatQuantity, formatSignedCurrency, pnlColorClass } from "@/lib/format";

export default function Positions() {
  const query = useListPositionsApiPositionsGet();

  const columns = useMemo<ColumnDef<PositionResponse>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Coin",
        cell: ({ row }) => <span className="font-medium">{row.original.symbol}</span>,
      },
      {
        accessorKey: "quantity",
        header: "Quantity",
        cell: ({ row }) => formatQuantity(row.original.quantity),
      },
      {
        accessorKey: "average_entry_price",
        header: "Average Entry",
        cell: ({ row }) => formatCurrency(row.original.average_entry_price),
      },
      {
        accessorKey: "current_price",
        header: "Current Price",
        cell: ({ row }) => formatCurrency(row.original.current_price),
      },
      {
        accessorKey: "unrealized_pnl",
        header: "Unrealized P&L",
        cell: ({ row }) => (
          <span className={pnlColorClass(row.original.unrealized_pnl)}>
            {formatSignedCurrency(row.original.unrealized_pnl)}
          </span>
        ),
      },
      {
        id: "roi",
        accessorFn: (row) => computeRoiPct(row.unrealized_pnl, row.invested),
        header: "ROI",
        cell: ({ row }) => {
          const roi = computeRoiPct(row.original.unrealized_pnl, row.original.invested);
          return <span className={pnlColorClass(roi)}>{formatPercent(roi, { signed: true })}</span>;
        },
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Active Positions</h1>
      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        data={query.data}
        onRetry={() => query.refetch()}
        isEmpty={(d) => d.positions.length === 0}
        emptyMessage="No open positions."
      >
        {(data) => (
          <DataTable
            columns={columns}
            data={data.positions}
            searchPlaceholder="Search by coin..."
            globalFilterFn={(row, search) => row.symbol.toLowerCase().includes(search.toLowerCase())}
          />
        )}
      </QueryState>
    </div>
  );
}
