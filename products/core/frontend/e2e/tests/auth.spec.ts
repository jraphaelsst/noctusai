import { test, expect } from '../fixtures/auth.fixture';

test.describe('Authentication', () => {
  test('shows login form when unauthenticated', async ({ page }) => {
    await page.route('**/api/auth/oauth/providers', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.goto('/login');

    await expect(page.locator('h1')).toContainText('NoctusAI');
    await expect(page.locator('h2')).toContainText('Entrar');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toContainText('Entrar');
  });

  test('can toggle between login and signup', async ({ page }) => {
    await page.route('**/api/auth/oauth/providers', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.goto('/login');

    // Should start in login mode
    await expect(page.locator('h2')).toContainText('Entrar');

    // Toggle to signup
    await page.getByText('Não tem conta? Criar agora').click();
    await expect(page.locator('h2')).toContainText('Criar conta');

    // Signup-specific fields should appear
    await expect(page.getByPlaceholder('João Silva')).toBeVisible();
    await expect(page.getByPlaceholder('Imobiliária Silva')).toBeVisible();

    // Toggle back to login
    await page.getByText('Já tem conta? Entrar').click();
    await expect(page.locator('h2')).toContainText('Entrar');
  });

  test('shows error on invalid login', async ({ page }) => {
    await page.route('**/api/auth/oauth/providers', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: '{"detail":"Email ou senha incorretos"}',
      }),
    );

    await page.goto('/login');
    await page.locator('input[type="email"]').fill('wrong@email.com');
    await page.locator('input[type="password"]').fill('wrongpassword');
    await page.locator('button[type="submit"]').click();

    // The login form surfaces the API `detail` in an inline error div
    // (the pre-refactor `.error` class was dropped in the Tailwind rewrite).
    await expect(page.getByText('Email ou senha incorretos')).toBeVisible();
  });

  test('redirects to landing when accessing protected route without auth', async ({ page }) => {
    await page.route('**/api/auth/oauth/providers', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.goto('/');

    // No token → the seed createProductApp guard redirects unauthenticated
    // users to `unauthRedirect`, which core sets to '/landing' (apex landing
    // page added in df821179). The login form lives at /login.
    await expect(page).toHaveURL(/\/landing/);
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.route('**/api/auth/oauth/providers', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"access_token":"mock-jwt-token"}',
      }),
    );
    await page.route('**/api/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'u1', nome: 'Rafael', email: 'rafael@test.com', role: 'member', org_id: 'o1' },
          organization: { id: 'o1', nome: 'Org Teste', slug: 'org-teste', plano: 'pro' },
          products: [],
        }),
      }),
    );
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":null}' }),
    );

    await page.goto('/login');
    await page.locator('input[type="email"]').fill('rafael@test.com');
    await page.locator('input[type="password"]').fill('password123');
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL('/');
    // Authed dashboard renders the user's name via the seed Header user-card.
    await expect(page.getByText('Rafael').first()).toBeVisible();
  });

  test('logout clears token and redirects to login', async ({ authenticatedPage: page }) => {
    await page.route('**/api/subscriptions/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":null}' }),
    );

    await page.goto('/');
    await expect(page.getByText('Rafael Oliveira').first()).toBeVisible();

    // Logout moved into the seed Header user-card HoverCard: hover the user
    // card to open it, then click the logout icon-button (title="Sair").
    // Dashboard handleLogout() clears the token then navigates to /login.
    await page.getByText('Rafael Oliveira').first().hover();
    await page.getByRole('button', { name: 'Sair' }).click();

    await expect(page).toHaveURL(/\/login/);

    // Verify token was cleared
    const token = await page.evaluate(() => localStorage.getItem('noctus_token'));
    expect(token).toBeNull();
  });
});
