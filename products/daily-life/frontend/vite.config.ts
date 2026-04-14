import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 8110,
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@noctusai/shared": path.resolve(__dirname, "../../../shared/frontend/src"),
      // Shared design-system imports these packages — resolve from this project
      "lucide-react": path.resolve(__dirname, "node_modules/lucide-react"),
      "@radix-ui/react-hover-card": path.resolve(__dirname, "node_modules/@radix-ui/react-hover-card"),
      "@radix-ui/react-collapsible": path.resolve(__dirname, "node_modules/@radix-ui/react-collapsible"),
    },
    dedupe: ["react", "react-dom", "zustand", "@tanstack/react-query"],
  },
});
