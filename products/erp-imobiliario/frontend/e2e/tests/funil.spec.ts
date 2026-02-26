import { test, expect } from '../fixtures/auth.fixture';
import { mockFunilAPIs, mockClientesAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

test.describe('Funil (Sales Pipeline)', () => {
  test('displays kanban columns', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    // ETAPAS_CONFIG labels: Qualificação, Visitas, Proposta, Negociação, Fechado
    await expect(page.getByRole('heading', { name: 'Qualificação' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Proposta' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Negociação' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Visitas' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Fechado' })).toBeVisible();
  });

  test('shows client cards in correct columns', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    await expect(page.getByText('João Santos')).toBeVisible();
    await expect(page.getByText('Maria Ferreira')).toBeVisible();
    await expect(page.getByText('Pedro Almeida')).toBeVisible();
  });

  test('has "Novo Cliente" button', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    await expect(page.getByText('Novo Cliente')).toBeVisible();
  });

  test('"Novo Cliente" button opens dialog', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockFunilAPIs(page);
    await mockClientesAPIs(page);
    await page.goto('/funil');

    await page.getByText('Novo Cliente').click();
    await expect(page.getByRole('dialog')).toBeVisible();
  });
});
