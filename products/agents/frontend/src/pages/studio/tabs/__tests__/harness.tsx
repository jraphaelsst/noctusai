/** Shared test harness for the Julia v2 Studio tabs: real seed ApiClient over a faked `fetch`. */
import React from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "@noctusai/lib/components";

export function renderWith(ui: React.ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </ConfirmProvider>
    </QueryClientProvider>,
  );
}
