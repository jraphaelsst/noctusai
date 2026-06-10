import { test, expect } from '../fixtures/auth.fixture';
import {
  mockMailchimpConnectionConnected,
  mockMailchimpConnectionDisconnected,
  mockMailchimpContacts,
} from '../fixtures/mailchimp';

test.describe('Contatos', () => {
  test('gate shows NotConnected when probe returns disconnected', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionDisconnected(page);
    await page.goto('/contatos');

    await expect(page.getByTestId('mailchimp-not-connected')).toBeVisible();
    await expect(page.getByRole('link', { name: /Conectar Mailchimp/i })).toBeVisible();
  });

  test('with connection — rows render with contact emails', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpContacts(page);
    await page.goto('/contatos');

    await expect(page.getByText('joao@exemplo.com')).toBeVisible();
    await expect(page.getByText('maria@exemplo.com')).toBeVisible();
  });

  test('shows loading state while fetching contacts', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    // Don't mock contacts — causes loading state
    await page.route('**/api/mailchimp/contacts**', async (route) => {
      await new Promise((r) => setTimeout(r, 2000));
      await route.continue();
    });
    await page.goto('/contatos');

    await expect(page.getByTestId('contatos-loading')).toBeVisible();
  });

  test('status badge renders correctly for subscribed contact', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpContacts(page);
    await page.goto('/contatos');

    await expect(page.getByText('Inscrito').first()).toBeVisible();
  });

  test('create contact modal opens and has email field', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpContacts(page);
    await page.goto('/contatos');

    await page.getByTestId('btn-novo-contato').click();
    await expect(page.getByTestId('contato-modal')).toBeVisible();
    await expect(page.getByTestId('contact-email-input')).toBeVisible();
  });

  test('create contact modal submit fires PUT request', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpContacts(page);
    await page.goto('/contatos');

    await page.getByTestId('btn-novo-contato').click();
    await page.getByTestId('contact-email-input').fill('novo@exemplo.com');
    await page.getByTestId('contact-first-name-input').fill('Novo');

    const requestPromise = page.waitForRequest('**/api/mailchimp/contacts/**');
    await page.getByTestId('contact-modal-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('PUT');
  });

  test('archive confirm fires DELETE request', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpContacts(page);
    await page.goto('/contatos');

    // Click archive button for first contact
    await page.getByTestId('archive-contato-joao@exemplo.com').click();
    await expect(page.getByTestId('confirm-archive-contato')).toBeVisible();

    const requestPromise = page.waitForRequest('**/api/mailchimp/contacts/**');
    await page.getByTestId('confirm-archive-contato').click();
    const req = await requestPromise;

    expect(req.method()).toBe('DELETE');
  });

  test('edit contact — email field is read-only', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpContacts(page);
    await page.goto('/contatos');

    await page.getByTestId('edit-contato-joao@exemplo.com').click();
    const emailInput = page.getByTestId('contact-email-input');
    await expect(emailInput).toBeDisabled();
    await expect(emailInput).toHaveValue('joao@exemplo.com');
  });
});
