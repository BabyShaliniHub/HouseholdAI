import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on the host; in Docker nginx proxies /api to the backend service.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": process.env.VITE_API_TARGET ?? "http://localhost:8000" } },
});
