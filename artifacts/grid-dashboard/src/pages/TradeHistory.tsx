import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useListTradeHistoryApiTradeHistoryGet, type TradeResponse } from "@workspace/api-client-react";
import { DataTable } from "@/components/DataTable";
import { QueryState } from "@/components/QueryState";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatDateTime, formatQuantity, formatSignedCurrency, pnlColorClass } from "@/lib/format";

export default function TradeHistory() {
  const query = useListTradeHistoryApiTradeHistoryGet({ limit: 500 });

  const columns = useMemo<ColumnDef<TradeResponse>[]>(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      {
        accessorKey: "side",
        header: "Buy / Sell",
        cell: ({ row }) => (
          <Badge variant={row.original.side === "buy" ? "default" : "secondary"}>
            {row.original.side.toUpperCase()}
          </Badge>
        ),
      },
      { accessorKey: "price", header: "Price", cell: ({ row }) => formatCurrency(row.original.price) },
      { accessorKey: "quantity", header: "Quantity", cell: ({ row }) => formatQuantity(row.original.quantity) },
      {
        accessorKey: "pnl",
        header: "Profit",
        cell: ({ row }) => (
          <span className={pnlColorClass(row.original.pnl)}>{formatSignedCurrency(row.original.pnl)}</span>
        ),
      },
      { accessorKey: "fee", header: "Fees", cell: ({ row }) => formatCurrency(row.original.fee) },
      {
        accessorKey: "executed_at",
        header: "Time",
        cell: ({ row }) => formatDateTime(row.original.executed_at),
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Trade History</h1>
      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        data={query.data}
        onRetry={() => query.refetch()}
        isEmpty={(d) => d.trades.length === 0}
        emptyMessage="No completed trades yet."
      >
        {(data) => (
          <DataTable
            columns={columns}
            data={data.trades}
            searchPlaceholder="Search by symbol..."
            globalFilterFn={(row, search) => row.symbol.toLowerCase().includes(search.toLowerCase())}
          />
        )}
      </QueryState>
    </div>
  );
}
