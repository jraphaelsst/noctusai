import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  server: { host: "0.0.0.0", port: {{FRONTEND_PORT}} },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@noctusai/shared": path.resolve(__dirname, "../../../shared/frontend/src"),
      // Ensure shared design-system deps resolve from this project's node_modules
      "lucide-react": path.resolve(__dirname, "node_modules/lucide-react"),
      "@radix-ui/react-hover-card": path.resolve(__dirname, "node_modules/@radix-ui/react-hover-card"),
      "@radix-ui/react-collapsible": path.resolve(__dirname, "node_modules/@radix-ui/react-collapsible"),
    },
    dedupe: ["react", "react-dom", "zustand", "@tanstack/react-query"],
  },
});
