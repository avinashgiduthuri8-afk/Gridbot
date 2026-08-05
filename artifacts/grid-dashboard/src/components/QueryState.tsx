import { AlertTriangle, Inbox } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

interface QueryStateProps<T> {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  data: T | undefined;
  onRetry?: () => void;
  /** Returns true when `data` should be treated as "empty" (e.g. an empty array). */
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  loadingRows?: number;
  children: (data: T) => React.ReactNode;
}

function errorMessage(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return String((error as { message: unknown }).message);
  }
  return "Something went wrong while loading this data.";
}

/**
 * Wraps a react-query result and renders exactly one of: loading skeleton,
 * error state (with retry), empty state, or the real content — used by
 * every page instead of each one re-implementing this branching.
 */
export function QueryState<T>({
  isLoading,
  isError,
  error,
  data,
  onRetry,
  isEmpty,
  emptyMessage = "Nothing here yet.",
  loadingRows = 4,
  children,
}: QueryStateProps<T>) {
  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="state-loading">
        {Array.from({ length: loadingRows }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed p-10 text-center"
        data-testid="state-error"
      >
        <AlertTriangle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">{errorMessage(error)}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} data-testid="button-retry">
            Try again
          </Button>
        )}
      </div>
    );
  }

  if (data === undefined || (isEmpty && isEmpty(data))) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed p-10 text-center"
        data-testid="state-empty"
      >
        <Inbox className="h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  return <>{children(data)}</>;
}
