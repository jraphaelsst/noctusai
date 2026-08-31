/**
 * LeadDetailModal.test.tsx — Cat A regression: the field grid must not
 * unmount back to a skeleton on a background refetch.
 *
 * `<EntityDetailDialog>` (the seed organ, `@noctusai/lib/components`) takes
 * exactly one `isLoading` boolean and swaps `<SkeletonGrid/>` in over the
 * field grid whenever it is true — it has no data-presence check of its
 * own. The old gate here (`shouldFetch && (fetched.isPending ||
 * fetched.isFetching)`) meant every board-card open that re-fetched an
 * already-open lead (a background refetch after any lead mutation
 * elsewhere) replaced a fully-rendered lead with a skeleton, even though
 * `resolved` still held the record. `@noctusai/lib/components` is stubbed
 * (same pattern used across this product's test suite) so this file
 * asserts the `isLoading` PROP this component computes and passes down,
 * not `EntityDetailDialog`'s own rendering.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseLead = vi.fn();
const mockUseLeadSources = vi.fn();

vi.mock("@/hooks/useLeads", () => ({
  useLead: (id: string | null) => mockUseLead(id),
}));
vi.mock("@/hooks/useLeadsSources", () => ({
  useLeadSources: () => mockUseLeadSources(),
}));

let lastProps: any = null;
vi.mock("@noctusai/lib/components", () => ({
  EntityDetailDialog: (props: any) => {
    lastProps = props;
    return null;
  },
}));

function lead(over: Partial<any> = {}) {
  return {
    id: "lead-1",
    cliente_nome: "Ana Silva",
    needs_review: false,
    origem: "ZAP",
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  lastProps = null;
  mockUseLeadSources.mockReturnValue({ data: undefined });
});

async function renderModal(props: Partial<any> = {}) {
  const mod = await import("./LeadDetailModal");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(
    React.createElement(mod.LeadDetailModal, {
      open: true,
      onClose: vi.fn(),
      leadId: "lead-1",
      ...props,
    }),
  );
}

describe("LeadDetailModal — isLoading gate passed to EntityDetailDialog", () => {
  it("🔴 stays false during a background refetch once the lead has landed (Cat A regression)", async () => {
    mockUseLead.mockReturnValue({
      data: lead(),
      isPending: false,
      // A board-card re-open, or any mutation elsewhere that invalidates
      // this lead, triggers a background refetch here.
      isFetching: true,
      isError: false,
      error: null,
    });
    await renderModal();
    expect(lastProps.isLoading).toBe(false);
    expect(lastProps.sections.length).toBeGreaterThan(0);
  });

  it("is true on first load — isPending, no data yet", async () => {
    mockUseLead.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
    });
    await renderModal();
    expect(lastProps.isLoading).toBe(true);
  });

  it("is false when the caller already holds the record (no fetch at all)", async () => {
    mockUseLead.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: false,
      isError: false,
      error: null,
    });
    await renderModal({ leadId: undefined, lead: lead({ cliente_nome: "Held record" }) });
    expect(lastProps.isLoading).toBe(false);
    expect(lastProps.title).toBe("Held record");
  });
});
