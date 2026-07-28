import { test, expect } from '../fixtures/auth.fixture';
import { mockDashboardAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Sidebar Navigation', () => {
  test('regular user sees nav items', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: false });
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Funil de Vendas' })).toBeVisible();
    // Gated by the `processos-venda` status_pagina row (migration 041) — if
    // that row is missing the item silently never renders, so this assertion
    // is the only thing that would catch it.
    await expect(page.getByRole('link', { name: 'Processos de Venda' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Clientes' })).toBeVisible();
    // Nav now distinguishes "Metas individuais" from "Metas da Empresa" — use
    // the exact item name to avoid a strict-mode multi-match on "Metas".
    await expect(page.getByRole('link', { name: 'Metas individuais' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Imóveis|Imoveis/ })).toBeVisible();
  });

  test('shows brand header', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByText('ONE')).toBeVisible();
  });

  test('admin user sees Painel de Controle section', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: true });
    await mockDashboardAPIs(page);
    // Roles now come from the backend (/api/profiles/me/roles), not Supabase
    // user_roles. Override the fixture default (['corretor']) — LIFO last wins.
    await page.route('**/api/profiles/me/roles', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: ['admin'] }) }),
    );
    await page.goto('/dashboard');

    await expect(page.getByText('Painel de Controle')).toBeVisible();
    await expect(page.getByRole('link', { name: /Usuários|Usuarios/ })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
  });

  test('regular user does not see admin section', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: false });
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByText('Painel de Controle')).toHaveCount(0);
  });

  test('active nav item is highlighted on Dashboard', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    const dashboardLink = page.getByRole('link', { name: 'Dashboard' });
    await expect(dashboardLink).toBeVisible();
    await expect(dashboardLink).toHaveClass(/bg-primary/);
  });

  test('navigates to Funil when clicked', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.route('**/api/funil**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.goto('/dashboard');

    await page.getByRole('link', { name: 'Funil' }).click();
    await expect(page).toHaveURL('/funil');
  });

  test('navigates to Clientes when clicked', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.route('**/api/clientes**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[],"total":0,"page":1,"page_size":50}' }),
    );
    await page.goto('/dashboard');

    await page.getByRole('link', { name: 'Clientes' }).click();
    await expect(page).toHaveURL('/clientes');
  });
});
