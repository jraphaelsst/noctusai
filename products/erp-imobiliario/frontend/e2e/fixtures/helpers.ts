import type { Route } from '@playwright/test';

export function jsonResponse(data: unknown, status = 200) {
  return (route: Route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(data),
    });
}

export function paginatedResponse(data: unknown[], total?: number) {
  return jsonResponse({
    data,
    total: total ?? data.length,
    page: 1,
    page_size: 50,
  });
}

export function successResponse(data: unknown) {
  return jsonResponse({ data });
}

export function okResponse(message = 'OK') {
  return jsonResponse({ message });
}

export function errorResponse(detail: string, status = 400) {
  return (route: Route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify({ detail }),
    });
}
