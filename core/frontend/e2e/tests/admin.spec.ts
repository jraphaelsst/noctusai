import { test, expect } from '../fixtures/auth.fixture';
import { mockAdminAPIs } from '../fixtures/api-mocks';

test.describe('Admin Panel', () => {
  test('non-admin is redirected away from /admin', async ({ authenticatedPage: page }) => {
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":null}' }),
    );
    await page.goto('/admin');

    // AdminRoute redirects non-admins to /
    await expect(page).toHaveURL('/');
  });

  test('admin can access /admin and sees sidebar', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    // Sidebar navigation items
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Organiza/ })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Assinaturas' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Chaves API' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Planos' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Faturamento' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Webhooks' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Analytics' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Configura/ })).toBeVisible();
  });

  test('admin dashboard shows stats', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    // The admin dashboard should load
    await expect(page.locator('.admin-layout')).toBeVisible();
  });

  test('navigates to Organizations page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await page.getByRole('link', { name: /Organiza/ }).click();
    await expect(page).toHaveURL('/admin/orgs');
  });

  test('navigates to Subscriptions page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await page.getByRole('link', { name: 'Assinaturas' }).click();
    await expect(page).toHaveURL('/admin/subs');
  });

  test('navigates to API Keys page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await page.getByRole('link', { name: 'Chaves API' }).click();
    await expect(page).toHaveURL('/admin/api-keys');
  });

  test('navigates to Plans page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await page.getByRole('link', { name: 'Planos' }).click();
    await expect(page).toHaveURL('/admin/plans');
  });

  test('admin header shows user name and logout', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await expect(page.getByText('Ana Souza')).toBeVisible();
    await expect(page.getByText('Sair')).toBeVisible();
  });
});
