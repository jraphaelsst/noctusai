import { test, expect } from '../fixtures/auth.fixture';
import { mockDashboardAPIs } from '../fixtures/api-mocks';

/**
 * Selectors target the post-`df821179` Dashboard, which renders via the seed
 * `<Header>` (user name shown as the header user-card text, capitalized by
 * `formatName`) + Tailwind product-card grid. The pre-refactor bespoke CSS
 * classes (`.user-name`, `.product-card`, `.org-name`, `.btn-admin`,
 * `.trial-info`, `.upgrade-banner`) no longer exist — we assert role/text
 * semantics instead, preserving each test's original intent.
 */
test.describe('Dashboard', () => {
  test('displays user name and welcome heading', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    // Header user-card renders the (formatted) full name.
    await expect(page.getByText('Rafael Oliveira').first()).toBeVisible();
    // Welcome heading uses the first name.
    await expect(page.getByRole('heading', { name: 'Bem-vindo, Rafael!' })).toBeVisible();
  });

  test('shows welcome message with first name', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Bem-vindo, Rafael!' })).toBeVisible();
    await expect(page.getByText('Seus produtos NoctusAI')).toBeVisible();
  });

  test('renders product cards with access status', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    // Product with access — card heading + "Acessar" call-to-action.
    await expect(page.getByRole('heading', { name: 'ERP Imobiliário' })).toBeVisible();
    await expect(page.getByText('Acessar')).toBeVisible();

    // Product without access (the granted CRM card, not the coming-soon one)
    // shows "Solicitar acesso".
    await expect(page.getByText('Solicitar acesso')).toBeVisible();
  });

  test('lists only real products — no "coming soon" phantoms', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    // Real catalog products render (from /api/auth/me)...
    await expect(page.getByRole('heading', { name: 'ERP Imobiliário' })).toBeVisible();
    // ...and the old hardcoded "coming soon" placeholder cards are gone — the
    // dashboard now reflects only products that actually exist.
    await expect(page.getByText('Em breve')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'BI Analytics' })).toHaveCount(0);
  });

  test('shows a "dev" badge on products not deployed in this environment', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    // erp-imobiliario deployed (no badge); crm-vendas not deployed (dev badge).
    await page.route('**/api/products/deployment-status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ deployed: { 'erp-imobiliario': true, 'crm-vendas': false } }),
      }),
    );
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'ERP Imobiliário' })).toBeVisible();
    // Exactly one tile (crm-vendas) carries the "dev" badge.
    await expect(page.getByText('dev', { exact: true })).toHaveCount(1);
  });

  test('shows subscription badge', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    // The plan badge sits beside the "Seus produtos NoctusAI" subtitle.
    await expect(page.getByText('Seus produtos NoctusAI')).toBeVisible();
    await expect(page.getByText('Profissional').first()).toBeVisible();
  });

  test('shows upgrade banner for free plan', async ({ authenticatedPage: page }) => {
    // No subscription → free org → upgrade banner. The org category is
    // 'production' (mockOrganization) so the non-test-org banner renders.
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":null}' }),
    );
    await page.goto('/');

    await expect(page.getByText('Desbloqueie todo o potencial do NoctusAI')).toBeVisible();
    await expect(page.getByText('Ver planos')).toBeVisible();
  });

  test('admin user sees Admin Panel button', async ({ adminPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    await expect(page.getByRole('button', { name: 'Admin Panel' })).toBeVisible();
  });

  test('non-admin user does not see Admin Panel button', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await page.goto('/');

    // Wait for the dashboard to render before asserting absence.
    await expect(page.getByRole('heading', { name: 'Bem-vindo, Rafael!' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Admin Panel' })).toHaveCount(0);
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
            plans: { nome: 'Profissional', slug: 'pro' },
          },
        }),
      }),
    );
    await page.goto('/');

    // Trial banner copy + the "Assinar agora" CTA.
    await expect(page.getByText(/Seu período de teste/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Assinar agora' })).toBeVisible();
  });
});
