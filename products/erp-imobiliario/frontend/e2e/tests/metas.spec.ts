import { test, expect } from '../fixtures/auth.fixture';
import { mockMetasAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Metas', () => {
  test('displays metas page', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMetasAPIs(page);
    await page.goto('/metas');

    await expect(page.getByRole('heading', { name: 'Metas', exact: true })).toBeVisible();
  });

  test('shows meta cards with categoria labels', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMetasAPIs(page);
    await page.goto('/metas');

    // MetaCard renders categoriaLabels[meta.categoria] as the title
    // visitas → "Visita", captacao_imoveis → "Captação de Imóveis", fechamento → "Fechamento"
    await expect(page.getByText('Fechamento').first()).toBeVisible();
    await expect(page.getByText('Visita').first()).toBeVisible();
  });

  test('shows meta type sections', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMetasAPIs(page);
    await page.goto('/metas');

    // Metas grouped by type with section headers
    await expect(page.getByText(/Metas Diárias/)).toBeVisible();
    await expect(page.getByText(/Metas Semanais/)).toBeVisible();
  });

  test('shows meta status indicators', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockMetasAPIs(page);
    await page.goto('/metas');

    // Status badge for active metas
    await expect(page.getByText('Aberta').first()).toBeVisible();
  });

  test('shows empty state when no metas', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await page.route('**/api/metas**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [], total: 0, page: 1, page_size: 50 }),
      }),
    );
    await page.goto('/metas');

    await expect(page.getByText(/nenhuma/i)).toBeVisible();
  });
});
