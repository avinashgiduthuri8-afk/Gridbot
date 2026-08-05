import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";

// The generated API client (see @workspace/api-client-react) defaults to
// relative "/api/..." requests. In dev, vite.config.ts proxies /api to the
// FastAPI backend (grid-trading-bot/dashboard/app.py, default
// http://localhost:8000). In production, serve this build from the same
// origin as the API (or reverse-proxy /api to it) — no setBaseUrl() call
// is needed either way.

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Trading data changes frequently but this is a read-only dashboard,
      // not a live ticker — a short polling interval keeps it reasonably
      // fresh without hammering the API.
      refetchInterval: 15_000,
      retry: 1,
      staleTime: 5_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster />
    </QueryClientProvider>
  </StrictMode>,
);
