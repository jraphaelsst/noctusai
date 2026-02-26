import { test, expect } from '../fixtures/auth.fixture';
import { mockDashboardAPIs } from '../fixtures/api-mocks';

test.describe('Dashboard', () => {
  test('displays user name and organization', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.locator('.user-name')).toContainText('Rafael Oliveira');
    await expect(page.locator('.org-name')).toContainText('Imobiliária Centro Sul');
  });

  test('shows welcome message with first name', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.getByText('Bem-vindo, Rafael!')).toBeVisible();
    await expect(page.getByText('Seus produtos NoctusAI')).toBeVisible();
  });

  test('renders product cards with access status', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    // Product with access
    const erpCard = page.locator('.product-card', { hasText: 'ERP Imobiliário' });
    await expect(erpCard).toBeVisible();
    await expect(erpCard).toHaveClass(/unlocked/);
    await expect(erpCard.locator('.product-status')).toContainText('Acessar');

    // Product without access (use .locked to disambiguate from coming-soon CRM card)
    const crmCard = page.locator('.product-card.locked', { hasText: 'CRM Vendas' });
    await expect(crmCard).toBeVisible();
    await expect(crmCard.locator('.product-status')).toContainText('Solicitar acesso');
  });

  test('shows "coming soon" placeholder cards', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.locator('.product-card.coming-soon')).toHaveCount(3);
    await expect(page.getByText('Em breve')).toHaveCount(3);
  });

  test('shows subscription badge', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.locator('.org-name .badge')).toContainText('Profissional');
  });

  test('shows upgrade banner for free plan', async ({ authenticatedPage: page }) => {
    // Override subscription to return no sub (free)
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":null}' }),
    );
    await page.goto('/');

    await expect(page.locator('.upgrade-banner')).toBeVisible();
    await expect(page.getByText('Desbloqueie todo o potencial do NoctusAI')).toBeVisible();
    await expect(page.getByText('Ver planos')).toBeVisible();
  });

  test('admin user sees Admin Panel button', async ({ adminPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.locator('.btn-admin')).toBeVisible();
    await expect(page.locator('.btn-admin')).toContainText('Admin Panel');
  });

  test('non-admin user does not see Admin Panel button', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.locator('.btn-admin')).toHaveCount(0);
  });

  test('shows trial countdown when on trial', async ({ authenticatedPage: page }) => {
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            id: 'sub-002',
            status: 'trial',
            started_at: '2026-02-20T00:00:00Z',
            expires_at: '2026-03-20T00:00:00Z',
            plans: { name: 'Profissional', slug: 'pro' },
          },
        }),
      }),
    );
    await page.goto('/');

    await expect(page.locator('.trial-info')).toBeVisible();
    await expect(page.getByText('Assinar agora')).toBeVisible();
  });
});
