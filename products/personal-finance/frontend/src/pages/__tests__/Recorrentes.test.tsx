/**
 * Recorrentes page — scheduler-artifact banner unit tests
 * (PF Phase 5 PF-5).
 *
 * Tests the per-row "Próxima execução automática" banner that surfaces
 * `is_automatico=true` recurring rules + their `proxima_data`. The full
 * page wires 5 hooks + 2 modals; here we exercise the `<RecorrenteRow>`
 * sub-component directly to avoid that orchestration cost — the banner
 * decision lives entirely inside the row.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Break the import chain — the page module pulls in seed/infra + react-router
// transitively via the hooks; we only want to exercise <RecorrenteRow/>.
// Mocks must be declared BEFORE the SUT import so vitest's hoisting kicks in.
vi.mock("@/hooks/useRecorrentes", () => ({
  useRecorrentes: () => ({ data: [], isLoading: false }),
  useCreateRecorrente: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUpdateRecorrente: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useDeleteRecorrente: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useExecutarPendentes: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useExecutarUnico: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/useContas", () => ({
  useContas: () => ({ data: [], isLoading: false }),
}));
vi.mock("@/hooks/useCategorias", () => ({
  useCategorias: () => ({ data: [], isLoading: false }),
}));
vi.mock("@/components/Modal", () => ({ default: () => null }));
vi.mock("@/components/ConfirmDialog", () => ({ default: () => null }));

import { RecorrenteRow } from "@/pages/Recorrentes";
import type { Recorrente } from "@/types";

function makeRecorrente(overrides: Partial<Recorrente> = {}): Recorrente {
  return {
    id: "rec-1",
    nome: "Aluguel",
    valor: 2500,
    tipo: "despesa",
    frequencia: "mensal",
    is_automatico: false,
    lembrete_dias: 3,
    ativo: true,
    proxima_data: "2026-06-01",
    ...overrides,
  };
}

describe("RecorrenteRow scheduler banner (PF Phase 5 PF-5)", () => {
  const noop = vi.fn();

  it("renders the 'Auto' badge + next-run line when is_automatico=true", () => {
    render(
      <RecorrenteRow
        item={makeRecorrente({ is_automatico: true })}
        onEdit={noop}
        onDelete={noop}
        onExecute={noop}
      />,
    );

    expect(screen.getByTestId("recorrente-auto-badge")).not.toBeNull();
    const nextRun = screen.getByTestId("recorrente-next-run");
    expect(nextRun).not.toBeNull();
    expect(nextRun.textContent).toContain("Próxima execução automática");
  });

  it("hides the Auto badge + next-run line when is_automatico=false", () => {
    render(
      <RecorrenteRow
        item={makeRecorrente({ is_automatico: false })}
        onEdit={noop}
        onDelete={noop}
        onExecute={noop}
      />,
    );

    expect(screen.queryByTestId("recorrente-auto-badge")).toBeNull();
    expect(screen.queryByTestId("recorrente-next-run")).toBeNull();
  });

  it("hides the next-run line when is_automatico=true but proxima_data is missing", () => {
    render(
      <RecorrenteRow
        item={makeRecorrente({ is_automatico: true, proxima_data: undefined })}
        onEdit={noop}
        onDelete={noop}
        onExecute={noop}
      />,
    );

    // Auto badge still visible (the rule IS automatic — we just don't know when).
    expect(screen.getByTestId("recorrente-auto-badge")).not.toBeNull();
    expect(screen.queryByTestId("recorrente-next-run")).toBeNull();
  });
});
