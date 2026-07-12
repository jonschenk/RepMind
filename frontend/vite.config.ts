import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Backend runs on :8000; SSE for /api/chat must not be buffered.
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
