/**
 * Route-interception fixtures for /api/email-marketing/contacts — the
 * platform (in-home) contacts endpoint backing the Contatos page
 * (social_wiring.contacts). NOT Mailchimp — see e2e/fixtures/mailchimp.ts
 * for the /api/mailchimp/* audience-member routes (EmailMembros page).
 */
import type { Page } from '@playwright/test';
import { makePlatformContactsPage, makePlatformContact, mockPlatformContacts } from './mock-data';

export async function mockContactsList(page: Page, contacts = mockPlatformContacts) {
  await page.route(/\/api\/email-marketing\/contacts(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makePlatformContactsPage(contacts)),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ data: makePlatformContact({ id: 'contact-new' }) }),
      });
    }
    return route.continue();
  });
  await page.route(/\/api\/email-marketing\/contacts\/[^/]+$/, (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: makePlatformContact() }),
      });
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, message: 'Contato removido' }),
      });
    }
    return route.continue();
  });
}

export async function mockContactsEmpty(page: Page) {
  await mockContactsList(page, []);
}
