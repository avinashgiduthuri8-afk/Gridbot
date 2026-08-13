import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
    },
  },
  test: {
    // Keep discovery within the dashboard package. Without this, Vitest
    // walks the bot's Python cache directories when run from the workspace.
    dir: path.resolve(import.meta.dirname, "src"),
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: false,
  },
});
