/**
 * `<CalendarioMes/>` — smoke finding 6 (no weekday headers, no leading offset),
 * the phone agenda list (R0), the auto-generated badge and the `clienteId`
 * filter reaching the calendar query (R9).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  useAuthStore: () => ({ user: { id: "u" } }),
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn();
  const useMutation = vi.fn(() => ({ mutate: vi.fn(), isPending: false, isError: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient, keepPreviousData: (p: unknown) => p };
});

import { useQuery } from "@tanstack/react-query";
import { CalendarioMes } from "./CalendarioMes";
import type { Pauta } from "@/hooks/usePautas";

const mockUseQuery = vi.mocked(useQuery);

const pauta = (over: Partial<Pauta>): Pauta => ({
  id: "p1",
  org_id: "o",
  cliente_id: "c1",
  marca_id: null,
  titulo: "Post institucional",
  formato: "feed",
  funil: null,
  linha_editorial: null,
  copy_texto: null,
  direcao_video: null,
  canal: null,
  data_publicacao: new Date(2026, 3, 8, 9, 0).toISOString(),
  caracteres_copy: 0,
  ...over,
});

function mockCalendario(itens: Pauta[] | undefined, extra: Record<string, unknown> = {}) {
  mockUseQuery.mockImplementation(((opts: { queryKey?: unknown[] }) => {
    if (opts?.queryKey?.includes("calendario")) {
      return {
        data: itens ? { inicio: "", fim: "", itens } : undefined,
        isPending: !itens,
        isFetching: false,
        error: null,
        ...extra,
      };
    }
    return { data: { itens: [], total: 0 }, isPending: false, isFetching: false, error: null };
  }) as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  // April 2026 starts on a WEDNESDAY → two leading empty cells, Monday-first.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 3, 15, 12, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("CalendarioMes — month grid", () => {
  it("renders Monday-first weekday headers", () => {
    mockCalendario([]);
    render(<CalendarioMes />);
    const headers = within(screen.getByTestId("calendario-grade"))
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]);
  });

  it("offsets day 1 under its real weekday (Wednesday for April 2026)", () => {
    mockCalendario([]);
    const { container } = render(<CalendarioMes />);
    const grade = container.querySelectorAll('[data-testid="calendario-grade"] > div')[1];
    const celulas = Array.from(grade.children);
    expect(celulas[0]).toHaveAttribute("aria-hidden");
    expect(celulas[1]).toHaveAttribute("aria-hidden");
    expect(celulas[2]).toHaveAttribute("data-dia", "1");
    expect(celulas.length % 7).toBe(0);
  });

  it("badges a pauta generated from an accepted orçamento", () => {
    mockCalendario([pauta({ id: "auto", titulo: "Reels recorrente", gerada_automaticamente: true })]);
    render(<CalendarioMes />);
    expect(within(screen.getByTestId("calendario-agenda")).getByText("auto")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("calendario-grade")).getByLabelText("Gerada do orçamento"),
    ).toBeInTheDocument();
  });
});

describe("CalendarioMes — phone agenda (R0)", () => {
  it("lists only the days that have pautas, with the weekday spelled out", () => {
    mockCalendario([
      pauta({ id: "a", titulo: "Post A", data_publicacao: new Date(2026, 3, 8, 9).toISOString() }),
      pauta({ id: "b", titulo: "Post B", data_publicacao: new Date(2026, 3, 20, 9).toISOString() }),
    ]);
    render(<CalendarioMes />);
    const agenda = screen.getByTestId("calendario-agenda");
    expect(agenda).toHaveClass("sm:hidden");
    const dias = within(agenda).getAllByRole("listitem").filter((li) => li.tagName === "LI" && li.querySelector("p"));
    expect(dias).toHaveLength(2);
    expect(dias[0]).toHaveTextContent(/quarta-feira/i);
    expect(dias[0]).toHaveTextContent("Post A");
  });

  it("says so when the month has nothing scheduled", () => {
    mockCalendario([]);
    render(<CalendarioMes />);
    expect(within(screen.getByTestId("calendario-agenda")).getByText(/Nenhuma pauta agendada/)).toBeInTheDocument();
  });
});

describe("CalendarioMes — states + filter", () => {
  it("shows a skeleton on first load and an error when the query fails", () => {
    mockCalendario(undefined);
    const { unmount } = render(<CalendarioMes />);
    expect(screen.queryByTestId("calendario-grade")).not.toBeInTheDocument();
    unmount();
    mockCalendario(undefined, { isPending: false, error: new Error("x") });
    render(<CalendarioMes />);
    expect(screen.getByText("Não foi possível carregar o calendário.")).toBeInTheDocument();
  });

  it("scopes the calendar query to clienteId and hides the cliente picker", () => {
    mockCalendario([]);
    render(<CalendarioMes clienteId="c9" />);
    const chave = mockUseQuery.mock.calls
      .map(([o]) => (o as { queryKey: unknown[] }).queryKey)
      .find((k) => k.includes("calendario"));
    expect(chave).toContain("c9");
    expect(screen.queryByLabelText("Cliente")).not.toBeInTheDocument();
  });
});
