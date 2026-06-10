/**
 * Route-interception fixtures for /api/mailchimp/* endpoints.
 *
 * Each `mockMailchimp*` function sets up page.route interceptions for a
 * slice of the Mailchimp API. Tests compose these fixtures as needed.
 *
 * Contract: §1 of the mailchimp integration plan (binding shapes).
 */
import type { Page } from '@playwright/test';
import {
  mockConnectionConnected,
  mockConnectionDisconnected,
  mockAudiences,
  mockContacts,
  mockSegments,
  mockSegmentMembers,
  mockTemplates,
  mockCampaigns,
} from './mock-data';
import { jsonResponse, createdResponse, noContentResponse, errorResponse } from './helpers';

// ─── Connection ───────────────────────────────────────────────────────────────

export async function mockMailchimpConnectionConnected(page: Page) {
  await page.route('**/api/mailchimp/connection', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConnectionConnected),
      });
    }
    if (route.request().method() === 'PUT') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConnectionConnected),
      });
    }
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConnectionConnected),
      });
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });
  await page.route('**/api/mailchimp/audiences', jsonResponse(mockAudiences));
}

export async function mockMailchimpConnectionDisconnected(page: Page) {
  await page.route('**/api/mailchimp/connection', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConnectionDisconnected),
      });
    }
    if (route.request().method() === 'PUT') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConnectionConnected),
      });
    }
    return route.continue();
  });
  await page.route('**/api/mailchimp/audiences', jsonResponse(mockAudiences));
}

export async function mockMailchimpConnectionInvalidKey(page: Page) {
  await page.route('**/api/mailchimp/connection', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockConnectionDisconnected),
      });
    }
    if (route.request().method() === 'PUT') {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        // Real backend envelope (seed AppException handler): {error:{code,message}}
        // — extractErrorMessage's first branch parses error.message.
        body: JSON.stringify({
          error: { code: 'mailchimp_rejected', message: 'Chave API inválida ou datacenter incorreto.' },
        }),
      });
    }
    return route.continue();
  });
}

// ─── Contacts ────────────────────────────────────────────────────────────────

export async function mockMailchimpContacts(page: Page) {
  await page.route(/\/api\/mailchimp\/contacts(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockContacts),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(mockContacts.items[0]),
      });
    }
    return route.continue();
  });
  await page.route('**/api/mailchimp/contacts/*', (route) => {
    if (route.request().method() === 'PUT') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockContacts.items[0]),
      });
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });
}

// ─── Segments ────────────────────────────────────────────────────────────────

export async function mockMailchimpSegments(page: Page) {
  await page.route(/\/api\/mailchimp\/segments(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSegments),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ ...mockSegments.items[0], id: 99, name: 'Nova Lista' }),
      });
    }
    return route.continue();
  });
  await page.route(/\/api\/mailchimp\/segments\/\d+\/members(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSegmentMembers),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    }
    return route.continue();
  });
  await page.route(/\/api\/mailchimp\/segments\/\d+\/members\/.+/, (route) => {
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });
  await page.route(/\/api\/mailchimp\/segments\/\d+$/, (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSegments.items[0]),
      });
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });
}

export async function mockMailchimpSegmentsMemberError(page: Page) {
  await mockMailchimpSegments(page);
  // Override member POST with a 400 error (email not in audience)
  await page.route(/\/api\/mailchimp\/segments\/\d+\/members(\?.*)?$/, (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'mailchimp_rejected',
            message: 'O email não pertence à audiência.',
          },
        }),
      });
    }
    return route.continue();
  });
}

// ─── Templates ───────────────────────────────────────────────────────────────

export async function mockMailchimpTemplates(page: Page) {
  await page.route(/\/api\/mailchimp\/templates(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockTemplates),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          ...mockTemplates.items[0],
          id: 199,
          name: 'Novo Template',
        }),
      });
    }
    return route.continue();
  });
  await page.route(/\/api\/mailchimp\/templates\/\d+$/, (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockTemplates.items[0]),
      });
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });
}

// ─── Campaigns ───────────────────────────────────────────────────────────────

export async function mockMailchimpCampaigns(page: Page) {
  await page.route(/\/api\/mailchimp\/campaigns(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockCampaigns),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(mockCampaigns.items[0]),
      });
    }
    return route.continue();
  });
  await page.route(/\/api\/mailchimp\/campaigns\/[^/]+$/, (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockCampaigns.items[0]),
      });
    }
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    return route.continue();
  });
  await page.route(/\/api\/mailchimp\/campaigns\/[^/]+\/actions\/send$/, (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...mockCampaigns.items[0], status: 'sent' }),
    });
  });
  await page.route(/\/api\/mailchimp\/campaigns\/[^/]+\/actions\/schedule$/, (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...mockCampaigns.items[0], status: 'schedule' }),
    });
  });
  await page.route(/\/api\/mailchimp\/campaigns\/[^/]+\/actions\/unschedule$/, (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...mockCampaigns.items[0], status: 'save' }),
    });
  });
  await page.route(/\/api\/mailchimp\/campaigns\/[^/]+\/actions\/test$/, (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
}
