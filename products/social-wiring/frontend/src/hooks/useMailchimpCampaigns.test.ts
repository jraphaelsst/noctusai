/**
 * useMailchimpCampaigns.test.ts — unit tests for the Mailchimp campaigns hook.
 *
 * Covers:
 *   1. useMailchimpCampaigns — calls GET /api/mailchimp/campaigns.
 *   2. queryFn never returns undefined — returns empty items on no data.
 *   3. useMailchimpCampaignMutations.create — calls POST /api/mailchimp/campaigns.
 *   4. useMailchimpCampaignMutations.remove — calls DELETE /api/mailchimp/campaigns/:id.
 *   5. useMailchimpCampaignMutations.send — calls POST /api/mailchimp/campaigns/:id/actions/send.
 *   6. useMailchimpCampaignMutations.schedule — calls POST /api/mailchimp/campaigns/:id/actions/schedule.
 *   7. Mutations invalidate the mailchimp family key on success.
 *
 * Mock strategy: vi.mock @/lib/api (hoisted). All hook tests use real hook logic.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useMailchimpCampaigns,
  useMailchimpCampaignMutations,
} from "./useMailchimpCampaigns";

// ─── API mock ─────────────────────────────────────────────────────────────────
// NOTE: vi.mock is hoisted to the top by Vitest — factory CANNOT reference
// variables declared below. Use vi.fn() inline; grab refs via import after.

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

// Grab refs after mock registration
import { api as mockApi } from "@/lib/api";
const mockApiGet = mockApi.get as ReturnType<typeof vi.fn>;
const mockApiPost = mockApi.post as ReturnType<typeof vi.fn>;
const mockApiDelete = (mockApi as any).delete as ReturnType<typeof vi.fn>;
const mockApiPatch = mockApi.patch as ReturnType<typeof vi.fn>;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, Wrapper };
}

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeCampaign = (id = "camp-001") => ({
  id,
  web_id: 1001,
  title: "Test Campaign",
  status: "save" as const,
  subject_line: "Test Subject",
  preview_text: null,
  from_name: "Social Wiring",
  reply_to: "reply@social.com",
  segment_id: null,
  template_id: null,
  send_time: null,
  create_time: "2026-06-01T10:00:00Z",
  emails_sent: 0,
  opens: null,
  clicks: null,
  archive_url: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockApiGet.mockResolvedValue({
    items: [makeCampaign("camp-001"), makeCampaign("camp-002")],
    total: 2,
  });
  mockApiPost.mockResolvedValue(makeCampaign("camp-new"));
  mockApiDelete.mockResolvedValue(undefined);
  mockApiPatch.mockResolvedValue(makeCampaign("camp-001"));
});

afterEach(() => {
  vi.clearAllMocks();
});

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("useMailchimpCampaigns", () => {
  it("calls GET /api/mailchimp/campaigns", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMailchimpCampaigns(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApiGet).toHaveBeenCalledWith("/api/mailchimp/campaigns");
  });

  it("queryFn never returns undefined — returns items array on empty response", async () => {
    mockApiGet.mockResolvedValue({ items: [], total: 0 });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMailchimpCampaigns(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.items).toEqual([]);
  });

  it("passes count/offset params to API as query string in URL", async () => {
    const { Wrapper } = makeWrapper();
    renderHook(() => useMailchimpCampaigns({ count: 10, offset: 20 }), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
    const url: string = mockApiGet.mock.calls[0][0];
    expect(url).toContain("count=10");
    expect(url).toContain("offset=20");
  });
});

describe("useMailchimpCampaignMutations", () => {
  it("create fires POST /api/mailchimp/campaigns", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMailchimpCampaignMutations(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      result.current.create.mutate({
        title: "Test Campaign",
        subject_line: "Test Subject",
        from_name: "Social Wiring",
        reply_to: "reply@social.com",
      });
    });

    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/mailchimp/campaigns",
      expect.objectContaining({ title: "Test Campaign" }),
    );
  });

  it("remove fires DELETE /api/mailchimp/campaigns/:id", async () => {
    mockApiDelete.mockResolvedValue(undefined);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMailchimpCampaignMutations(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      result.current.remove.mutate("camp-001");
    });

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(mockApiDelete).toHaveBeenCalledWith(
      "/api/mailchimp/campaigns/camp-001",
    );
  });

  it("send fires POST /api/mailchimp/campaigns/:id/actions/send", async () => {
    mockApiPost.mockResolvedValue(undefined);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMailchimpCampaignMutations(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      result.current.send.mutate("camp-001");
    });

    await waitFor(() => expect(result.current.send.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/mailchimp/campaigns/camp-001/actions/send",
      {},
    );
  });

  it("schedule fires POST /api/mailchimp/campaigns/:id/actions/schedule", async () => {
    mockApiPost.mockResolvedValue(undefined);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMailchimpCampaignMutations(), {
      wrapper: Wrapper,
    });

    const scheduleTime = "2026-07-01T10:00:00+00:00";
    await act(async () => {
      result.current.schedule.mutate({
        id: "camp-001",
        body: { schedule_time: scheduleTime },
      });
    });

    await waitFor(() => expect(result.current.schedule.isSuccess).toBe(true));
    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/mailchimp/campaigns/camp-001/actions/schedule",
      { schedule_time: scheduleTime },
    );
  });

  it("mutations invalidate the mailchimp family key on success", async () => {
    mockApiDelete.mockResolvedValue(undefined);
    const { qc, Wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useMailchimpCampaignMutations(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      result.current.remove.mutate("camp-001");
    });

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["mailchimp"] }),
    );
  });
});
