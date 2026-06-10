import { test, expect } from '../fixtures/auth.fixture';
import {
  mockMailchimpConnectionConnected,
  mockMailchimpSegments,
  mockMailchimpSegmentsMemberError,
} from '../fixtures/mailchimp';

test.describe('Listas (segmentos)', () => {
  test('renders segment table with name and member count', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpSegments(page);
    await page.goto('/email-marketing/listas');

    await expect(page.getByText('Clientes VIP')).toBeVisible();
    await expect(page.getByText('Newsletter')).toBeVisible();
    await expect(page.getByText('25')).toBeVisible();
  });

  test('create segment modal opens and submits', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpSegments(page);
    await page.goto('/email-marketing/listas');

    await page.getByTestId('btn-nova-lista').click();
    await expect(page.getByTestId('lista-modal')).toBeVisible();
    await page.getByTestId('lista-name-input').fill('Nova Lista Teste');

    const requestPromise = page.waitForRequest('**/api/mailchimp/segments**');
    await page.getByTestId('lista-modal-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });

  test('Membros button opens drawer with member list', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpSegments(page);
    await page.goto('/email-marketing/listas');

    await page.getByTestId('membros-btn-1').click();
    await expect(page.getByTestId('membros-drawer')).toBeVisible();
    await expect(page.getByText('joao@exemplo.com')).toBeVisible();
  });

  test('add member fires POST request', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpSegments(page);
    await page.goto('/email-marketing/listas');

    await page.getByTestId('membros-btn-1').click();
    await page.getByTestId('add-member-email-input').fill('novo@exemplo.com');

    const requestPromise = page.waitForRequest('**/api/mailchimp/segments/1/members**');
    await page.getByTestId('add-member-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });

  test('400 on add member shows "crie em Contatos primeiro" error', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpSegmentsMemberError(page);
    await page.goto('/email-marketing/listas');

    await page.getByTestId('membros-btn-1').click();
    await page.getByTestId('add-member-email-input').fill('naoexiste@exemplo.com');
    await page.getByTestId('add-member-submit').click();

    await expect(page.getByTestId('add-member-error')).toBeVisible();
    await expect(page.getByTestId('add-member-error')).toContainText('Contatos');
  });

  test('remove member button fires DELETE request', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpSegments(page);
    await page.goto('/email-marketing/listas');

    await page.getByTestId('membros-btn-1').click();

    const requestPromise = page.waitForRequest(
      /\/api\/mailchimp\/segments\/\d+\/members\/.+/,
    );
    await page.getByTestId('remove-member-joao@exemplo.com').click();
    const req = await requestPromise;

    expect(req.method()).toBe('DELETE');
  });
});
