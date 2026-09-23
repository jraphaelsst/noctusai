/**
 * ProvenienciaContainer — the "Proveniência" fetch owner.
 *
 * Coverage: `aberto` reaches `useProveniencia` straight through (the lazy
 * gate), the two lying-loading-state signals (`showSkeleton`/`isRefreshing`)
 * are derived off `data` and never `isPending`/`isFetching` alone, and
 * `onRetry` calls the query's `refetch`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseProveniencia = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/hooks/useProveniencia", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/useProveniencia")>("@/hooks/useProveniencia");
  return {
    ...actual,
    useProveniencia: (...args: unknown[]) => mockUseProveniencia(...args),
  };
});

import { ProvenienciaContainer } from "./ProvenienciaContainer";

function queryResult(over: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isPending: true,
    isFetching: true,
    isError: false,
    refetch: mockRefetch,
    ...over,
  };
}

async function render(props: { clienteId: string; contratoId: string; aberto: boolean }) {
  const rtl = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  rtl.render(
    <MemoryRouter>
      <ProvenienciaContainer {...props} />
    </MemoryRouter>,
  );
  return rtl;
}

describe("ProvenienciaContainer", () => {
  it("passes `aberto` straight through to `useProveniencia`, alongside both ids", async () => {
    mockUseProveniencia.mockReturnValue(queryResult());
    await render({ clienteId: "cli1", contratoId: "c1", aberto: true });
    expect(mockUseProveniencia).toHaveBeenCalledWith("cli1", "c1", true);
  });

  it("🔴 showSkeleton is `isPending && !data`, never bare `isPending` — false mid-refetch, not a lie over good data", async () => {
    mockUseProveniencia.mockReturnValue(
      queryResult({
        isPending: false,
        isFetching: true,
        data: {
          items: [
            {
              entidade: "contrato",
              campo: "cpf",
              rotulo: "CPF",
              valor: "123",
              estado: "confirmado",
              origem: null,
              documento: null,
              em: null,
              fontes_possiveis: [],
            },
          ],
        },
      }),
    );
    const { screen } = await render({ clienteId: "cli1", contratoId: "c1", aberto: true });
    expect(screen.queryByTestId("proveniencia-skeleton")).toBeNull();
    expect(screen.getByTestId("proveniencia-lista").textContent).toContain("Atualizando…");
  });

  it("shows the skeleton only while pending AND no data yet", async () => {
    mockUseProveniencia.mockReturnValue(queryResult({ isPending: true, data: undefined }));
    const { screen } = await render({ clienteId: "cli1", contratoId: "c1", aberto: true });
    expect(screen.getByTestId("proveniencia-skeleton")).toBeTruthy();
  });

  it("onRetry calls the query's refetch", async () => {
    mockUseProveniencia.mockReturnValue(
      queryResult({ isPending: false, isFetching: false, isError: true, data: undefined }),
    );
    const { screen, fireEvent } = await render({ clienteId: "cli1", contratoId: "c1", aberto: true });
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(mockRefetch).toHaveBeenCalled();
  });
});
