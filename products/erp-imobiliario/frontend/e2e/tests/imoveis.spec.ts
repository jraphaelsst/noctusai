import { test, expect } from '../fixtures/auth.fixture';
import { mockImoveisAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Imóveis', () => {
  test('displays property listings', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockImoveisAPIs(page);
    await page.goto('/imoveis');

    await expect(page.getByText('Apartamento 3 quartos Moema')).toBeVisible();
    await expect(page.getByText('Casa com piscina Vila Mariana')).toBeVisible();
    await expect(page.getByText('Terreno 500m² Pinheiros')).toBeVisible();
  });

  test('shows property location info', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockImoveisAPIs(page);
    await page.goto('/imoveis');

    await expect(page.getByText('Moema').first()).toBeVisible();
    await expect(page.getByText('Vila Mariana').first()).toBeVisible();
    await expect(page.getByText('Pinheiros').first()).toBeVisible();
  });

  test('shows property types', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockImoveisAPIs(page);
    await page.goto('/imoveis');

    await expect(page.getByText(/apartamento/i).first()).toBeVisible();
    await expect(page.getByText(/casa/i).first()).toBeVisible();
    await expect(page.getByText(/terreno/i).first()).toBeVisible();
  });

  test('shows empty state when no properties', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await page.route('**/api/ativos**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [], total: 0, page: 1, page_size: 50 }),
      }),
    );
    await page.goto('/imoveis');

    await expect(page.getByText(/nenhum/i)).toBeVisible();
  });
});
