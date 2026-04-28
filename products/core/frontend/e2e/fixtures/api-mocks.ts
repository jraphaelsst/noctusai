import type { Page } from '@playwright/test';
import { jsonResponse, paginatedResponse, successResponse, okResponse } from './helpers';
import {
  mockSubscription,
  mockProducts,
  mockPlans,
  mockTeamMembers,
  mockInvitations,
  mockRoles,
  mockOnboardingStatus,
  mockAdminStats,
  mockAdminOrganizations,
  mockAdminSubscriptions,
  mockAdminApiKeys,
} from './mock-data';

export async function mockDashboardAPIs(page: Page) {
  await page.route('**/api/subscriptions/me', successResponse(mockSubscription));
}

export async function mockTeamAPIs(page: Page) {
  await page.route('**/api/team', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockTeamMembers }),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"OK"}' });
  });

  await page.route('**/api/team/invitations', jsonResponse({ data: mockInvitations }));
  await page.route('**/api/team/invitations/*', okResponse());
  await page.route('**/api/team/invite', okResponse('Convite enviado'));
  await page.route('**/api/team/*/role', okResponse());
  await page.route('**/api/roles', jsonResponse({ data: mockRoles }));
}

export async function mockPricingAPIs(page: Page) {
  await page.route('**/api/plans', jsonResponse({ data: mockPlans }));
  await page.route('**/api/billing/checkout', jsonResponse({ checkout_url: 'https://checkout.stripe.com/test' }));
}

export async function mockOnboardingAPIs(page: Page) {
  await page.route('**/api/onboarding/status', successResponse(mockOnboardingStatus));
  await page.route('**/api/onboarding/complete', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          steps: {
            company_details: true,
            choose_plan: false,
            invite_team: false,
            enable_product: false,
          },
          onboarding_completed: false,
          progress: { completed: 1, total: 4, percentage: 25 },
        },
      }),
    }),
  );
}

export async function mockAdminAPIs(page: Page) {
  await page.route('**/api/admin/stats', jsonResponse(mockAdminStats));
  await page.route('**/api/organizations', paginatedResponse(mockAdminOrganizations));
  await page.route('**/api/subscriptions', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockAdminSubscriptions, total: 1, page: 1, page_size: 50 }),
      });
    }
    return route.fulfill({ status: 201, contentType: 'application/json', body: '{"data":{}}' });
  });
  await page.route('**/api/admin/api-keys', jsonResponse({ data: mockAdminApiKeys }));
  await page.route('**/api/api-keys', okResponse());
  await page.route('**/api/plans', jsonResponse({ data: mockPlans }));
  await page.route('**/api/webhooks', jsonResponse({ data: [] }));
  await page.route('**/api/admin/analytics/overview', jsonResponse({ data: { mrr: 5980, arr: 71760, active_orgs: 35 } }));
  await page.route('**/api/admin/analytics/revenue', jsonResponse({ data: [] }));
  await page.route('**/api/admin/analytics/tenants', jsonResponse({ data: [] }));
  await page.route('**/api/settings/platform', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [] }),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":{}}' });
  });
}
