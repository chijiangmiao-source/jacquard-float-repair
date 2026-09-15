/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发态把 /api 与 /health 代理到 FastAPI（默认 8000，可用 API_PORT 覆盖）。
const apiTarget = `http://localhost:${process.env.API_PORT ?? "8000"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: Number(process.env.WEB_PORT ?? 5173),
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
});
