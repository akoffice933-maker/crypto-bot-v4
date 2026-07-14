import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/webhook": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/portfolio": "http://localhost:8000",
      "/analytics": "http://localhost:8000",
      "/metrics": "http://localhost:8000",
      "/learning": "http://localhost:8000",
      "/config": "http://localhost:8000",
      "/execution": "http://localhost:8000",
    },
  },
});
