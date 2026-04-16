/**
 * NoctusAI Seed Framework — Frontend
 *
 * The seed is the spine of every product frontend. All products inherit
 * their structural infrastructure from here:
 *
 *   - createProductApp()    → Full App component (routing, auth, providers)
 *   - createProductLayout() → Layout component (sidebar, header, nav)
 *
 * Products just provide their config (name, icon, pages, nav groups).
 * The seed handles everything structural.
 */
export { createProductApp } from './app';
export { createProductLayout } from './layout';
export { createViteConfig } from './vite';
export type { ProductAppConfig, ProductRoute } from './app';
export type { ProductLayoutConfig } from './layout';
