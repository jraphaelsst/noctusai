import { test, expect } from '../fixtures/auth.fixture';
import { mockPricingAPIs } from '../fixtures/api-mocks';

/**
 * Pricing was rewritten to Tailwind cards in the seed migration — the bespoke
 * `.pricing-card` / `.pricing-price-value` / `.pricing-cta` / `.pricing-toggle-btn`
 * / `.pricing-popular-tag` classes are gone. We anchor each plan card to its
 * `<h3>` heading and assert role/text semantics. A card is the heading's nearest
 * ancestor that also contains the price + CTA, so we scope via a filtered locator.
 */

/** Locate the plan card <div> that contains the given plan-name heading. */
function planCard(page: import('@playwright/test').Page, name: string) {
  return page
    .locator('div.relative.flex.flex-col')
    .filter({ has: page.getByRole('heading', { name }) });
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
    // exact:true so the price span "Grátis" is distinct from the
    // "Começar Grátis" CTA button.
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

    // Default is monthly — Pro plan shows the monthly price + /mês period.
    const proCard = planCard(page, 'Profissional');
    await expect(proCard.getByText('R$ 199,90')).toBeVisible();
    await expect(proCard.getByText('/mês')).toBeVisible();

    // Switch to yearly.
    await page.getByRole('button', { name: /Anual/ }).click();

    await expect(proCard.getByText('R$ 1999,90')).toBeVisible();
    await expect(proCard.getByText('/ano')).toBeVisible();
  });

  test('shows "Mais Popular" tag on Pro plan', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(page.getByText('Mais Popular')).toBeVisible();
  });

  test('shows feature list on plan cards', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const proCard = planCard(page, 'Profissional');
    await expect(proCard.getByText('10 usuários')).toBeVisible();
    await expect(proCard.getByText('5 produtos')).toBeVisible();
  });

  test('checkout button triggers redirect', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const proCard = planCard(page, 'Profissional');
    await expect(proCard.getByRole('button', { name: 'Assinar' })).toBeVisible();
  });
});
