/**
 * Pure display-formatting helpers. Every number these functions receive
 * comes directly from an API response — nothing here computes P&L, ROI,
 * or any other trading figure. That logic lives entirely in the backend
 * (trading/portfolio_metrics.py, replay/report.py) per the project's
 * "reuse, don't duplicate" rule.
 */

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "-" : "";
  return `${sign}₹${Math.abs(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatSignedCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}₹${Math.abs(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPercent(value: number | null | undefined, options?: { signed?: boolean }): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = options?.signed && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: 8 });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function pnlColorClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "text-muted-foreground";
  return value > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400";
}

export function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "active":
      return "default";
    case "paused":
      return "secondary";
    case "stopped":
      return "destructive";
    case "completed":
      return "outline";
    default:
      return "outline";
  }
}

/**
 * ROI% for a position. The backend doesn't expose a pre-computed ROI field
 * on PositionResponse (only unrealized_pnl and invested), and the ratio
 * here is the exact same one-line formula as
 * trading/portfolio_metrics.pnl_pct() (pnl / invested * 100) — this is the
 * one deliberate, disclosed exception to "P&L comes from the backend" in
 * this dashboard: a trivial display ratio of two already-backend-computed
 * numbers, not a re-derivation of P&L itself (which would require price
 * arithmetic the frontend never performs). See Phase 4 delivery notes.
 */
export function computeRoiPct(unrealizedPnl: number, invested: number): number {
  if (invested <= 0) return 0;
  return (unrealizedPnl / invested) * 100;
}
