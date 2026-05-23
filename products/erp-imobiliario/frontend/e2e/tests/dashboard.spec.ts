import { test, expect } from '../fixtures/auth.fixture';
import { mockDashboardAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('ERP Dashboard', () => {
  test('displays metric cards', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    // Use heading role for card titles (avoids matching description text)
    await expect(page.getByRole('heading', { name: 'Total de Metas' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Metas Concluídas' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Metas Abertas' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Vencem Amanhã' })).toBeVisible();
  });

  test('shows performance section', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByText('Performance').first()).toBeVisible();
  });

  test('displays chart containers', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByText('Resumo de Progresso').first()).toBeVisible();
  });

  test('shows header with user name', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByText('Rafael Oliveira').first()).toBeVisible();
  });
});
