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

  test('can toggle between login and signup mode', async ({ page }) => {
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"invalid_grant"}' }),
    );
    await page.route('**/rest/v1/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/login');

    // Start in login mode
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible();

    // Toggle to signup
    await page.getByText('Cadastre-se').click();
    await expect(page.getByRole('button', { name: 'Criar Conta' })).toBeVisible();

    // Signup fields should be visible
    await expect(page.getByPlaceholder(/nome/i)).toBeVisible();

    // Toggle back
    await page.getByText('Faça login').click();
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible();
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

  test('shows password recovery dialog', async ({ page }) => {
    await page.route('**/auth/v1/token**', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"invalid_grant"}' }),
    );
    await page.route('**/rest/v1/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/login');

    await page.getByText('Esqueci minha senha').click();

    await expect(page.getByText('Recuperar Senha').first()).toBeVisible();
    await expect(page.getByText('Informe seu email cadastrado')).toBeVisible();
  });
});
