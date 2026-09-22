import type { Page } from '@playwright/test';

import { test, expect } from '../fixtures/auth.fixture';
import { mockDashboardAPIs } from '../fixtures/api-mocks';
import { mockSupabaseQueries } from '../fixtures/supabase-mocks';

/**
 * Expand the desktop sidebar rail before asserting on TEXT.
 *
 * Since the seed shell's hover rail (`AppShell.tsx`, 2026-08-27) the sidebar
 * rests icon-only at this suite's 1280px viewport: brand subtitle and group
 * labels are `max-w-0 opacity-0` until the rail is hovered or focused.
 *
 * Only TEXT assertions need this. Nav LINKS stay visible collapsed — the `<a>`
 * is still rendered and `aria-label` carries the accessible name — which is
 * why `getByRole('link', ...)` assertions below are untouched, and why that
 * distinction is worth keeping visible rather than hovering everywhere.
 */
async function expandSidebarRail(page: Page) {
  const rail = page.locator('aside[data-rail-expanded]');
  // 🔴 This mouse.move is LOAD-BEARING. Do not delete it as noise.
  //
  // Playwright's pointer starts at (0,0). The collapsed rail is
  // `fixed inset-y-0 left-0 md:w-16`, i.e. it OCCUPIES x∈[0,64] — so the
  // pointer is ALREADY INSIDE it before the test does anything. `hover()`
  // then moves from (0,0) to the rail's centre: a move WITHIN the same
  // element, crossing no boundary, so Chromium emits no `mouseover` —
  // and AppShell's rail expands on React's DELEGATED `onMouseEnter`,
  // which is synthesised from `mouseover`. No crossing, no expansion, and
  // every text assertion below then fails against a `max-w-0 opacity-0`
  // label. Parking the pointer in the content area first restores the
  // boundary crossing.
  //
  // Measured 2026-09-20, same sha, `mcr.microsoft.com/playwright:*-noble`
  // (linux/amd64, as CI runs it): 1.62.1 passed, 1.63.0 failed all 3
  // retries, and adding this ONE line made 1.63.0 pass. It presents as a
  // version regression — the erp pin `~1.62.1` was an attempt to treat it
  // as one — but the latent bug is ours: the test never reliably crossed
  // into the element it hovers. Pinning only hid it.
  await page.mouse.move(640, 360);
  await rail.hover();
  await expect(rail).toHaveAttribute('data-rail-expanded', 'true');
}

/**
 * Open one nav group (topic) by its label.
 *
 * Since 2026-09-21 every group starts COLLAPSED by construction (seed
 * `Sidebar.tsx`); only the group holding the active route auto-opens. A
 * link inside any other group is not rendered visible until its group is
 * expanded — exactly what a user does — so the test does it too. The toggle
 * is a real <button aria-expanded> named by the group label.
 */
async function expandNavGroup(page: Page, label: string) {
  await expandSidebarRail(page);
  const trigger = page.getByRole('button', { name: label, exact: true });
  if ((await trigger.getAttribute('aria-expanded')) !== 'true') {
    await trigger.click();
  }
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
}

test.describe('Sidebar Navigation', () => {
  test('regular user sees nav items', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: false });
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Funil de Vendas' })).toBeVisible();
    // Gated by the `processos-venda` status_pagina row (migration 041) — if
    // that row is missing the item silently never renders, so this assertion
    // is the only thing that would catch it.
    await expect(page.getByRole('link', { name: 'Processos de Venda' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Clientes' })).toBeVisible();
    // Nav now distinguishes "Metas individuais" from "Metas da Empresa" — use
    // the exact item name to avoid a strict-mode multi-match on "Metas".
    await expandNavGroup(page, 'Metas & Desempenho');
    await expect(page.getByRole('link', { name: 'Metas individuais' })).toBeVisible();
    await expandNavGroup(page, 'Comercial');
    await expect(page.getByRole('link', { name: /Imóveis|Imoveis/ })).toBeVisible();
  });

  test('shows brand header', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expandSidebarRail(page);
    // 🔴 The HEADING, not `getByText('ONE')`.
    //
    // `getByText` matches case-insensitive SUBSTRINGS, so "ONE" also matches
    // "Selec-ione" — the placeholder on the dashboard's two date-picker
    // buttons. That made the locator resolve to 3 elements and fail on strict
    // mode. The ambiguity was always there; it only surfaced once the rail
    // hover above added enough of a wait for the dashboard body to finish
    // rendering, where before this assertion raced ahead of it and happened to
    // find the brand alone.
    //
    // A race that passes is not a passing test, so this pins the element the
    // test is actually about rather than re-introducing the race.
    await expect(page.getByRole('heading', { name: 'ONE' })).toBeVisible();
  });

  test('admin user sees Painel de Controle section', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: true });
    await mockDashboardAPIs(page);
    // Roles now come from the backend (/api/profiles/me/roles), not Supabase
    // user_roles. Override the fixture default (['corretor']) — LIFO last wins.
    await page.route('**/api/profiles/me/roles', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: ['admin'] }) }),
    );
    await page.goto('/dashboard');

    await expandSidebarRail(page);
    await expect(page.getByText('Painel de Controle')).toBeVisible();
    await expandNavGroup(page, 'Painel de Controle');
    await expect(page.getByRole('link', { name: /Usuários|Usuarios/ })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
  });

  test('groups start collapsed except the one holding the active route', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: false });
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expandSidebarRail(page);
    // /dashboard lives in "Principal" — auto-opened so the user sees where they are.
    await expect(page.getByRole('button', { name: 'Principal', exact: true })).toHaveAttribute('aria-expanded', 'true');
    // Every other topic starts closed; the user expands what they need.
    await expect(page.getByRole('button', { name: 'Comercial', exact: true })).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByRole('link', { name: 'Permutas' })).toBeHidden();
  });

  test('regular user does not see admin section', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page, { isAdmin: false });
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    await expect(page.getByText('Painel de Controle')).toHaveCount(0);
  });

  test('active nav item is highlighted on Dashboard', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.goto('/dashboard');

    const dashboardLink = page.getByRole('link', { name: 'Dashboard' });
    await expect(dashboardLink).toBeVisible();
    await expect(dashboardLink).toHaveClass(/bg-primary/);
  });

  test('navigates to Funil when clicked', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.route('**/api/funil**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[]}' }),
    );
    await page.goto('/dashboard');

    await page.getByRole('link', { name: 'Funil' }).click();
    await expect(page).toHaveURL('/funil');
  });

  test('navigates to Clientes when clicked', async ({ authenticatedPage: page }) => {
    await mockSupabaseQueries(page);
    await mockDashboardAPIs(page);
    await page.route('**/api/clientes**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":[],"total":0,"page":1,"page_size":50}' }),
    );
    await page.goto('/dashboard');

    await page.getByRole('link', { name: 'Clientes' }).click();
    await expect(page).toHaveURL('/clientes');
  });
});
