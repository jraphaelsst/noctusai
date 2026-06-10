import { test, expect } from '../fixtures/auth.fixture';
import {
  mockMailchimpConnectionConnected,
  mockMailchimpTemplates,
} from '../fixtures/mailchimp';

test.describe('Templates', () => {
  test('card grid renders template names', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/templates');

    await expect(page.getByTestId('templates-grid')).toBeVisible();
    await expect(page.getByText('Newsletter Junho')).toBeVisible();
    await expect(page.getByText('Promoção Verão')).toBeVisible();
  });

  test('"Editar no Mailchimp" anchor has edit_url and target=_blank', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/templates');

    const link = page.getByTestId('edit-mailchimp-101');
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute(
      'href',
      'https://us6.admin.mailchimp.com/templates/edit?id=101',
    );
    await expect(link).toHaveAttribute('target', '_blank');
  });

  test('drag-and-drop badge renders for drag-and-drop template', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/templates');

    await expect(
      page.getByTestId('template-card-102').getByText('Drag & Drop'),
    ).toBeVisible();
  });

  test('"Novo template" modal opens and requires name + HTML', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/templates');

    await page.getByTestId('btn-novo-template').click();
    await expect(page.getByTestId('create-template-modal')).toBeVisible();

    // Submit disabled without name
    await expect(page.getByTestId('create-template-submit')).toBeDisabled();

    await page.getByTestId('template-name-input').fill('Meu Template');
    await page.getByTestId('template-html-input').fill('<html></html>');
    await expect(page.getByTestId('create-template-submit')).toBeEnabled();
  });

  test('create template fires POST request', async ({ authenticatedPage: page }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/templates');

    await page.getByTestId('btn-novo-template').click();
    await page.getByTestId('template-name-input').fill('Novo Template HTML');
    await page.getByTestId('template-html-input').fill('<!DOCTYPE html><html></html>');

    const requestPromise = page.waitForRequest('**/api/mailchimp/templates**');
    await page.getByTestId('create-template-submit').click();
    const req = await requestPromise;

    expect(req.method()).toBe('POST');
  });

  test('delete confirm dialog fires DELETE request', async ({
    authenticatedPage: page,
  }) => {
    await mockMailchimpConnectionConnected(page);
    await mockMailchimpTemplates(page);
    await page.goto('/email-marketing/templates');

    await page.getByTestId('delete-template-101').click();

    const requestPromise = page.waitForRequest('**/api/mailchimp/templates/101');
    await page.getByTestId('confirm-delete-template').click();
    const req = await requestPromise;

    expect(req.method()).toBe('DELETE');
  });
});
