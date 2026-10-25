import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api and /ws to the local FastAPI backend.
// In production the build output (dist/) is served by FastAPI StaticFiles,
// so the app uses relative URLs and these proxies are dev-only.
//
// 后台端口：VITE_BACKEND_PORT 或 FUNASR_SUBTITLE_PORT，默认 8765。
// 页面端口：VITE_PORT，默认 5173。VITE_STRICT_PORT=1 时被占用就失败，不自动换端口。
// vite.config.ts 不带 @types/node，用 globalThis 读环境变量，避免把 Node 类型加进依赖。
const env = ((globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env) ?? {};
const backendPort = env.VITE_BACKEND_PORT || env.FUNASR_SUBTITLE_PORT || "8765";
const backendHost = env.VITE_BACKEND_HOST || env.FUNASR_SUBTITLE_HOST || "127.0.0.1";
const BACKEND = `http://${backendHost}:${backendPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(env.VITE_PORT || 5173),
    strictPort: env.VITE_STRICT_PORT === "1",
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
      },
      "/ws": {
        target: BACKEND,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
