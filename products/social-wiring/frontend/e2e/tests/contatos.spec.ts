/**
 * Contatos — platform (in-home) contact management.
 *
 * The Contatos page shows LOCAL platform contacts (social_wiring.contacts,
 * via /api/email-marketing/contacts) — NOT Mailchimp audience members. It
 * has no MailchimpGate. See src/pages/Contatos.tsx and the
 * contacts/identity FE rework (commit bdcfe0ad5).
 */
import { test, expect } from '../fixtures/auth.fixture';
import { mockContactsList, mockContactsEmpty } from '../fixtures/contacts';
import { mockPlatformContacts } from '../fixtures/mock-data';

test.describe('Contatos', () => {
  test('renders empty state when there are no contacts', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsEmpty(page);
    await page.goto('/contatos');

    await expect(page.getByTestId('contatos-empty')).toBeVisible();
  });

  test('contacts list — rows render with contact emails', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsList(page);
    await page.goto('/contatos');

    await expect(page.getByText('joao@exemplo.com')).toBeVisible();
    await expect(page.getByText('maria@exemplo.com')).toBeVisible();
  });

  test('shows loading state while fetching contacts', async ({
    authenticatedPage: page,
  }) => {
    // Don't mock the list route — causes loading state (route never resolves).
    await page.route('**/api/email-marketing/contacts**', async (route) => {
      await new Promise((r) => setTimeout(r, 2000));
      await route.continue();
    });
    await page.goto('/contatos');

    await expect(page.getByTestId('contatos-loading')).toBeVisible();
  });

  test('source badge renders correctly for whatsapp contact', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsList(page);
    await page.goto('/contatos');

    await expect(page.getByTestId('source-badge-whatsapp')).toBeVisible();
    await expect(page.getByTestId('source-badge-manual')).toBeVisible();
  });

  test('create contact modal opens and has email field', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsList(page);
    await page.goto('/contatos');

    await page.getByTestId('btn-novo-contato').click();
    await expect(page.getByTestId('contato-modal')).toBeVisible();
    await expect(page.getByTestId('contact-email-input')).toBeVisible();
  });

  test('create contact modal submit fires POST request', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsList(page);
    await page.goto('/contatos');

    await page.getByTestId('btn-novo-contato').click();
    await page.getByTestId('contact-email-input').fill('novo@exemplo.com');
    await page.getByTestId('contact-nome-input').fill('Novo');

    const requestPromise = page.waitForRequest('**/api/email-marketing/contacts');
    await page.getByTestId('contact-modal-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });

  test('archive confirm fires DELETE request', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsList(page);
    await page.goto('/contatos');

    const contactId = mockPlatformContacts[0].id;
    await page.getByTestId(`archive-contato-${contactId}`).click();
    await expect(page.getByTestId('confirm-archive-contato')).toBeVisible();

    const requestPromise = page.waitForRequest('**/api/email-marketing/contacts/**');
    await page.getByTestId('confirm-archive-contato').click();
    const req = await requestPromise;

    expect(req.method()).toBe('DELETE');
  });

  test('edit contact — prefills existing fields, email stays editable', async ({
    authenticatedPage: page,
  }) => {
    await mockContactsList(page);
    await page.goto('/contatos');

    const contact = mockPlatformContacts[0];
    await page.getByTestId(`edit-contato-${contact.id}`).click();
    const emailInput = page.getByTestId('contact-email-input');
    // ContactUpdate schema accepts `email` (backend comment: a typo'd
    // address must be correctable) — the field is intentionally NOT
    // disabled on edit, unlike the old Mailchimp-backed contract.
    await expect(emailInput).toBeEnabled();
    await expect(emailInput).toHaveValue(contact.email);
    await expect(page.getByTestId('contact-nome-input')).toHaveValue(contact.nome);
  });
});
