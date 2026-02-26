import { test as base, type Page } from '@playwright/test';
import { mockSession, mockSupabaseUser } from './mock-data';
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

type AuthFixtures = {
  authenticatedPage: Page;
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    await seedSupabaseAuth(page);
    await use(page);
  },
});

export { expect } from '@playwright/test';
export { seedSupabaseAuth };
