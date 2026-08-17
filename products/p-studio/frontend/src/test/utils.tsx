/* Helpers compartilhados dos testes de página/componente. */
import { type ReactElement, type ReactNode } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/** Mostra o pathname atual — para asserções de navegação. */
export function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = "/",
    path,
    extraRoutes,
  }: { route?: string; path?: string; extraRoutes?: ReactNode } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        {path ? (
          <>
            <Routes>
              <Route path={path} element={ui} />
              {extraRoutes}
            </Routes>
            <LocationDisplay />
          </>
        ) : (
          ui
        )}
      </MemoryRouter>
    </QueryClientProvider>
  );
}
