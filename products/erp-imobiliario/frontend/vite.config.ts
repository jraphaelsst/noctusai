import { createViteConfig } from "../../../seed/frontend/framework/vite.config.factory";
import { componentTagger } from "lovable-tagger";
import { VitePWA } from "vite-plugin-pwa";

export default createViteConfig({
  port: 8080,
  extend: (config) => {
    // Keep ERP-specific plugins
    config.plugins = [
      ...(config.plugins || []),
      componentTagger(),
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["favicon.ico", "apple-touch-icon.png", "mask-icon.svg"],
        manifest: {
          name: "Corretor Goal Hub",
          short_name: "GoalHub",
          description: "ERP para corretores de imóveis com sistema de matching",
          theme_color: "#1a1a2e",
          background_color: "#ffffff",
          display: "standalone",
          scope: "/",
          start_url: "/",
          icons: [
            {
              src: "pwa-192x192.png",
              sizes: "192x192",
              type: "image/png",
            },
            {
              src: "pwa-512x512.png",
              sizes: "512x512",
              type: "image/png",
            },
            {
              src: "pwa-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "any maskable",
            },
          ],
        },
        workbox: {
          globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/.*\.supabase\.co\/rest\/v1\/.*/i,
              handler: "NetworkFirst",
              options: {
                cacheName: "supabase-api-cache",
                expiration: {
                  maxEntries: 50,
                  maxAgeSeconds: 60 * 5, // 5 minutes
                },
              },
            },
          ],
        },
      }),
    ].filter(Boolean);

    // Keep ERP test config
    (config as any).test = {
      globals: true,
      environment: "jsdom",
      setupFiles: [],
    };

    return config;
  },
});
