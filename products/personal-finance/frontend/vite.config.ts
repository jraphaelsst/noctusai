import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 8090,
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@noctusai/shared": path.resolve(__dirname, "../../../shared/frontend/src"),
    },
    dedupe: ["react", "react-dom", "zustand", "@tanstack/react-query"],
  },
});
