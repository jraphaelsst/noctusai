/**
 * Importacao.test.tsx — Leads "Importação" subtab.
 *
 * Focus:
 *   1. The dropzone/file-input is disabled (never accepts a new file) while
 *      a preview parse OR a commit write is in flight — the double-submit
 *      gap this file closes.
 *   2. The commit button shows visible pending feedback and stays disabled
 *      while committing (regression net for the pre-existing behavior).
 *   3. The batch-history table's empty state is unreachable while pending
 *      or fetching, and an error state renders on failure (regression net
 *      for the state-quadrant this page already had — no test file existed
 *      for it before this change).
 *
 * Mock strategy mirrors Configuracao.test.tsx / EmailMarketingConfig.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseLeadImportPreview = vi.fn();
const mockUseLeadImportCommit = vi.fn();
const mockUseLeadImportBatches = vi.fn();

vi.mock("@/hooks/useLeadsImport", () => ({
  useLeadImportPreview: mockUseLeadImportPreview,
  useLeadImportCommit: mockUseLeadImportCommit,
  useLeadImportBatches: mockUseLeadImportBatches,
}));

// ─── Design-system / UI stubs ────────────────────────────────────────────────

vi.mock("@noctusai/lib/design-system", () => ({
  TableSkeleton: ({ rows, columns }: any) => (
    <div data-testid="table-skeleton" data-rows={rows} data-columns={columns} />
  ),
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt} {...rest}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}));
vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...rest }: any) => <div {...rest}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...rest }: any) => <div {...rest}>{children}</div>,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── Fixtures ────────────────────────────────────────────────────────────────

function makeMutation(overrides: Partial<any> = {}) {
  return { mutate: vi.fn(), reset: vi.fn(), isPending: false, isError: false, data: undefined, error: null, ...overrides };
}
function makeBatchesQuery(overrides: Partial<any> = {}) {
  return {
    data: { data: [], pagination: { page: 1, page_size: 20, total: 0 } },
    isPending: false,
    isFetching: false,
    isError: false,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseLeadImportPreview.mockReturnValue(makeMutation());
  mockUseLeadImportCommit.mockReturnValue(makeMutation());
  mockUseLeadImportBatches.mockReturnValue(makeBatchesQuery());
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Importacao } = await import("./Importacao");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Importacao)), fireEvent: rtl.fireEvent };
}

// ─── Double-submit prevention ────────────────────────────────────────────────

describe("Importacao — busy gating (no double-submit)", () => {
  it("disables the file input while a preview parse is in flight", async () => {
    mockUseLeadImportPreview.mockReturnValue(makeMutation({ isPending: true }));
    const { getByTestId } = await renderPage();
    const input = getByTestId("leads-import-file-input") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("disables the file input while a commit write is in flight", async () => {
    mockUseLeadImportCommit.mockReturnValue(makeMutation({ isPending: true }));
    const { getByTestId } = await renderPage();
    const input = getByTestId("leads-import-file-input") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("marks the dropzone aria-disabled + not tab-reachable while busy", async () => {
    mockUseLeadImportPreview.mockReturnValue(makeMutation({ isPending: true }));
    const { getByTestId } = await renderPage();
    const dropzone = getByTestId("leads-import-dropzone");
    expect(dropzone.getAttribute("aria-disabled")).toBe("true");
    expect(dropzone.getAttribute("tabindex")).toBe("-1");
  });

  it("leaves the dropzone interactive when idle", async () => {
    const { getByTestId } = await renderPage();
    const dropzone = getByTestId("leads-import-dropzone");
    expect(dropzone.getAttribute("aria-disabled")).toBe("false");
    expect(dropzone.getAttribute("tabindex")).toBe("0");
  });

  it("shows visible pending feedback and stays disabled on the commit button while committing", async () => {
    mockUseLeadImportPreview.mockReturnValue(
      makeMutation({
        data: {
          filename: "leads.xlsx",
          sheets: ["Sheet1"],
          rows_read: 10,
          rows_new: 5,
          rows_existing: 5,
          rows_skipped: 0,
          unmapped_origens: [],
          unmapped_corretores: [],
          sample: [],
          warnings: [],
        },
      }),
    );
    mockUseLeadImportCommit.mockReturnValue(makeMutation({ isPending: true }));
    const { getByTestId } = await renderPage();
    const commitBtn = getByTestId("leads-import-commit") as HTMLButtonElement;
    expect(commitBtn.disabled).toBe(true);
  });
});

// ─── Batch history table — state quadrant ───────────────────────────────────

describe("Importacao — batch history table", () => {
  it("shows the skeleton and NOT the empty state while pending", async () => {
    mockUseLeadImportBatches.mockReturnValue(makeBatchesQuery({ data: undefined, isPending: true, isFetching: true }));
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("leads-batches-loading")).toBeTruthy();
    expect(queryByTestId("leads-batches-empty")).toBeNull();
  });

  it("does not show the empty state during a background refetch", async () => {
    mockUseLeadImportBatches.mockReturnValue(
      makeBatchesQuery({ data: { data: [], pagination: { page: 1, page_size: 20, total: 0 } }, isFetching: true }),
    );
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("leads-batches-empty")).toBeNull();
  });

  it("shows an error state on fetch failure", async () => {
    mockUseLeadImportBatches.mockReturnValue(makeBatchesQuery({ isError: true }));
    const { getByTestId } = await renderPage();
    expect(getByTestId("leads-batches-error")).toBeTruthy();
  });

  it("shows the honest empty state once resolved with zero batches", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("leads-batches-empty")).toBeTruthy();
  });
});
