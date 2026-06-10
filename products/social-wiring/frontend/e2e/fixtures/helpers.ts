import type { Route } from '@playwright/test';

export function jsonResponse(data: unknown, status = 200) {
  return (route: Route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(data),
    });
}

export function createdResponse(data: unknown) {
  return (route: Route) =>
    route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(data),
    });
}

export function noContentResponse() {
  return (route: Route) =>
    route.fulfill({ status: 204, body: '' });
}

export function errorResponse(code: string, message: string, status = 400) {
  return (route: Route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { code, message } }),
    });
}
