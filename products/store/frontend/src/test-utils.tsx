/** Shared test helpers (not shipped): QueryClient wrapper, router, API stub. */
import React from "react";
import { vi } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PublicSettings } from "@/lib/api";

export const apiMock = { get: vi.fn(), post: vi.fn(), put: vi.fn(), upload: vi.fn() };

export const PUBLIC_SETTINGS: PublicSettings = {
  product_name: "Contrato Blindado de Compra e Venda",
  price_cents: 4700,
  items: [
    { label: "Contrato À Vista (Word + PDF)", anchor_cents: 9700 },
    { label: "Lista de 14 certidões e documentos", anchor_cents: 4700 },
  ],
  anchor_total_cents: 14400,
  guarantee_days: 7,
  author: { name: "Gilson", role: "corretor de imóveis", bio: "Bio do Gilson.", photo_url: null },
  checkout_enabled: true,
};

export function renderWithProviders(ui: React.ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
