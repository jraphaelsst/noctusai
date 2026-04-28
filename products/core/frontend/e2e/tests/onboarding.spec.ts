import { test, expect } from '../fixtures/auth.fixture';
import { mockOnboardingAPIs, mockPricingAPIs } from '../fixtures/api-mocks';

test.describe('Onboarding', () => {
  test('displays 4-step wizard', async ({ authenticatedPage: page }) => {
    await mockOnboardingAPIs(page);
    await mockPricingAPIs(page);
    await page.goto('/onboarding');

    await expect(page.getByText('Configure sua conta em poucos passos')).toBeVisible();

    // All 4 step labels visible in progress bar
    await expect(page.locator('.onboarding-step-label', { hasText: 'Dados da Empresa' })).toBeVisible();
    await expect(page.locator('.onboarding-step-label', { hasText: 'Escolher Plano' })).toBeVisible();
    await expect(page.locator('.onboarding-step-label', { hasText: 'Convidar Equipe' })).toBeVisible();
    await expect(page.locator('.onboarding-step-label', { hasText: 'Ativar Produto' })).toBeVisible();
  });

  test('step 1 shows company details form', async ({ authenticatedPage: page }) => {
    await mockOnboardingAPIs(page);
    await mockPricingAPIs(page);
    await page.goto('/onboarding');

    // First step should be active
    await expect(page.locator('h2')).toContainText('Dados da Empresa');

    // Form fields
    await expect(page.getByPlaceholder('Minha Empresa Ltda')).toBeVisible();
    await expect(page.getByPlaceholder('00.000.000/0001-00')).toBeVisible();
    await expect(page.getByPlaceholder('(11) 99999-0000')).toBeVisible();
    await expect(page.getByPlaceholder('Rua Exemplo, 123 - Sao Paulo, SP')).toBeVisible();
  });

  test('shows skip and next buttons', async ({ authenticatedPage: page }) => {
    await mockOnboardingAPIs(page);
    await mockPricingAPIs(page);
    await page.goto('/onboarding');

    await expect(page.getByText('Pular')).toBeVisible();
    await expect(page.getByText('Proximo')).toBeVisible();
  });

  test('advances to next step on submit', async ({ authenticatedPage: page }) => {
    await mockOnboardingAPIs(page);
    await mockPricingAPIs(page);
    await page.goto('/onboarding');

    // Fill step 1
    await page.getByPlaceholder('Minha Empresa Ltda').fill('Imobiliária XYZ');
    await page.getByPlaceholder('00.000.000/0001-00').fill('12.345.678/0001-99');

    // Submit step 1
    await page.getByText('Proximo').click();

    // Should advance to step 2 (Choose Plan)
    await expect(page.locator('h2')).toContainText('Escolher Plano');
  });

  test('skip button advances without filling', async ({ authenticatedPage: page }) => {
    await mockOnboardingAPIs(page);
    await mockPricingAPIs(page);
    await page.goto('/onboarding');

    await page.getByText('Pular').click();

    // Should advance to step 2
    await expect(page.locator('h2')).toContainText('Escolher Plano');
  });

  test('back button returns to previous step', async ({ authenticatedPage: page }) => {
    await mockOnboardingAPIs(page);
    await mockPricingAPIs(page);

    // Override onboarding to start at step 2
    await page.route('**/api/onboarding/status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            org_id: 'org-001',
            org_nome: 'Imobiliária Centro Sul',
            onboarding_completed: false,
            steps: { company_details: true, choose_plan: false, invite_team: false, enable_product: false },
            progress: { completed: 1, total: 4, percentage: 25 },
          },
        }),
      }),
    );

    await page.goto('/onboarding');
    await expect(page.locator('h2')).toContainText('Escolher Plano');

    await page.getByText('Voltar').click();
    await expect(page.locator('h2')).toContainText('Dados da Empresa');
  });

  test('last step shows "Concluir" button', async ({ authenticatedPage: page }) => {
    await mockPricingAPIs(page);

    // Override onboarding to start at step 4
    await page.route('**/api/onboarding/status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            org_id: 'org-001',
            org_nome: 'Imobiliária Centro Sul',
            onboarding_completed: false,
            steps: { company_details: true, choose_plan: true, invite_team: true, enable_product: false },
            progress: { completed: 3, total: 4, percentage: 75 },
          },
        }),
      }),
    );
    await page.route('**/api/onboarding/complete', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            steps: { company_details: true, choose_plan: true, invite_team: true, enable_product: true },
            onboarding_completed: true,
            progress: { completed: 4, total: 4, percentage: 100 },
          },
        }),
      }),
    );

    await page.goto('/onboarding');
    await expect(page.locator('h2')).toContainText('Ativar Produto');
    await expect(page.getByRole('button', { name: 'Concluir' })).toBeVisible();
  });
});
