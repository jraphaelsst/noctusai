/**
 * WorkflowsPanel.test.tsx — regression coverage for the "Sem marca" bucket's
 * refetch-unmount bug.
 *
 * `unassignedQuery.loading` used to be `isPending || isFetching`
 * (KB § PATTERNS/frontend/lying-loading-state.md's usual advice), but
 * `unassignedWorkflows` always defaults to `[]` via `?? []`, and every
 * drag-assign invalidates this query — so once workflows had loaded, the
 * NEXT drag-assign's background refetch flipped `loading` back to `true`
 * and `<UnassignedBucket/>` swapped its already-rendered rows for
 * "Carregando…", every single time. The fix gates on the RAW
 * `unassignedQuery.data` (undefined until the first successful fetch)
 * instead of the always-array `unassignedWorkflows`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseN8nWorkflows = vi.fn();
const mockUseActiveAccountId = vi.fn();

vi.mock("@/state/useActiveAccount", () => ({
  useActiveAccountId: (...args: unknown[]) => mockUseActiveAccountId(...args),
}));

vi.mock("@/hooks/useN8nWorkflows", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useN8nWorkflows")>(
    "@/hooks/useN8nWorkflows",
  );
  return {
    ...actual,
    useN8nWorkflows: (...args: unknown[]) => mockUseN8nWorkflows(...args),
    useAssignWorkflow: () => ({ mutate: vi.fn(), isPending: false }),
    useUnassignWorkflow: () => ({ mutate: vi.fn(), isPending: false }),
    useUpdateWorkflow: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteWorkflow: () => ({ mutate: vi.fn(), isPending: false }),
    useRunWorkflow: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

vi.mock("@/hooks/useN8nFolders", () => ({
  useCreateFolder: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateFolder: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteFolder: () => ({ mutate: vi.fn(), isPending: false }),
}));

const CLIENT_QUERY = {
  isPending: false,
  isFetching: false,
  isError: false,
  data: { workflows: [], folders: [] },
  refetch: vi.fn(),
};

function unassignedWorkflow(id: string, name: string) {
  return {
    id,
    name,
    active: true,
    archived: false,
    tags: [],
    folder_id: null,
    can_run: true,
    run_blocked_reason: null,
    open_url: `https://n8n.example/workflow/${id}`,
    updated_at: null,
  };
}

beforeEach(() => {
  mockUseActiveAccountId.mockReturnValue("acct-1");
  mockUseN8nWorkflows.mockReset();
});

async function renderPanel() {
  const mod = await import("./WorkflowsPanel");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
  const { TooltipProvider } = await import("@/components/ui/tooltip");
  // `ExecutionsDialog` (mounted but closed) calls the REAL
  // `useWorkflowExecutions` — needs a live QueryClient even though its
  // query is disabled while closed. `WorkflowCard` wraps its actions in
  // `<Tooltip>`, which needs a `TooltipProvider` ancestor (normally
  // supplied app-wide; this test mounts the panel in isolation).
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtl.render(
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(TooltipProvider, null, React.createElement(mod.WorkflowsPanel)),
    ),
  );
}

describe("WorkflowsPanel — 'Sem marca' bucket loading gate", () => {
  it("keeps unassigned workflows mounted through a background refetch (isFetching, data present)", async () => {
    mockUseN8nWorkflows.mockImplementation(({ scope }: { scope: string }) =>
      scope === "client"
        ? CLIENT_QUERY
        : {
            isPending: false,
            // A drag-assign invalidated this query — it is refetching in
            // the background, but the LAST successful page is still here.
            isFetching: true,
            isError: false,
            data: { workflows: [unassignedWorkflow("wf-1", "Fluxo sem marca")] },
            refetch: vi.fn(),
          },
    );

    const { getByTestId, queryByText, getByText } = await renderPanel();

    // The bucket's own content stays in the DOM — never swapped for the
    // "Carregando…" skeleton just because a background refetch is in
    // flight.
    expect(getByTestId("n8n-unassigned-bucket")).toBeTruthy();
    expect(getByText("Fluxo sem marca")).toBeTruthy();
    expect(queryByText("Carregando…")).toBeNull();
  });

  it("shows the skeleton only on first load (isPending, no data yet)", async () => {
    mockUseN8nWorkflows.mockImplementation(({ scope }: { scope: string }) =>
      scope === "client"
        ? CLIENT_QUERY
        : {
            isPending: true,
            isFetching: true,
            isError: false,
            data: undefined,
            refetch: vi.fn(),
          },
    );

    const { getByText, queryByText } = await renderPanel();

    expect(getByText("Carregando…")).toBeTruthy();
    expect(queryByText("Fluxo sem marca")).toBeNull();
  });
});
