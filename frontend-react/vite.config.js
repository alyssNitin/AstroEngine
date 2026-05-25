/**
 * vite.config.js — NarayanAstroReader Vite configuration
 *
 * Dev server proxies /api/* and /auth/* to FastAPI on :8000 so the
 * React dev-server never has CORS issues.  Production build writes to
 * dist/ which FastAPI mounts as a StaticFiles directory.
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      // Allows imports like: import Button from "@/components/ui/Button"
      "@": path.resolve(__dirname, "./src"),
    },
  },

  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to the FastAPI backend during development
      "/auth": { target: "http://localhost:8000", changeOrigin: true },
      "/kundli": { target: "http://localhost:8000", changeOrigin: true },
      "/wallet": { target: "http://localhost:8000", changeOrigin: true },
      "/payment": { target: "http://localhost:8000", changeOrigin: true },
      "/admin": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      "/share": { target: "http://localhost:8000", changeOrigin: true },
    },
  },

  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Source maps in production help debugging without exposing source
    sourcemap: false,
    rollupOptions: {
      output: {
        // Split vendor chunk for better caching
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
});
