import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useListPositionsApiPositionsGet, type PositionResponse } from "@workspace/api-client-react";
import { DataTable } from "@/components/DataTable";
import { QueryState } from "@/components/QueryState";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatCurrency, formatQuantity, formatSignedCurrency, pnlColorClass, statusVariant } from "@/lib/format";

const STATUS_FILTERS = ["all", "active", "paused"] as const;

export default function LiveGrids() {
  const query = useListPositionsApiPositionsGet();
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");

  const columns = useMemo<ColumnDef<PositionResponse>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Coin",
        cell: ({ row }) => <span className="font-medium">{row.original.symbol}</span>,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <Badge variant={statusVariant(row.original.status)}>{row.original.status.toUpperCase()}</Badge>
        ),
      },
      {
        id: "grid_level",
        accessorFn: (row) => row.current_level,
        header: "Grid Level",
        cell: ({ row }) => `${row.original.current_level}/${row.original.max_levels}`,
      },
      {
        accessorKey: "average_entry_price",
        header: "Average Price",
        cell: ({ row }) => formatCurrency(row.original.average_entry_price),
      },
      {
        accessorKey: "current_price",
        header: "Current Price",
        cell: ({ row }) => formatCurrency(row.original.current_price),
      },
      {
        accessorKey: "quantity",
        header: "Quantity",
        cell: ({ row }) => formatQuantity(row.original.quantity),
      },
      {
        accessorKey: "invested",
        header: "Investment",
        cell: ({ row }) => formatCurrency(row.original.invested),
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
        id: "trailing_status",
        accessorFn: (row) => (row.trailing_enabled ? "on" : "off"),
        header: "Trailing Status",
        cell: ({ row }) =>
          row.original.trailing_enabled ? (
            <Badge variant="secondary">
              Active{row.original.trailing_peak_price ? ` @ ${formatCurrency(row.original.trailing_peak_price)}` : ""}
            </Badge>
          ) : (
            <span className="text-muted-foreground">Off</span>
          ),
      },
    ],
    [],
  );

  const filtered = useMemo(() => {
    if (!query.data) return [];
    if (statusFilter === "all") return query.data.positions;
    return query.data.positions.filter((p) => p.status === statusFilter);
  }, [query.data, statusFilter]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Live Grids</h1>
      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        data={query.data}
        onRetry={() => query.refetch()}
        isEmpty={(d) => d.positions.length === 0}
        emptyMessage="No live grids right now."
      >
        {() => (
          <DataTable
            columns={columns}
            data={filtered}
            searchPlaceholder="Search by coin..."
            globalFilterFn={(row, search) => row.symbol.toLowerCase().includes(search.toLowerCase())}
            emptyMessage="No grids match your filters."
            toolbar={
              <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
                <SelectTrigger className="w-40" data-testid="select-status-filter">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_FILTERS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s === "all" ? "All statuses" : s[0].toUpperCase() + s.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            }
          />
        )}
      </QueryState>
    </div>
  );
}
