import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api goes to the Smart Flow API (smartflow api): local by default, or SMARTFLOW_API=http://<host>:8787.
// In production the page calls VITE_CITY_API (the API's public URL) instead.
const api = { "/api": { target: process.env.SMARTFLOW_API ?? "http://127.0.0.1:8787", changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  build: { target: "es2022", sourcemap: false },
  // the strategy registry and its figures live in ../config (shared with the agents' host)
  server: { port: 5173, proxy: api, fs: { allow: [".."] } },
  preview: { proxy: api },
});
