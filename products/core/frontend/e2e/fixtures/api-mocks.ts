import type { Page } from '@playwright/test';
import { jsonResponse, paginatedResponse, successResponse, okResponse } from './helpers';
import {
  mockSubscription,
  mockProducts,
  mockPlans,
  mockBillingCatalog,
  mockCheckoutUrl,
  mockTeamMembers,
  mockInvitations,
  mockCreatedInvitation,
  mockRoles,
  mockOnboardingStatus,
  mockAdminStats,
  mockAdminOrganizations,
  mockAdminSubscriptions,
  mockAdminApiKeys,
} from './mock-data';

export async function mockDashboardAPIs(page: Page) {
  await page.route('**/api/subscriptions/me', successResponse(mockSubscription));
  // Deployment-status drives the launcher's "dev" badge. Default to
  // "nothing probed" so dashboard tests stay off the real backend; a
  // specific test overrides this (a route registered later wins).
  await page.route('**/api/products/deployment-status', jsonResponse({ deployed: {} }));
}

export async function mockTeamAPIs(page: Page) {
  // Every team call carries `?org_id=` since multi-org S4b/S5 (the team page is scoped to one
  // org), and a string glob like '**/api/team' never matches a URL with a query string. Match
  // the PATH, query or not.
  const path = (p: string) => new RegExp(`/api/team${p}(\\?.*)?$`);
  await page.route(path(''), (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockTeamMembers }),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"OK"}' });
  });

  await page.route(path('/invitations'), jsonResponse({ data: mockInvitations }));
  await page.route(path('/invitations/[^/?]+'), okResponse());
  // The real route answers the created invitation as `{ data }` (core routers/team.py); the
  // invite hook commits that row into the pending list, so a `{ message }` mock breaks it.
  await page.route(path('/invite'), jsonResponse({ data: mockCreatedInvitation }));
  await page.route(path('/[^/?]+/role'), okResponse());
  await page.route('**/api/roles', jsonResponse({ data: mockRoles }));
}

export async function mockPricingAPIs(page: Page) {
  // /api/plans still feeds Onboarding's plan step.
  await page.route('**/api/plans', jsonResponse({ data: mockPlans }));
  await page.route('**/api/billing/plans', jsonResponse({ data: mockBillingCatalog }));
  await page.route('**/api/billing/subscribe', jsonResponse({
    data: { subscription_id: 'sub-e2e', checkout_url: mockCheckoutUrl, gateway: 'stripe', mode: 'test', pix_qr: null },
  }));
  // The hosted checkout page itself — answered locally so the redirect is
  // observable without leaving the test sandbox.
  await page.route(`${mockCheckoutUrl}**`, (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Stripe Checkout (mock)</h1>' }),
  );
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
