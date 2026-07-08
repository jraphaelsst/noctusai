import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";
import { componentTagger } from "lovable-tagger";
import { VitePWA } from "vite-plugin-pwa";

// ── Service worker: RETIREMENT (self-destroying) ────────────────────────────
// erp-imobiliario was the ONLY product that shipped a PWA service worker
// (inherited from its original "Corretor Goal Hub" / Lovable scaffold). For an
// always-online ERP the offline precache buys ~nothing, but it caused a real
// production incident: a service worker serves the app shell + JS from Cache
// Storage, BYPASSING all HTTP cache headers — so the seed's `no-cache` on
// index.html could not reach clients, and users (e.g. Marina, 2026-07-08) were
// pinned to an OLD precached bundle: stale labels ("Certificados" vs the
// current "Certidões") + an already-fixed form-freeze bug. See
// `KB § PATTERNS/frontend/spa-cache-and-service-worker.md`.
//
// `selfDestroying: true` builds a sw.js that, on a client's next visit,
// unregisters the existing service worker and deletes its caches — so every
// stuck client heals automatically with no manual steps. Keep this flag for at
// least one full release cycle so all clients pick up the self-destroying
// worker; once field telemetry shows no active `nai`/workbox SW remains, the
// VitePWA import can be removed entirely.
export default createViteConfig({
  port: 8080,
  extend: (config) => {
    config.plugins = [
      ...(config.plugins || []),
      componentTagger(),
      VitePWA({
        selfDestroying: true,
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
