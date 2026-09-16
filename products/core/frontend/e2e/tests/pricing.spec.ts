import { test, expect } from '../fixtures/auth.fixture';
import { mockPricingAPIs } from '../fixtures/api-mocks';
import { mockCheckoutUrl } from '../fixtures/mock-data';

/**
 * Pricing reads `GET /api/billing/plans` (sellable plans + active prices in
 * cents + offered gateways) and starts a subscription with
 * `POST /api/billing/subscribe`, then redirects to the gateway's page.
 * Each plan card is an `<article>` labelled with the plan name.
 */

type Page = import('@playwright/test').Page;

function planCard(page: Page, name: string) {
  return page.getByRole('article', { name });
}

test.describe('Pricing', () => {
  test('displays plan cards', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(page.getByRole('heading', { name: 'Escolha seu plano' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Gratuito' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Profissional' })).toBeVisible();
  });

  test('shows free plan as "Grátis"', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const freeCard = planCard(page, 'Gratuito');
    // exact:true so the price "Grátis" is distinct from the "Começar Grátis" CTA.
    await expect(freeCard.getByText('Grátis', { exact: true })).toBeVisible();
    await expect(freeCard.getByRole('button', { name: 'Começar Grátis' })).toBeVisible();
  });

  test('shows monthly/yearly toggle', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(page.getByRole('button', { name: 'Mensal' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Anual/ })).toBeVisible();
  });

  test('toggles between monthly and yearly pricing', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    // Default is monthly. Prices are Intl-formatted (pt-BR), so match loosely
    // on the separators rather than on the exact space character.
    const proCard = planCard(page, 'Profissional');
    await expect(proCard.getByText(/R\$\s*199,90/)).toBeVisible();
    await expect(proCard.getByText('/mês')).toBeVisible();

    await page.getByRole('button', { name: /Anual/ }).click();

    await expect(proCard.getByText(/R\$\s*1\.999,90/)).toBeVisible();
    await expect(proCard.getByText('/ano')).toBeVisible();
  });

  test('shows "Mais Popular" tag on Pro plan', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(planCard(page, 'Profissional').getByText('Mais Popular')).toBeVisible();
    await expect(planCard(page, 'Gratuito').getByText('Mais Popular')).toHaveCount(0);
  });

  test('shows feature list on plan cards', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const proCard = planCard(page, 'Profissional');
    await expect(proCard.getByText('10 usuários')).toBeVisible();
    await expect(proCard.getByText('5 produtos')).toBeVisible();
    await expect(proCard.getByText('Suporte prioritario')).toBeVisible();
  });

  test('checkout button triggers redirect', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const proCard = planCard(page, 'Profissional');
    await proCard.getByRole('button', { name: 'Assinar' }).click();

    const subscribe = page.waitForRequest('**/api/billing/subscribe');
    await page.getByRole('button', { name: 'Continuar para o pagamento' }).click();
    const body = (await subscribe).postDataJSON();
    expect(body).toMatchObject({ plan_price_id: 'price-002-m', gateway: 'stripe', billing_method: 'card' });

    await page.waitForURL(`${mockCheckoutUrl}**`);
    await expect(page.getByRole('heading', { name: 'Stripe Checkout (mock)' })).toBeVisible();
  });
});
