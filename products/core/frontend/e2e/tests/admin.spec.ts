import { test, expect } from '../fixtures/auth.fixture';
import { mockAdminAPIs } from '../fixtures/api-mocks';
import type { Page } from '@playwright/test';

// The admin sidebar is nested (Administracao › Visão geral | Clientes |
// Comercial | Plataforma) and each level is an accordion: only the group on
// the current page's path is open. Open a sub-group before reaching a link
// inside it (owner-approved UX, 2026-10-05, MENUS.md).
async function openNavGroup(page: Page, label: string) {
  const header = page.getByRole('button', { name: label, exact: true });
  if ((await header.getAttribute('aria-expanded')) !== 'true') {
    await header.click();
  }
  await expect(header).toHaveAttribute('aria-expanded', 'true');
}

test.describe('Admin Panel', () => {
  test('non-admin is redirected away from /admin', async ({ authenticatedPage: page }) => {
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":null}' }),
    );
    await page.goto('/admin');

    // SECURITY INTENT: CoreLayout's admin guard (`if (!isAdmin) <Navigate
    // to="/" replace>`) sends a member off /admin to the dashboard. Assert
    // both the redirect AND that no admin-only content rendered.
    await expect(page).toHaveURL('/');
    await expect(page.getByRole('heading', { name: 'Bem-vindo, Rafael!' })).toBeVisible();
    await expect(page.getByText('Visao geral da plataforma NoctusAI')).toHaveCount(0);
  });

  test('admin can access /admin and sees sidebar', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    // Sidebar navigation items, group by group (accordion: one open at a time)
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Analytics' })).toBeVisible();

    await openNavGroup(page, 'Clientes');
    await expect(page.getByRole('link', { name: /Organiza/ })).toBeVisible();

    await openNavGroup(page, 'Comercial');
    await expect(page.getByRole('link', { name: 'Assinaturas' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Planos' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Faturamento' })).toBeVisible();

    await openNavGroup(page, 'Plataforma');
    await expect(page.getByRole('link', { name: 'Chaves API' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Webhooks' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Configura/ })).toBeVisible();
  });

  test('admin dashboard shows stats', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    // The AdminDashboard renders its heading + the platform overview within
    // the AppShell (the pre-refactor `.admin-layout` class was dropped).
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('Visao geral da plataforma NoctusAI')).toBeVisible();
  });

  test('navigates to Organizations page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await openNavGroup(page, 'Clientes');
    await page.getByRole('link', { name: /Organiza/ }).click();
    await expect(page).toHaveURL('/admin/orgs');
  });

  test('navigates to Subscriptions page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await openNavGroup(page, 'Comercial');
    await page.getByRole('link', { name: 'Assinaturas' }).click();
    await expect(page).toHaveURL('/admin/subs');
  });

  test('navigates to API Keys page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await openNavGroup(page, 'Plataforma');
    await page.getByRole('link', { name: 'Chaves API' }).click();
    await expect(page).toHaveURL('/admin/api-keys');
  });

  test('navigates to Plans page', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    await openNavGroup(page, 'Comercial');
    await page.getByRole('link', { name: 'Planos' }).click();
    await expect(page).toHaveURL('/admin/plans');
  });

  test('admin header shows user name and logout', async ({ adminPage: page }) => {
    await mockAdminAPIs(page);
    await page.goto('/admin');

    // Seed Header renders the (formatted) name; logout is the icon-button
    // (title="Sair") inside the user-card HoverCard — hover to reveal it.
    await expect(page.getByText('Ana Souza').first()).toBeVisible();
    await page.getByText('Ana Souza').first().hover();
    await expect(page.getByRole('button', { name: 'Sair' })).toBeVisible();
  });
});
