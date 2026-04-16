/**
 * NoctusAI Seed Framework — Frontend
 *
 * The seed is the spine of every product frontend. All products inherit
 * their structural infrastructure from here:
 *
 *   - createProductApp()    → Full App component (routing, auth, providers)
 *   - createProductLayout() → Layout component (sidebar, header, nav)
 *   - createViteConfig()    → Vite build config (imported separately via path)
 *
 * Products just provide their config (name, icon, pages, nav groups).
 * The seed handles everything structural.
 */
export { createProductApp } from './app';
export { createProductLayout } from './layout';
export type { ProductAppConfig, ProductRoute, RoleRouteConfig } from './app';
export type { ProductLayoutConfig, LayoutEnrichment } from './layout';

// createViteConfig lives at seed/frontend/framework/vite.config.factory.ts
// It's config-time code (not app-time), so it's NOT in src/ and NOT bundled.
// Products import it directly: import { createViteConfig } from "../../../seed/frontend/framework/vite.config.factory";
