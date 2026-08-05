import { useGetSettingsApiSettingsGet } from "@workspace/api-client-react";
import { QueryState } from "@/components/QueryState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { formatCurrency } from "@/lib/format";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const query = useGetSettingsApiSettingsGet();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      <p className="text-sm text-muted-foreground">
        Read-only in this phase — operational and risk configuration only. No secrets are ever displayed here.
      </p>

      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        data={query.data}
        onRetry={() => query.refetch()}
      >
        {(s) => (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">Risk Management</CardTitle></CardHeader>
              <CardContent className="divide-y">
                <Row label="Max total capital" value={formatCurrency(s.risk.max_total_capital)} />
                <Row label="Max capital per coin" value={formatCurrency(s.risk.max_capital_per_coin)} />
                <Row label="Max simultaneous grids" value={s.risk.max_simultaneous_grids} />
                <Row label="Min wallet balance" value={formatCurrency(s.risk.min_wallet_balance)} />
                <Row label="Daily loss limit" value={formatCurrency(s.risk.daily_loss_limit)} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Polling Intervals</CardTitle></CardHeader>
              <CardContent className="divide-y">
                <Row label="Order poll interval" value={`${s.order_poll_interval_seconds}s`} />
                <Row label="Price poll interval" value={`${s.price_poll_interval_seconds}s`} />
                <Row label="Daily summary interval" value={`${s.daily_summary_interval_seconds}s`} />
                <Row
                  label="Monitor interval"
                  value={s.monitor_interval_seconds !== null && s.monitor_interval_seconds !== undefined ? `${s.monitor_interval_seconds}s` : "—"}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Feature Flags</CardTitle></CardHeader>
              <CardContent className="divide-y">
                <Row
                  label="Emergency stop"
                  value={<Badge variant={s.emergency_stop_active ? "destructive" : "default"}>{s.emergency_stop_active ? "ACTIVE" : "Inactive"}</Badge>}
                />
                <Row label="Google Drive backup" value={<Badge variant={s.backup_enabled ? "default" : "outline"}>{s.backup_enabled ? "Enabled" : "Disabled"}</Badge>} />
                <Row label="CoinDCX webhook" value={<Badge variant={s.webhook_enabled ? "default" : "outline"}>{s.webhook_enabled ? "Enabled" : "Disabled"}</Badge>} />
              </CardContent>
            </Card>

            {s.grid_defaults && (
              <Card>
                <CardHeader><CardTitle className="text-base">Quick Default Grid</CardTitle></CardHeader>
                <CardContent className="divide-y">
                  {Object.entries(s.grid_defaults).map(([key, value]) => (
                    <Row key={key} label={key.replace(/_/g, " ")} value={String(value)} />
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </QueryState>
      <Separator />
    </div>
  );
}
