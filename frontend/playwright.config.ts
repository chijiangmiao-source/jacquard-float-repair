import { defineConfig } from "@playwright/test";

const webPort = Number(process.env.WEB_PORT ?? 8080);
const apiPort = Number(process.env.API_PORT ?? 8000);
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${webPort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL,
    actionTimeout: 30_000,
  },
  // 容器内（docker compose verify）由 E2E_BASE_URL 指向已启动的 web/api；
  // 本地运行时自动拉起后端与前端两个服务。
  webServer: process.env.E2E_BASE_URL
    ? []
    : [
        {
          command: `uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
          cwd: "../backend",
          url: `http://127.0.0.1:${apiPort}/health`,
          reuseExistingServer: true,
          timeout: 60_000,
        },
        {
          command: `npm run build && npm run preview -- --port ${webPort} --strictPort`,
          url: `http://127.0.0.1:${webPort}`,
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
});
