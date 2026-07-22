/**
 * Configuracao.test.tsx — Leads "Configuração" subtab.
 *
 * Focus: the state-quadrant gap this file closes (previously NO loading /
 * error handling at all — an empty list rendered silently during the
 * initial fetch, a worse lie than the loading text it replaces elsewhere in
 * this module). Asserts:
 *   1. The empty state is unreachable while a query is pending OR fetching.
 *   2. Error states render (with a retry affordance) on query failure.
 *   3. The unmapped-queue "good news" empty state is distinct from a
 *      generic empty state and from the loading/error states.
 *   4. The mirrored Corretores section gets the same treatment.
 *
 * Mock strategy mirrors EmailMarketingConfig.test.tsx / Contatos.test.tsx —
 * every `@/components/ui/*` primitive is a lightweight stub, hooks are
 * `vi.fn()`s configured per test, `@noctusai/lib/design-system` is stubbed
 * (real barrel throws at module-load without VITE_SUPABASE_URL — see
 * WhatsAppChat.test.tsx's docstring for the full rationale).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseLeadSources = vi.fn();
const mockUseLeadSourceAliases = vi.fn();
const mockUseLeadSourceUnmapped = vi.fn();
const mockUseLeadSourceMutations = vi.fn();
const mockUseLeadSourceAliasMutations = vi.fn();

vi.mock("@/hooks/useLeadsSources", () => ({
  useLeadSources: mockUseLeadSources,
  useLeadSourceAliases: mockUseLeadSourceAliases,
  useLeadSourceUnmapped: mockUseLeadSourceUnmapped,
  useLeadSourceMutations: mockUseLeadSourceMutations,
  useLeadSourceAliasMutations: mockUseLeadSourceAliasMutations,
}));

const mockUseLeadCorretores = vi.fn();
const mockUseLeadCorretorAliases = vi.fn();
const mockUseLeadCorretorUnmapped = vi.fn();
const mockUseLeadCorretorMutations = vi.fn();
const mockUseLeadCorretorAliasMutations = vi.fn();

vi.mock("@/hooks/useLeadsCorretores", () => ({
  useLeadCorretores: mockUseLeadCorretores,
  useLeadCorretorAliases: mockUseLeadCorretorAliases,
  useLeadCorretorUnmapped: mockUseLeadCorretorUnmapped,
  useLeadCorretorMutations: mockUseLeadCorretorMutations,
  useLeadCorretorAliasMutations: mockUseLeadCorretorAliasMutations,
}));

// ─── Design-system / UI stubs ────────────────────────────────────────────────

vi.mock("@noctusai/lib/design-system", () => ({
  Skeleton: ({ "data-testid": dt }: any) => <div data-testid={dt ?? "skeleton"} />,
  TableSkeleton: ({ rows, columns }: any) => (
    <div data-testid="table-skeleton" data-rows={rows} data-columns={columns} />
  ),
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt} {...rest}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/input", () => ({
  Input: ({ onChange, value, "data-testid": dt, ...rest }: any) => (
    <input value={value ?? ""} onChange={onChange} data-testid={dt} {...rest} />
  ),
}));
vi.mock("@/components/ui/label", () => ({
  Label: ({ children, htmlFor }: any) => <label htmlFor={htmlFor}>{children}</label>,
}));
vi.mock("@/components/ui/switch", () => ({
  Switch: ({ checked, onCheckedChange, id }: any) => (
    <input type="checkbox" id={id} checked={!!checked} onChange={(e) => onCheckedChange?.(e.target.checked)} />
  ),
}));
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: any) => (open ? <div data-testid="dialog">{children}</div> : null),
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: any) => (open ? <div data-testid="alert-dialog">{children}</div> : null),
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <h2>{children}</h2>,
  AlertDialogDescription: ({ children }: any) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: any) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: any) => <button>{children}</button>,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children, "data-testid": dt }: any) => <div data-testid={dt}>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children, value }: any) => <div data-value={value}>{children}</div>,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeQuery(overrides: Partial<any> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  };
}

function makeMutation(overrides: Partial<any> = {}) {
  return { mutate: vi.fn(), isPending: false, ...overrides };
}

function defaultSourceMutations() {
  return {
    create: makeMutation(),
    update: makeMutation(),
    remove: makeMutation(),
  };
}
function defaultAliasMutations() {
  return { upsert: makeMutation(), remove: makeMutation() };
}

beforeEach(() => {
  vi.clearAllMocks();

  mockUseLeadSources.mockReturnValue(makeQuery({ data: [] }));
  mockUseLeadSourceAliases.mockReturnValue(makeQuery({ data: [] }));
  mockUseLeadSourceUnmapped.mockReturnValue(makeQuery({ data: [] }));
  mockUseLeadSourceMutations.mockReturnValue(defaultSourceMutations());
  mockUseLeadSourceAliasMutations.mockReturnValue(defaultAliasMutations());

  mockUseLeadCorretores.mockReturnValue(makeQuery({ data: [] }));
  mockUseLeadCorretorAliases.mockReturnValue(makeQuery({ data: [] }));
  mockUseLeadCorretorUnmapped.mockReturnValue(makeQuery({ data: [] }));
  mockUseLeadCorretorMutations.mockReturnValue(defaultSourceMutations());
  mockUseLeadCorretorAliasMutations.mockReturnValue(defaultAliasMutations());
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Configuracao } = await import("./Configuracao");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Configuracao)), fireEvent: rtl.fireEvent };
}

// ─── Origens — sources table ────────────────────────────────────────────────

describe("Configuracao — Origens sources table", () => {
  it("shows the skeleton and NOT the empty state while pending", async () => {
    mockUseLeadSources.mockReturnValue(makeQuery({ data: undefined, isPending: true, isFetching: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("sources-loading")).toBeTruthy();
    expect(queryByTestId("sources-empty")).toBeNull();
    expect(queryByTestId("sources-table")).toBeNull();
  });

  it("does NOT show the empty state during a background refetch (isFetching, cached data present but stale-checked)", async () => {
    mockUseLeadSources.mockReturnValue(makeQuery({ data: [], isPending: false, isFetching: true }));
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("sources-empty")).toBeNull();
  });

  it("shows an error state with a retry affordance on failure", async () => {
    const refetch = vi.fn();
    mockUseLeadSources.mockReturnValue(makeQuery({ isError: true, refetch }));
    const { getByTestId, fireEvent } = await renderPage();
    const errorEl = getByTestId("sources-error");
    expect(errorEl).toBeTruthy();
    fireEvent.click(errorEl.querySelector("button")!);
    expect(refetch).toHaveBeenCalled();
  });

  it("shows the honest empty state once resolved with zero sources", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("sources-empty")).toBeTruthy();
  });

  it("shows the table once sources resolve with data", async () => {
    mockUseLeadSources.mockReturnValue(
      makeQuery({
        data: [{ id: "s1", org_id: "o1", slug: "site", label: "Site", categoria: "direto", cor: null, ativo: true, ordem: 1, created_at: "", updated_at: null }],
      }),
    );
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("sources-table")).toBeTruthy();
    expect(queryByTestId("sources-empty")).toBeNull();
  });
});

// ─── Origens — unmapped queue ("map these first") ───────────────────────────

describe("Configuracao — Origens unmapped queue", () => {
  it("does not show the good-news empty state while the unmapped query is pending", async () => {
    mockUseLeadSourceUnmapped.mockReturnValue(makeQuery({ data: undefined, isPending: true, isFetching: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("sources-unmapped-loading")).toBeTruthy();
    expect(queryByTestId("sources-unmapped-empty")).toBeNull();
  });

  it("shows an error state with retry when the unmapped queue fails", async () => {
    const refetch = vi.fn();
    mockUseLeadSourceUnmapped.mockReturnValue(makeQuery({ isError: true, refetch }));
    const { getByTestId, fireEvent } = await renderPage();
    const errorEl = getByTestId("sources-unmapped-error");
    fireEvent.click(errorEl.querySelector("button")!);
    expect(refetch).toHaveBeenCalled();
  });

  it("reads as GOOD NEWS (not a failure) when the queue is empty", async () => {
    const { getByTestId, queryByTestId } = await renderPage();
    const empty = getByTestId("sources-unmapped-empty");
    expect(empty.textContent).toMatch(/tudo mapeado/i);
    expect(queryByTestId("sources-unmapped-queue")).toBeNull();
  });

  it("shows the queue when there are unmapped aliases", async () => {
    mockUseLeadSourceUnmapped.mockReturnValue(makeQuery({ data: [{ alias: "FB_ADS", count: 3 }] }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("sources-unmapped-queue")).toBeTruthy();
    expect(queryByTestId("sources-unmapped-empty")).toBeNull();
  });
});

// ─── Corretores — mirrored section ──────────────────────────────────────────

describe("Configuracao — Corretores section (mirrored)", () => {
  async function switchToCorretores() {
    const rendered = await renderPage();
    rendered.fireEvent.click(rendered.getByTestId("config-section-corretores"));
    return rendered;
  }

  it("shows the skeleton and NOT the empty state while corretores are pending", async () => {
    mockUseLeadCorretores.mockReturnValue(makeQuery({ data: undefined, isPending: true, isFetching: true }));
    const { getByTestId, queryByTestId } = await switchToCorretores();
    expect(getByTestId("corretores-loading")).toBeTruthy();
    expect(queryByTestId("corretores-empty")).toBeNull();
  });

  it("shows an error state on corretores fetch failure", async () => {
    mockUseLeadCorretores.mockReturnValue(makeQuery({ isError: true }));
    const { getByTestId } = await switchToCorretores();
    expect(getByTestId("corretores-error")).toBeTruthy();
  });

  it("shows the honest empty state once resolved with zero corretores", async () => {
    const { getByTestId } = await switchToCorretores();
    expect(getByTestId("corretores-empty")).toBeTruthy();
  });

  it("shows the good-news empty state for the corretores unmapped queue", async () => {
    const { getByTestId } = await switchToCorretores();
    expect(getByTestId("corretores-unmapped-empty").textContent).toMatch(/tudo mapeado/i);
  });

  it("does not show the corretores good-news empty state while pending", async () => {
    mockUseLeadCorretorUnmapped.mockReturnValue(makeQuery({ data: undefined, isPending: true, isFetching: true }));
    const { queryByTestId } = await switchToCorretores();
    expect(queryByTestId("corretores-unmapped-empty")).toBeNull();
  });
});
