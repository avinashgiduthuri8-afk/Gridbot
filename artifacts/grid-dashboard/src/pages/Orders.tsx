import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useListOrdersApiOrdersGet, type OrderResponse } from "@workspace/api-client-react";
import { DataTable } from "@/components/DataTable";
import { QueryState } from "@/components/QueryState";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatCurrency, formatDateTime, formatQuantity } from "@/lib/format";

const STATUS_OPTIONS = ["all", "open", "filled", "partially_filled", "failed", "cancelled", "unknown"];

export default function Orders() {
  const query = useListOrdersApiOrdersGet({ limit: 500 });
  const [symbolFilter, setSymbolFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("");

  const columns = useMemo<ColumnDef<OrderResponse>[]>(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      {
        accessorKey: "side",
        header: "Side",
        cell: ({ row }) => (
          <Badge variant={row.original.side === "buy" ? "default" : "secondary"}>
            {row.original.side.toUpperCase()}
          </Badge>
        ),
      },
      { accessorKey: "order_type", header: "Type" },
      { accessorKey: "price", header: "Price", cell: ({ row }) => formatCurrency(row.original.price) },
      { accessorKey: "quantity", header: "Quantity", cell: ({ row }) => formatQuantity(row.original.quantity) },
      {
        accessorKey: "filled_quantity",
        header: "Filled Qty",
        cell: ({ row }) => formatQuantity(row.original.filled_quantity),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <Badge variant="outline">{row.original.status}</Badge>,
      },
      { accessorKey: "fee", header: "Fee", cell: ({ row }) => formatCurrency(row.original.fee) },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }) => formatDateTime(row.original.created_at),
      },
    ],
    [],
  );

  const filtered = useMemo(() => {
    if (!query.data) return [];
    return query.data.orders.filter((o) => {
      if (symbolFilter && !o.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) return false;
      if (statusFilter !== "all" && o.status !== statusFilter) return false;
      if (dateFilter && !o.created_at.startsWith(dateFilter)) return false;
      return true;
    });
  }, [query.data, symbolFilter, statusFilter, dateFilter]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Orders</h1>
      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        data={query.data}
        onRetry={() => query.refetch()}
        isEmpty={(d) => d.orders.length === 0}
        emptyMessage="No orders recorded yet."
      >
        {() => (
          <DataTable
            columns={columns}
            data={filtered}
            searchPlaceholder="Search all columns..."
            emptyMessage="No orders match your filters."
            toolbar={
              <div className="flex flex-wrap gap-2">
                <Input
                  value={symbolFilter}
                  onChange={(e) => setSymbolFilter(e.target.value)}
                  placeholder="Filter by symbol"
                  className="w-40"
                  data-testid="input-symbol-filter"
                />
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-40" data-testid="select-status-filter">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s === "all" ? "All statuses" : s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  type="date"
                  value={dateFilter}
                  onChange={(e) => setDateFilter(e.target.value)}
                  className="w-40"
                  data-testid="input-date-filter"
                />
              </div>
            }
          />
        )}
      </QueryState>
    </div>
  );
}
