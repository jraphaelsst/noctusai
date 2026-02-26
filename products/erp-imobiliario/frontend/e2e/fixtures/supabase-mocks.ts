import type { Page } from '@playwright/test';
import { mockStatusPaginas, mockAdminStatusPaginas, mockUserRoles, mockAdminUserRoles } from './mock-data';

/**
 * Mock all Supabase PostgREST queries used by the layout (Header + Sidebar + AuthProvider).
 *
 * Playwright uses LIFO route matching — the LAST registered route that matches wins.
 * We register the catch-all FIRST, then specific table patterns AFTER,
 * so specific routes always take priority.
 */
export async function mockSupabaseQueries(page: Page, options: { isAdmin?: boolean } = {}) {
  const { isAdmin = false } = options;

  // 1. Catch-all for any unhandled PostgREST calls (lowest priority — registered first)
  await page.route('**/rest/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
  );

  // 2. user_actions_log — AuthProvider login/logout logging
  await page.route('**/rest/v1/user_actions_log**', (route) =>
    route.fulfill({ status: 201, contentType: 'application/json', body: '[]' }),
  );

  // 3. status_pagina — Sidebar page status badges
  await page.route('**/rest/v1/status_pagina**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(isAdmin ? mockAdminStatusPaginas : mockStatusPaginas),
    }),
  );

  // 4. user_roles — useUserRole(), useUserRoles(), useIsAdmin()
  await page.route('**/rest/v1/user_roles**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(isAdmin ? mockAdminUserRoles : mockUserRoles),
    }),
  );

  // 5. profiles — useUserProfile() uses .single() which sends vnd.pgrst.object Accept header
  //    Also used by AuthProvider to PATCH last_activity_at
  //    (highest priority — registered last)
  await page.route('**/rest/v1/profiles**', (route) => {
    const method = route.request().method();
    const accept = route.request().headers()['accept'] || '';

    if (method === 'GET') {
      const isSingleRequest = accept.includes('vnd.pgrst.object');
      const profileObj = {
        id: 'user-001',
        nome: 'Rafael Oliveira',
        email: 'rafael@imobiliaria.com',
        telefone: '(11) 98765-4321',
        avatar: null,
        cargo: 'Corretor',
        last_activity_at: '2026-02-26T10:00:00Z',
      };

      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: isSingleRequest ? JSON.stringify(profileObj) : JSON.stringify([profileObj]),
      });
    }

    // PATCH (update last_activity_at) — just accept it
    return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
}
