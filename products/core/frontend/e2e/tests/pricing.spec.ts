import { test, expect } from '../fixtures/auth.fixture';
import { mockPricingAPIs } from '../fixtures/api-mocks';

test.describe('Pricing', () => {
  test('displays plan cards', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(page.getByText('Escolha seu plano')).toBeVisible();

    // Plan names
    await expect(page.locator('.pricing-card', { hasText: 'Gratuito' })).toBeVisible();
    await expect(page.locator('.pricing-card', { hasText: 'Profissional' })).toBeVisible();
  });

  test('shows free plan as "Grátis"', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const freeCard = page.locator('.pricing-card', { hasText: 'Gratuito' });
    await expect(freeCard.locator('.pricing-price-value')).toContainText('Grátis');
    await expect(freeCard.locator('.pricing-cta')).toContainText('Começar Grátis');
  });

  test('shows monthly/yearly toggle', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(page.getByText('Mensal')).toBeVisible();
    await expect(page.getByText('Anual')).toBeVisible();
  });

  test('toggles between monthly and yearly pricing', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    // Default is monthly — Pro plan should show monthly price
    const proCard = page.locator('.pricing-card', { hasText: 'Profissional' });
    await expect(proCard.locator('.pricing-price-value')).toContainText('R$ 199,90');
    await expect(proCard.locator('.pricing-price-period')).toContainText('/mês');

    // Switch to yearly
    await page.locator('.pricing-toggle-btn', { hasText: 'Anual' }).click();

    await expect(proCard.locator('.pricing-price-value')).toContainText('R$ 1999,90');
    await expect(proCard.locator('.pricing-price-period')).toContainText('/ano');
  });

  test('shows "Mais Popular" tag on Pro plan', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    await expect(page.locator('.pricing-popular-tag')).toContainText('Mais Popular');
  });

  test('shows feature list on plan cards', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const proCard = page.locator('.pricing-card', { hasText: 'Profissional' });
    await expect(proCard.getByText('10 usuários')).toBeVisible();
    await expect(proCard.getByText('5 produtos')).toBeVisible();
  });

  test('checkout button triggers redirect', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);
    await page.goto('/pricing');

    const proCard = page.locator('.pricing-card', { hasText: 'Profissional' });
    const ctaButton = proCard.locator('.pricing-cta');
    await expect(ctaButton).toContainText('Assinar');
  });
});
