import { test as base, type Page } from '@playwright/test';
import { mockSession, mockSupabaseUser, mockProfile } from './mock-data';
import { jsonResponse } from './helpers';

/**
 * Seeds the Supabase auth session in localStorage and intercepts
 * auth-related endpoints so the ERP app believes the user is authenticated.
 *
 * IMPORTANT: Only intercepts /auth/v1/* endpoints here.
 * PostgREST /rest/v1/* mocks must be set up via mockSupabaseQueries()
 * BEFORE calling page.goto() in each test.
 */
async function seedSupabaseAuth(page: Page) {
  // Seed session in localStorage before page loads
  await page.addInitScript(
    ({ session }) => {
      const storageKey = 'sb-localhost-auth-token';
      localStorage.setItem(storageKey, JSON.stringify(session));
    },
    { session: mockSession },
  );

  // Intercept token refresh
  await page.route('**/auth/v1/token**', jsonResponse(mockSession));

  // Intercept get user
  await page.route('**/auth/v1/user', jsonResponse(mockSupabaseUser));
}

/**
 * Mocks the BACKEND-API endpoints the layout enrichment + seed shell depend
 * on. The layout's `useERPLayoutEnrichment` blocks render (shows "Carregando…")
 * until the user profile resolves. The profile + roles reads moved from the
 * Supabase PostgREST tables to the backend API in the "Pattern D resolution"
 * (Phase 4, 2026-05-20): `useUserProfile` -> GET /api/profiles/me and
 * `useUserRoles` -> GET /api/profiles/me/roles. Without these mocks the
 * enrichment never unblocks and NO authenticated page ever renders, so every
 * page-level assertion fails with "element(s) not found".
 *
 * The rank badge (`/api/metas/{periodos,rankings}`) and the seed shell
 * (`/api/notificacoes*`, `/api/me/consents`) are non-blocking but mocked here
 * too so the authenticated DOM is deterministic and free of error toasts.
 *
 * Default roles = ['corretor']. Admin-only tests override the roles route
 * AFTER the fixture runs (Playwright LIFO route matching — last wins).
 */
async function mockLayoutBackendAPIs(page: Page) {
  // Profile — unblocks `useERPLayoutEnrichment` (isLoading is `... || !profile`).
  await page.route('**/api/profiles/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: mockProfile }) }),
  );
  // Roles — default non-admin (corretor). Admin tests override this route.
  await page.route('**/api/profiles/me/roles', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: ['corretor'] }) }),
  );
  // Rank badge in the header role label (non-blocking).
  await page.route('**/api/metas/periodos**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) }),
  );
  await page.route('**/api/metas/rankings**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: { unificado: [] } }) }),
  );
  // Seed shell — notification bell + AI consent badge (non-blocking).
  await page.route('**/api/notificacoes/contagem**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: { total: 0 } }) }),
  );
  await page.route('**/api/notificacoes**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [], total: 0, page: 1, page_size: 50 }) }),
  );
  await page.route('**/api/me/consents**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: { catalog: [] } }) }),
  );
}

type AuthFixtures = {
  authenticatedPage: Page;
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    await seedSupabaseAuth(page);
    await mockLayoutBackendAPIs(page);
    await use(page);
  },
});

export { expect } from '@playwright/test';
export { seedSupabaseAuth, mockLayoutBackendAPIs };
