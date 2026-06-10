import { test as base, type Page } from '@playwright/test';
import { mockSession, mockSupabaseUser } from './mock-data';
import { jsonResponse } from './helpers';

/**
 * Seeds the Supabase auth session in localStorage and intercepts
 * auth-related endpoints so the social-wiring app believes the user is
 * authenticated.
 *
 * Social Wiring's layout does not have the same enrichment gates as ERP —
 * it only needs Supabase auth + the seed shell non-blocking routes.
 */
async function seedSupabaseAuth(page: Page) {
  await page.addInitScript(
    ({ session }) => {
      const storageKey = 'sb-localhost-auth-token';
      localStorage.setItem(storageKey, JSON.stringify(session));
    },
    { session: mockSession },
  );

  await page.route('**/auth/v1/token**', jsonResponse(mockSession));
  await page.route('**/auth/v1/user', jsonResponse(mockSupabaseUser));
}

/**
 * Mocks the seed shell routes the layout depends on (notification bell,
 * consent badge). Without these, the shell may show error toasts but should
 * not block render — they are non-blocking for social-wiring's simple layout.
 */
async function mockShellAPIs(page: Page) {
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
    await mockShellAPIs(page);
    await use(page);
  },
});

export { expect } from '@playwright/test';
export { seedSupabaseAuth, mockShellAPIs };
