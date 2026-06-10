import { test, expect } from '../fixtures/auth.fixture';
import {
  mockMailchimpConnectionDisconnected,
  mockMailchimpConnectionConnected,
  mockMailchimpConnectionInvalidKey,
} from '../fixtures/mailchimp';

test.describe('Configuração do Mailchimp', () => {
  test('disconnected state shows API key form', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionDisconnected(page);
    await page.goto('/email-marketing/configuracao');

    await expect(page.getByTestId('mailchimp-config-form')).toBeVisible();
    await expect(page.getByLabel('Chave API Mailchimp')).toBeVisible();
  });

  test('connect button disabled when key is empty', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionDisconnected(page);
    await page.goto('/email-marketing/configuracao');

    await expect(page.getByTestId('mailchimp-connect-submit')).toBeDisabled();
  });

  test('connect button enabled when key is filled', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionDisconnected(page);
    await page.goto('/email-marketing/configuracao');

    await page.getByTestId('mailchimp-api-key-input').fill('test-key-us6');
    await expect(page.getByTestId('mailchimp-connect-submit')).toBeEnabled();
  });

  test('paste API key → audience picker appears on success', async ({
    authenticatedPage: page,
  }) => {
    // Stateful mock: GET returns disconnected initially, then connected after PUT.
    let connected = false;
    const { mockConnectionConnected, mockConnectionDisconnected, mockAudiences } = await import(
      '../fixtures/mock-data'
    );
    await page.route('**/api/mailchimp/connection', (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(connected ? mockConnectionConnected : mockConnectionDisconnected),
        });
      }
      if (method === 'PUT') {
        connected = true;
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockConnectionConnected),
        });
      }
      return route.continue();
    });
    await page.route('**/api/mailchimp/audiences', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAudiences),
      }),
    );
    await page.goto('/email-marketing/configuracao');

    await page.getByTestId('mailchimp-api-key-input').fill('valid-key-us6');
    await page.getByTestId('mailchimp-connect-submit').click();

    // After successful PUT + invalidation, the GET refetch returns connected state
    await expect(page.getByTestId('mailchimp-connected-state')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('mailchimp-audience-select')).toBeVisible();
  });

  test('invalid key shows inline error', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionInvalidKey(page);
    await page.goto('/email-marketing/configuracao');

    await page.getByTestId('mailchimp-api-key-input').fill('invalid-key');
    await page.getByTestId('mailchimp-connect-submit').click();

    await expect(page.getByTestId('mailchimp-connect-error')).toBeVisible();
    await expect(page.getByTestId('mailchimp-connect-error')).toContainText(
      'inválida',
    );
  });

  test('connected state shows server prefix and action buttons', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await page.goto('/email-marketing/configuracao');

    await expect(page.getByTestId('mailchimp-connected-state')).toBeVisible();
    await expect(page.getByText('us6')).toBeVisible();
    await expect(page.getByTestId('mailchimp-replace-key-btn')).toBeVisible();
    await expect(page.getByTestId('mailchimp-disconnect-btn')).toBeVisible();
  });

  test('Substituir chave shows the key form again', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await page.goto('/email-marketing/configuracao');

    await page.getByTestId('mailchimp-replace-key-btn').click();
    await expect(page.getByTestId('mailchimp-config-form')).toBeVisible();
    await expect(page.getByLabel('Chave API Mailchimp')).toBeVisible();
  });
});
