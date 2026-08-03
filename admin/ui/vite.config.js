import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // dev-mode only; in the container nginx does this proxying (see nginx.conf)
    proxy: {
      "/api": {
        target: process.env.STUDIO_API_URL || "http://localhost:9000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
