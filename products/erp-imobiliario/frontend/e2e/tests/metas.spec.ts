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
    //
    // 🔴 `exact: true` is load-bearing, not tidiness. `getByText` matches on
    // SUBSTRING, and every label here is a prefix of a sidebar nav entry:
    // "Fechamento" ⊂ "Fechamentos" (App.tsx nav), "Visita" ⊂ "Visitas". Without
    // it, `.first()` resolves to the SIDEBAR link rather than the card title —
    // and at desktop width the collapsed rail renders that label
    // `md:max-w-0 md:opacity-0`, i.e. HIDDEN, so the assertion fails against an
    // element it was never meant to select. It then passes or fails on DOM
    // order and rail state rather than on whether the card rendered, which is
    // exactly the 2026-09-20 CI failure (and it reproduces locally on the
    // pinned 1.62.1 too — this was never a Playwright-version problem).
    await expect(page.getByText('Fechamento', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Visita', { exact: true }).first()).toBeVisible();
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
