import type { Page } from '@playwright/test';
import { jsonResponse, paginatedResponse, successResponse, okResponse } from './helpers';
import {
  mockMetas,
  mockFunilColunas,
  mockProcessosColunas,
  mockProcessoStages,
  mockFunilStages,
  mockClientes,
  mockImoveis,
  mockMatches,
} from './mock-data';

export async function mockDashboardAPIs(page: Page) {
  await page.route('**/api/metas**', jsonResponse({ data: mockMetas, total: mockMetas.length, page: 1, page_size: 50 }));
}

export async function mockFunilAPIs(page: Page) {
  // Registered BEFORE the board route: Playwright matches in registration
  // order, and `**/api/funil**` would otherwise swallow `/api/funil/etapas`.
  await page.route('**/api/funil/etapas**', jsonResponse({ data: mockFunilStages }));
  await page.route('**/api/funil**', jsonResponse({ data: mockFunilColunas }));
  // Stage moves go through the NEGOCIAÇÃO now (roadmap P1.5.4) — the
  // cliente-level endpoint no longer drives the board.
  await page.route('**/api/negociacoes-venda/*/mover-etapa', okResponse());
  await page.route(
    '**/api/negociacoes-venda/*/aceitar-proposta',
    jsonResponse({
      data: {
        negociacao: { id: 'neg-002', status: 'aceita' },
        processo: { id: 'proc-001', etapa: 'elaboracao_contrato' },
        already_accepted: false,
      },
    }),
  );
  // The cliente-detail page asks for a cliente's open deals.
  await page.route(/\/api\/negociacoes-venda(\?.*)?$/, jsonResponse({ data: [] }));
}

export async function mockProcessosAPIs(page: Page) {
  // Stage definitions — the board and its editor read these since migration
  // 042. MUST be registered BEFORE the catch-all board route below: Playwright
  // matches routes in registration order, and `**/api/processos-venda**` would
  // otherwise swallow `/etapas` and answer it with the column payload.
  await page.route('**/api/processos-venda/etapas**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: mockProcessoStages }),
    }),
  );

  await page.route('**/api/processos-venda**', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'proc-001', etapa: 'assinatura' } }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: mockProcessosColunas }),
    });
  });
}

/**
 * The Funil stage list. Extracted because SEVERAL pages need it now: any page
 * rendering `FiltrosFunil` (Funil, Clientes) reads the DB-driven stage list
 * since migration 042, and a test that declares its own routes still has to
 * serve this one.
 */
export async function mockFunilStagesRoute(page: Page) {
  await page.route('**/api/funil/etapas**', jsonResponse({ data: mockFunilStages }));
}

export async function mockClientesAPIs(page: Page) {
  await mockFunilStagesRoute(page);

  // Use regex to match /api/clientes with or without query params (but NOT /api/clientes/*)
  await page.route(/\/api\/clientes(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockClientes, total: mockClientes.length, page: 1, page_size: 50 }),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'cli-new', nome: 'Novo Cliente', ...mockClientes[0] } }),
      });
    }
    return route.continue();
  });
  await page.route('**/api/clientes/*', (route) => {
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"OK"}' });
    }
    if (route.request().method() === 'PATCH') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":{}}' });
    }
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockClientes[0] }),
      });
    }
    return route.continue();
  });
}

export async function mockImoveisAPIs(page: Page) {
  await page.route('**/api/ativos**', jsonResponse({ data: mockImoveis, total: mockImoveis.length, page: 1, page_size: 50 }));
}

export async function mockMatchingAPIs(page: Page) {
  await page.route('**/api/matching', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockMatches, total: mockMatches.length, page: 1, page_size: 50 }),
      });
    }
    return route.continue();
  });
  await page.route('**/api/matching/gerar**', jsonResponse({ data: mockMatches, message: 'Matches gerados com sucesso' }));
  await page.route('**/api/matching/embed**', okResponse('Embedding concluído'));
  await page.route('**/api/matching/embed-batch**', okResponse('Batch embedding concluído'));
  await page.route('**/api/matching/*', (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { ...mockMatches[0], status: 'aceito' } }),
      });
    }
    return route.continue();
  });
}

export async function mockMetasAPIs(page: Page) {
  await page.route('**/api/metas**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: mockMetas, total: mockMetas.length, page: 1, page_size: 50 }),
      });
    }
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'meta-new', ...mockMetas[0] } }),
      });
    }
    return route.continue();
  });
}
