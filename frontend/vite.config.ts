import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Production build outputs to /static/ so Django's collectstatic picks it up.
  // Dev server uses "/" so Vite assets don't get proxied back to Django.
  base: command === "build" ? "/static/" : "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to Django dev server
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/fhir": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/admin": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/static": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/healthz": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          mantine: ["@mantine/core", "@mantine/hooks"],
          mantineExtra: [
            "@mantine/form",
            "@mantine/notifications",
            "@mantine/modals",
            "@mantine/dates",
          ],
          query: ["@tanstack/react-query", "axios"],
          charts: ["recharts", "@mantine/charts"],
          icons: ["@tabler/icons-react"],
        },
      },
    },
  },
}));
