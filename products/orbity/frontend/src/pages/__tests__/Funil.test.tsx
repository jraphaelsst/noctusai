/**
 * Funil (CRM kanban) — page-level render tests.
 *
 * These exist for TWO things the pre-organ board could not have passed:
 *
 * 1. **The board is the canonical organ, and its drag wiring is attached.**
 *    `data-kanban-card-id` / `data-kanban-column-id` are emitted by
 *    `@noctusai/lib`'s `KanbanCard` / `KanbanColumn` — they cannot appear
 *    unless the page really renders the organ with sortable cards and
 *    droppable columns. Asserting on them is the cheapest honest proof that
 *    the repoint took, short of a real browser drag.
 * 2. **The lying-loading race is closed.** `isPending === false` while
 *    `isFetching === true` (a background refetch, e.g. right after
 *    `seed-defaults` invalidates the funil) must NOT fall through to
 *    "Nenhuma etapa configurada" — that would offer to create stages for a
 *    funnel whose stages are already on the wire.
 *    (`KB § PATTERNS/frontend/lying-loading-state.md`)
 *
 * What these DON'T prove: that a pointer drag actually moves a card. jsdom
 * has no layout, so dnd-kit's collision detection has nothing to measure —
 * that leg is browser-only (the ERP pilot covers it in Playwright; orbity has
 * no e2e harness yet). The click test below is the nearest in-jsdom guard for
 * the related hazard: drag listeners swallowing ordinary card clicks.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
// Bare entry, NOT `/vitest`: the default entry extends `globalThis.expect`,
// which vitest injects under `globals: true`. See
// [[reference_lib_frontend_vitest_render_harness_gap]].
import "@testing-library/jest-dom";
import type { FunilStage, Lead } from "@/hooks/useCrm";

const { mockUseFunil, mockMoveMutate, idleMutation } = vi.hoisted(() => ({
  mockUseFunil: vi.fn(),
  mockMoveMutate: vi.fn(),
  // Hoisted alongside the mocks: `vi.mock`'s factory runs before module-scope
  // consts are initialised, so a plain top-level helper is a TDZ error there.
  idleMutation: () => ({ mutate: () => {}, isPending: false }),
}));

// The `@noctusai/lib/design-system` barrel this page imports (Button/Dialog/
// Badge/Input) transitively reaches `design-system/ai/useAIOutputFor`, which
// imports the seed infra singleton — and infra builds a Supabase client at
// MODULE LOAD, throwing without `VITE_SUPABASE_*`. Stubbing the infra seam is
// the intended isolation (the vitest factory ships the `@noctusai/seed/infra`
// subpath alias for exactly this), not a workaround: nothing on this page
// talks to Supabase.
vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    supabase: {},
    appConfig: {},
    useAuthStore: () => ({ user: null }),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    useNotificacoes: () => ({ data: [] }),
    useContagemNaoLidas: () => ({ data: 0 }),
    useMarcarComoLida: () => ({ mutate: noop }),
    useMarcarTodasComoLidas: () => ({ mutate: noop }),
    default: { api },
  };
});

vi.mock("@/hooks/useCrm", () => ({
  useFunil: () => mockUseFunil(),
  useCreateLead: idleMutation,
  useUpdateLead: idleMutation,
  useDeleteLead: idleMutation,
  useMoveLeadStage: () => ({ mutate: mockMoveMutate, isPending: false }),
  useSeedDefaultStages: idleMutation,
  useLeadActivities: () => ({ data: [], isPending: false }),
  useAddActivity: idleMutation,
}));

import Funil from "../Funil";

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeLead(overrides: Partial<Lead> & Pick<Lead, "id" | "name">): Lead {
  return {
    org_id: "org-1",
    email: null,
    phone: null,
    company: null,
    source: null,
    stage_id: "stage-novo",
    temperature: null,
    qualification_score: null,
    qualification_source: null,
    value: null,
    owner_id: null,
    next_contact: null,
    client_id: null,
    custom_fields: {},
    tags: [],
    won_at: null,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

const LEAD_A = makeLead({
  id: "lead-a",
  name: "Ana Prospect",
  email: "ana@exemplo.com",
  company: "Acme",
  value: 1000,
});
const LEAD_B = makeLead({ id: "lead-b", name: "Bruno Prospect", value: 500 });

const STAGES: FunilStage[] = [
  {
    stage: {
      id: "stage-novo",
      org_id: "org-1",
      name: "Novo",
      position: 0,
      color: "#3b82f6",
      created_at: "2026-07-01T00:00:00Z",
    },
    leads: [LEAD_A, LEAD_B],
  },
  {
    stage: {
      id: "stage-proposta",
      org_id: "org-1",
      name: "Proposta",
      position: 1,
      color: null,
      created_at: "2026-07-01T00:00:00Z",
    },
    leads: [],
  },
];

function funilQuery(overrides: Record<string, unknown> = {}) {
  return {
    data: STAGES,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── The organ is really mounted ─────────────────────────────────────────────

describe("Funil — canonical KanbanBoard organ", () => {
  it("renders one droppable column per stage, tagged by the organ", () => {
    mockUseFunil.mockReturnValue(funilQuery());
    const { container } = render(<Funil />);

    const columns = container.querySelectorAll("[data-kanban-column-id]");
    expect(columns).toHaveLength(2);
    expect(
      Array.from(columns).map((c) => c.getAttribute("data-kanban-column-id"))
    ).toEqual(["stage-novo", "stage-proposta"]);
  });

  it("renders each lead as a sortable card carrying its lead id", () => {
    mockUseFunil.mockReturnValue(funilQuery());
    const { container } = render(<Funil />);

    const cards = container.querySelectorAll("[data-kanban-card-id]");
    expect(Array.from(cards).map((c) => c.getAttribute("data-kanban-card-id"))).toEqual([
      "lead-a",
      "lead-b",
    ]);
    expect(screen.getByText("Ana Prospect")).toBeInTheDocument();
    expect(screen.getByText("Bruno Prospect")).toBeInTheDocument();
  });

  it("keeps the column chrome the pre-organ board had: name, count, subtotal", () => {
    mockUseFunil.mockReturnValue(funilQuery());
    const { container } = render(<Funil />);

    // Scope to the column the organ rendered, so this also proves the header
    // landed in the RIGHT column — a page-wide getByText would happily match
    // the page header's "… em pipeline" total instead.
    const novo = container.querySelector('[data-kanban-column-id="stage-novo"]')!
      .parentElement!;
    expect(within(novo).getByText("Novo")).toBeInTheDocument();
    expect(within(novo).getByText("2")).toBeInTheDocument();
    // R$1.000 + R$500 → the column subtotal.
    expect(within(novo).getByText(/1\.500/)).toBeInTheDocument();

    const proposta = container.querySelector('[data-kanban-column-id="stage-proposta"]')!
      .parentElement!;
    expect(within(proposta).getByText("Proposta")).toBeInTheDocument();
    expect(within(proposta).getByText("0")).toBeInTheDocument();
    // No leads ⇒ no subtotal row at all (not "R$ 0,00").
    expect(within(proposta).queryByText(/R\$/)).not.toBeInTheDocument();
  });

  it("shows the consumer's empty-column copy, not the organ's default", () => {
    mockUseFunil.mockReturnValue(funilQuery());
    render(<Funil />);

    expect(screen.getByText("Nenhum lead")).toBeInTheDocument();
    expect(screen.queryByText("Nenhum item nesta etapa")).not.toBeInTheDocument();
  });

  it("still opens the detail panel on click — drag listeners do not swallow it", () => {
    mockUseFunil.mockReturnValue(funilQuery());
    render(<Funil />);

    fireEvent.click(screen.getByText("Ana Prospect"));

    // The slide-over renders contact details the card itself never shows.
    expect(screen.getByText("ana@exemplo.com")).toBeInTheDocument();
    expect(screen.getByText("Atividades")).toBeInTheDocument();
  });
});

// ─── The lying-loading race ──────────────────────────────────────────────────

describe("Funil — loading vs empty", () => {
  it("shows the skeleton on first load", () => {
    mockUseFunil.mockReturnValue(funilQuery({ data: undefined, isPending: true }));
    const { container } = render(<Funil />);

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("Nenhuma etapa configurada")).not.toBeInTheDocument();
  });

  it("does NOT offer 'criar etapas padrão' while a refetch is still in flight", () => {
    // isPending false + isFetching true is exactly what TanStack v5 reports
    // mid-background-refetch — the state in which `isLoading` lies.
    mockUseFunil.mockReturnValue(
      funilQuery({ data: [], isPending: false, isFetching: true })
    );
    const { container } = render(<Funil />);

    expect(screen.queryByText("Nenhuma etapa configurada")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /criar etapas padrão/i })).not.toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("offers 'criar etapas padrão' once a settled fetch really returned no stages", () => {
    mockUseFunil.mockReturnValue(
      funilQuery({ data: [], isPending: false, isFetching: false })
    );
    render(<Funil />);

    expect(screen.getByText("Nenhuma etapa configurada")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /criar etapas padrão/i })).toBeInTheDocument();
  });

  it("surfaces the error state with a retry", () => {
    mockUseFunil.mockReturnValue(
      funilQuery({ data: undefined, isError: true, error: new Error("boom") })
    );
    render(<Funil />);

    expect(screen.getByText("Falha ao carregar o funil")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
