import { test as base, type Page } from '@playwright/test';
import { mockUser, mockAdminUser, mockOrganization, mockProducts } from './mock-data';
import { jsonResponse } from './helpers';

/**
 * Seeds localStorage with a mock token and intercepts /api/auth/me
 * so the app believes the user is authenticated.
 */
async function seedAuth(
  page: Page,
  user: typeof mockUser,
  org: typeof mockOrganization = mockOrganization,
) {
  // Set token before the page loads
  await page.addInitScript(
    ({ token }) => {
      localStorage.setItem('noctus_token', token);
    },
    { token: 'mock-jwt-token' },
  );

  // Intercept the profile fetch
  await page.route('**/api/auth/me', jsonResponse({
    user,
    organization: org,
    products: mockProducts,
  }));

  // Intercept OAuth providers (called on Login page)
  await page.route('**/api/auth/oauth/providers', jsonResponse({ data: [] }));
}

type AuthFixtures = {
  authenticatedPage: Page;
  adminPage: Page;
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    await seedAuth(page, mockUser);
    await use(page);
  },
  adminPage: async ({ page }, use) => {
    await seedAuth(page, mockAdminUser);
    await use(page);
  },
});

export { expect } from '@playwright/test';
export { seedAuth };
