import { test, expect } from '../fixtures/auth.fixture';
import { mockMatchingAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Matching de Ativos', () => {
  test('displays page title and match count', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    await expect(page.getByRole('heading', { name: 'Matching de Ativos' })).toBeVisible();
    await expect(page.getByText(/encontrado/)).toBeVisible();
  });

  test('shows match cards with scores', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    // score.toFixed(1) renders as "85.0%" and "45.0%"
    await expect(page.getByText('85.0%').first()).toBeVisible();
    await expect(page.getByText('45.0%').first()).toBeVisible();
  });

  test('shows score breakdown bars', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    await expect(page.getByText('Similaridade IA').first()).toBeVisible();
    await expect(page.getByText('Preço').first()).toBeVisible();
    await expect(page.getByText('Região').first()).toBeVisible();
    await expect(page.getByText('Specs').first()).toBeVisible();
  });

  test('shows accept/reject buttons for pending matches', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    await expect(page.getByRole('button', { name: /Aceitar/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Rejeitar/ }).first()).toBeVisible();
  });

  test('has "Recalcular Tudo" button', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    // The bulk-regenerate action is now labelled "Recalcular Tudo"
    // (was "Gerar Matches"). Same intent: trigger match (re)generation.
    await expect(page.getByRole('button', { name: /Recalcular Tudo/ })).toBeVisible();
  });

  test('has "Embed Batch" button', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    await expect(page.getByRole('button', { name: /Embed Batch/ })).toBeVisible();
  });

  test('shows filter controls', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    // Filtering was simplified to a single Status dropdown (the prior
    // origem-search input + "Score mínimo" slider were removed). Intent
    // preserved: the page exposes a filter control.
    await expect(page.getByText('Status:')).toBeVisible();
    await expect(page.getByRole('combobox')).toBeVisible();
  });

  test('shows status filter', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    await expect(page.getByText('Todos')).toBeVisible();
  });

  test('shows justificativa when present', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMatchingAPIs(page);
    await page.goto('/matching');

    await expect(page.getByText(/zona sul de São Paulo/)).toBeVisible();
  });

  test('shows empty state when no matches', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await page.route('**/api/matching', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: [], total: 0, page: 1, page_size: 50 }),
        });
      }
      return route.continue();
    });
    await page.goto('/matching');

    await expect(page.getByText(/Nenhum match encontrado/)).toBeVisible();
  });
});
