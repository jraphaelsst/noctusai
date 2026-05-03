/**
 * NoctusAI Seed Framework — Frontend
 *
 * The seed is the spine of every product frontend. Products import
 * from here and provide only their domain config.
 *
 *   - createProductInfra()  → All boilerplate (supabase, auth, api, notifications)
 *   - createProductApp()    → Full App component (routing, auth, providers)
 *   - createProductLayout() → Layout component (sidebar, header, nav)
 *   - createViteConfig()    → Vite build config (imported separately via path)
 */
export { createProductInfra } from './infra';
export { createProductApp } from './app';
export { createProductLayout, DEFAULT_AI_BADGES } from './layout';
export type { ProductAppConfig, ProductRoute, RoleRouteConfig, CustomAuthProvider } from './app';
export type { ProductLayoutConfig, LayoutEnrichment } from './layout';

// Seed-mounted pages — auto-routed by createProductApp, exported here so
// products that want to override the default route target can re-mount
// with their own wrapper.
export { ConsentSettingsPage } from './pages/ConsentSettingsPage';

// createViteConfig lives at seed/framework/frontend/vite.config.factory.ts
// Config-time code, imported by path: import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";
