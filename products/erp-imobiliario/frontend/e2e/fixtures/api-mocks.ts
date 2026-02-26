import type { Page } from '@playwright/test';
import { jsonResponse, paginatedResponse, successResponse, okResponse } from './helpers';
import {
  mockMetas,
  mockFunilColunas,
  mockClientes,
  mockImoveis,
  mockMatches,
} from './mock-data';

export async function mockDashboardAPIs(page: Page) {
  await page.route('**/api/metas**', jsonResponse({ data: mockMetas, total: mockMetas.length, page: 1, page_size: 50 }));
}

export async function mockFunilAPIs(page: Page) {
  await page.route('**/api/funil**', jsonResponse({ data: mockFunilColunas }));
  await page.route('**/api/clientes/*/mover-etapa', okResponse());
}

export async function mockClientesAPIs(page: Page) {
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
