import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Plain function (not vi.fn): vitest 4 reports a vi.fn-returned rejected
// promise as a test failure even when the consumer handles it.
let segmentImpl: (b: Record<string, unknown>) => Promise<unknown> = async () => ({});
const segmentPost = (b: Record<string, unknown>) => segmentImpl(b);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@noctusai/lib/components", () => ({ ResourceManager: () => <div data-testid="rm" /> }));
vi.mock("@noctusai/lib/design-system", () => ({ AIIndicator: () => null }));
vi.mock("@/lib/api", () => ({ api: {} }));
vi.mock("@/hooks/useEmailMarketing", async () => {
  const { useMutation } = await import("@tanstack/react-query");
  return {
    useEmContactMutations: () => ({ importMany: { mutate: vi.fn(), isPending: false } }),
    useEmAi: () => ({
      segmentContacts: useMutation({ mutationFn: (b: Record<string, unknown>) => segmentPost(b) }),
    }),
  };
});

import EmailContatos, { segmentErrorMessage, summarizeSegments } from "./Contatos";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EmailContatos />
    </QueryClientProvider>,
  );
}

describe("Contatos segmentation", () => {
  afterEach(cleanup);

  it("summarizeSegments counts per label, desc", () => {
    expect(
      summarizeSegments([
        { ref_id: "1", label: "B" },
        { ref_id: "2", label: "A" },
        { ref_id: "3", label: "A" },
      ]),
    ).toEqual([
      { label: "A", count: 2 },
      { label: "B", count: 1 },
    ]);
  });

  it("runs segmentation and shows segment chips with counts", async () => {
    segmentImpl = async () => ({
      data: {
        segmented: 3,
        persisted: [
          { ref_id: "1", label: "Corretores" },
          { ref_id: "2", label: "Corretores" },
          { ref_id: "3", label: "Investidores" },
        ],
      },
    });
    renderPage();
    fireEvent.click(screen.getByTestId("contatos-segment-run"));
    await waitFor(() => expect(screen.getAllByTestId("contatos-segment-chip")).toHaveLength(2));
    expect(screen.getAllByTestId("contatos-segment-chip")[0].textContent).toBe("Corretores · 2");
  });

  it("shows the empty state when nothing was segmented", async () => {
    segmentImpl = async () => ({ data: { segmented: 0, persisted: [] } });
    renderPage();
    fireEvent.click(screen.getByTestId("contatos-segment-run"));
    expect(await screen.findByTestId("contatos-segment-empty")).toBeTruthy();
  });

  it("surfaces a consent (403) error clearly", async () => {
    segmentImpl = async () => {
      throw Object.assign(new Error("[403] forbidden"), { status: 403 });
    };
    renderPage();
    fireEvent.click(screen.getByTestId("contatos-segment-run"));
    const el = await screen.findByTestId("contatos-segment-error");
    expect(el.textContent).toContain("consentimento");
    expect(segmentErrorMessage({ status: 403 })).toContain("segment_contacts");
  });
});
