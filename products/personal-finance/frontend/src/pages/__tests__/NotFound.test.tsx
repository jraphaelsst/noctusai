/**
 * NotFound page — static-content sanity test (PF Phase 6.c).
 *
 * NotFound is intentionally static — no useQuery, no api calls. The test
 * just confirms the 404 banner + the two navigation actions render.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Spy useNavigate without re-importing react-router-dom (the importActual
// path resolves to a stray UMD bundle under this monorepo layout). The
// MemoryRouter wrapper provides a real router context; we override only
// the navigate hook via the spy.
const navigateSpy = vi.fn();
vi.mock("react-router-dom", () => ({
  // BrowserRouter / MemoryRouter not needed here — NotFound consumes only
  // useNavigate; we still wrap in MemoryRouter (mocked passthrough) so the
  // existing wrapper imports don't break.
  MemoryRouter: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  useNavigate: () => navigateSpy,
}));

import NotFound from "@/pages/NotFound";

describe("NotFound page (PF Phase 6.c — static)", () => {
  it("renders the 404 headline + 'Pagina nao encontrada' message", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );
    expect(screen.getByText("404")).not.toBeNull();
    expect(screen.getByText(/Pagina nao encontrada/i)).not.toBeNull();
  });

  it("navigates back when 'Voltar' is clicked", () => {
    navigateSpy.mockClear();
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText(/Voltar/i));
    expect(navigateSpy).toHaveBeenCalledWith(-1);
  });

  it("navigates to '/' when 'Ir ao Inicio' is clicked", () => {
    navigateSpy.mockClear();
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText(/Ir ao Inicio/i));
    expect(navigateSpy).toHaveBeenCalledWith("/");
  });
});
