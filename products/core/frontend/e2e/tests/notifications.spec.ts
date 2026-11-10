import { test, expect } from '../fixtures/auth.fixture';
import { mockDashboardAPIs } from '../fixtures/api-mocks';
import { jsonResponse } from '../fixtures/helpers';

/**
 * The notification bell opens, the dropdown is actually on top (hit-test, not just "in the DOM"),
 * and the list is what the API returned. Regression for "the bell doesn't open" (2026-11-04).
 */
const lista = [
  { id: 'n1', org_id: 'o', user_id: 'u', tipo: 'lead_novo', titulo: 'Novo lead: Maria', mensagem: 'Chegou agora', is_read: false, created_at: new Date().toISOString(), metadata: { categoria: 'operacional', link: '/leads' } },
];

async function mockNotificacoes(page: import('@playwright/test').Page) {
  await page.route(/\/api\/notificacoes\/contagem/, jsonResponse({ nao_lidas: 1 }));
  await page.route(/\/api\/notificacoes(\?.*)?$/, jsonResponse({ data: lista, pagination: { total: 1 } }));
}

async function bellOpensOnTop(page: import('@playwright/test').Page) {
  await page.getByLabel('Notificacoes').first().click();
  const item = page.getByTestId('notificacao-n1');
  await expect(item).toBeVisible();
  // Visible in the DOM is not enough: something stacked above it would swallow the click.
  const onTop = await item.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && el.contains(hit);
  });
  expect(onTop).toBe(true);
}

test.describe('Notification bell', () => {
  test('opens on the dashboard', async ({ authenticatedPage: page }) => {
    await mockDashboardAPIs(page);
    await mockNotificacoes(page);
    await page.goto('/');
    await bellOpensOnTop(page);
  });

  test('is present and opens on a core page that has no header of its own', async ({ authenticatedPage: page }) => {
    await mockNotificacoes(page);
    await page.goto('/settings');
    await bellOpensOnTop(page);
  });
});

test.describe('Operational pop-up', () => {
  test('a notice created after load pops up neutral with an X; the backlog never does', async ({ authenticatedPage: page }) => {
    let servidor = [...lista];
    let contagens = 0;
    let listas = 0;
    // The bell polls ONLY the count (60 s, request budget 2026-11-10) and re-reads the list when
    // (nao_lidas, ultima_id) moves — so the count mock must follow the server, like the real one does.
    await page.route(/\/api\/notificacoes\/contagem/, (route) => {
      contagens += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ nao_lidas: servidor.length, ultima_id: servidor[0]?.id ?? null }),
      });
    });
    await page.route(/\/api\/notificacoes(\?.*)?$/, (route) => {
      listas += 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: servidor, pagination: { total: servidor.length } }) });
    });
    await page.clock.install();
    await page.goto('/settings');
    // The first load happens in REAL time (auth bootstrap); the fake clock cannot hurry it. Wait until
    // the backlog was actually served, or the "new" notice lands in the first load and never toasts.
    await expect.poll(() => contagens > 0 && listas > 0).toBe(true);
    await page.clock.runFor(1000);
    await expect(page.getByTestId('toast-operacional')).toHaveCount(0); // backlog: bell only
    servidor = [{ ...lista[0], id: 'n2', titulo: 'Novo lead: Joao', created_at: new Date(Date.now() + 60_000).toISOString() }, ...servidor];
    await page.clock.runFor(61_000); // one count poll (NOTIFICATION_POLL_MS = 60 s) → list re-read
    const toast = page.getByTestId('toast-operacional');
    await expect(toast).toHaveCount(1);
    await expect(toast).toContainText('Novo lead: Joao');
    await toast.getByLabel('Fechar notificação').click();
    await expect(toast).toHaveCount(0);
  });
});
