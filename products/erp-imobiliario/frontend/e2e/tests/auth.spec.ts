import { test, expect } from '@playwright/test';
import { mockSession, mockSupabaseUser } from '../fixtures/mock-data';
import { jsonResponse } from '../fixtures/helpers';

test.describe('ERP Authentication', () => {
  test('shows login form when not authenticated', async ({ page }) => {
    // Supabase will fail to get session — shows login form
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"invalid_grant"}' }),
    );
    await page.route('**/rest/v1/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/login');

    // LoginForm card title is "Entrar" (heading) and there's a submit button "Entrar"
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('login form shows email, password and forgot-password link', async ({ page }) => {
    // The seed LoginForm (consumed at /login) is sign-in only — there is no
    // inline signup toggle. ERP onboards via SSO/invite, not self-signup.
    // Intent: the login form exposes its core affordances (credentials +
    // password recovery), targeted via stable label/role/text selectors.
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"invalid_grant"}' }),
    );
    await page.route('**/rest/v1/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/login');

    await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Senha')).toBeVisible();
    // Password-recovery affordance is a link to the /forgot-password route.
    await expect(page.getByRole('link', { name: 'Esqueceu a senha?' })).toBeVisible();
  });

  test('shows error on invalid credentials', async ({ page }) => {
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: '{"error":"invalid_grant","error_description":"Invalid login credentials"}',
      }),
    );
    await page.route('**/rest/v1/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/login');

    await page.locator('input[type="email"]').fill('wrong@email.com');
    await page.locator('input[type="password"]').fill('wrongpassword123');
    await page.getByRole('button', { name: 'Entrar' }).click();

    // Should show error toast or message
    await expect(page.getByText(/incorretos|Invalid|erro/i).first()).toBeVisible({ timeout: 5000 });
  });

  test('navigates to password recovery page', async ({ page }) => {
    // Password recovery is no longer an in-page dialog — it moved to the
    // dedicated /forgot-password route (seed ForgotPasswordPage). Intent
    // preserved: a user CAN reach password recovery from the login screen.
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"invalid_grant"}' }),
    );
    await page.route('**/rest/v1/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/login');

    await page.getByRole('link', { name: 'Esqueceu a senha?' }).click();

    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(page.getByRole('heading', { name: 'Recuperar Senha' })).toBeVisible();
    await expect(page.getByText(/Informe seu email para receber o link/i)).toBeVisible();
  });
});
