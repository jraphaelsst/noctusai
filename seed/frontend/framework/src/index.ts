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
export { createProductLayout } from './layout';
export type { ProductAppConfig, ProductRoute, RoleRouteConfig } from './app';
export type { ProductLayoutConfig, LayoutEnrichment } from './layout';

// createViteConfig lives at seed/frontend/framework/vite.config.factory.ts
// Config-time code, imported by path: import { createViteConfig } from "../../../seed/frontend/framework/vite.config.factory";
