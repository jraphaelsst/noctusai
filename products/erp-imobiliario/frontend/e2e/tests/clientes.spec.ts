import { test, expect } from '../fixtures/auth.fixture';
import { mockClientesAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Clientes', () => {
  test('displays client list page', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockClientesAPIs(page);
    await page.goto('/clientes');

    await expect(page.getByRole('heading', { name: 'Clientes' })).toBeVisible();
  });

  test('shows client cards with name and info', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockClientesAPIs(page);
    await page.goto('/clientes');

    await expect(page.getByText('João Santos')).toBeVisible();
    await expect(page.getByText('Maria Ferreira')).toBeVisible();
  });

  test('has "Novo Cliente" button', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockClientesAPIs(page);
    await page.goto('/clientes');

    await expect(page.getByText('Novo Cliente')).toBeVisible();
  });

  test('shows empty state when no clients', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await page.route('**/api/clientes', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: [], total: 0, page: 1, page_size: 50 }),
        });
      }
      return route.continue();
    });
    await page.goto('/clientes');

    await expect(page.getByText('Nenhum cliente encontrado')).toBeVisible();
  });

  test('client card shows "Ver Detalhes" action', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockClientesAPIs(page);
    await page.goto('/clientes');

    await expect(page.getByText('Ver Detalhes').first()).toBeVisible();
  });

  test('navigating to client details changes URL', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockClientesAPIs(page);
    await page.goto('/clientes');

    await page.getByText('Ver Detalhes').first().click();
    await expect(page).toHaveURL(/\/clientes\/cli-001/);
  });
});
