import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The SPA talks to the backend over a JSON API. In dev we proxy /api -> FastAPI (the correct,
// recompute-gated backend); the same VITE_API_BASE swaps to NestJS later without UI changes.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": { target: process.env.VITE_API_BASE || "http://localhost:8000", changeOrigin: true },
    },
  },
});
