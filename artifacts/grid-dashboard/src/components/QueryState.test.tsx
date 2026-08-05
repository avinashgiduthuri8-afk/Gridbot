import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { QueryState } from "@/components/QueryState";
import { renderWithProviders } from "@/test/test-utils";

describe("QueryState", () => {
  it("renders the loading skeleton while isLoading is true", () => {
    renderWithProviders(
      <QueryState isLoading isError={false} data={undefined}>
        {() => <div>content</div>}
      </QueryState>,
    );
    expect(screen.getByTestId("state-loading")).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("renders the error state with a retry button on API failure", () => {
    const onRetry = vi.fn();
    renderWithProviders(
      <QueryState isLoading={false} isError error={new Error("Network down")} data={undefined} onRetry={onRetry}>
        {() => <div>content</div>}
      </QueryState>,
    );
    expect(screen.getByTestId("state-error")).toBeInTheDocument();
    expect(screen.getByText("Network down")).toBeInTheDocument();
    screen.getByTestId("button-retry").click();
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders the empty state when isEmpty(data) returns true", () => {
    renderWithProviders(
      <QueryState isLoading={false} isError={false} data={[]} isEmpty={(d: unknown[]) => d.length === 0} emptyMessage="Nothing to show">
        {() => <div>content</div>}
      </QueryState>,
    );
    expect(screen.getByTestId("state-empty")).toBeInTheDocument();
    expect(screen.getByText("Nothing to show")).toBeInTheDocument();
  });

  it("renders children with data on success", () => {
    renderWithProviders(
      <QueryState isLoading={false} isError={false} data={{ value: 42 }}>
        {(data) => <div>value is {data.value}</div>}
      </QueryState>,
    );
    expect(screen.getByText("value is 42")).toBeInTheDocument();
  });
});
