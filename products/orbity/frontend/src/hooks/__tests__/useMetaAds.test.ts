/**
 * Meta Ads hooks — render tests for query/mutation states:
 *   loading → success (with data) → success (empty list) → error
 *
 * Mocking pattern: vi.hoisted() initializes mocks before vi.mock factories.
 *
 * Note: localStorage is provisioned by the seed vitest.setup.ts — do not
 * re-polyfill here.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Shared mocks via vi.hoisted
// ---------------------------------------------------------------------------

const { mockGet, mockPost, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
}));

vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: { id: "u1", email: "test@orbity.app" } }),
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// ---------------------------------------------------------------------------
// Static import of the module under test (mocks are already hoisted)
// ---------------------------------------------------------------------------

import {
  useAdAccounts,
  useCampaigns,
  useSpendLeadsAggregate,
  useSyncCampaigns,
  useCreateAdAccount,
  useDeleteAdAccount,
  useCreateCampaign,
  useUpdateSituation,
} from "@/hooks/useMetaAds";

// ---------------------------------------------------------------------------
// Wrapper factory
// ---------------------------------------------------------------------------

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const sampleAdAccount = {
  id: "aa-1",
  org_id: "org-1",
  client_id: null,
  external_account_id: "act_123456",
  name: "Conta Principal",
  status: "active",
  connected_at: "2026-06-01T10:00:00Z",
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-01T10:00:00Z",
};

const sampleCampaign = {
  id: "camp-1",
  org_id: "org-1",
  client_id: null,
  ad_account_id: "aa-1",
  external_campaign_id: "12345678",
  name: "Campanha Leads Julho",
  objective: "LEAD_GENERATION",
  status: "active",
  daily_budget: 150.0,
  result_metric: "leads",
  situation: "on-track",
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-01T10:00:00Z",
};

const sampleAggregate = {
  period_start: "2026-05-01",
  period_end: "2026-06-01",
  items: [
    {
      client_id: null,
      client_name: null,
      month: "2026-05",
      total_spend: 4500.0,
      total_leads: 90,
      avg_cpl: 50.0,
      campaign_count: 3,
      on_track_count: 2,
      attention_count: 1,
      off_count: 0,
    },
  ],
  total_spend: 4500.0,
  total_leads: 90,
};

// ---------------------------------------------------------------------------
// useAdAccounts
// ---------------------------------------------------------------------------

describe("useAdAccounts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns loading state initially", () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAdAccounts(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("returns data on success", async () => {
    mockGet.mockResolvedValue({ items: [sampleAdAccount], total: 1, page: 1, page_size: 50 });
    const { result } = renderHook(() => useAdAccounts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].external_account_id).toBe("act_123456");
  });

  it("returns empty list when no accounts", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    const { result } = renderHook(() => useAdAccounts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(0);
  });

  it("returns error state on failure", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar contas"));
    const { result } = renderHook(() => useAdAccounts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Falha ao listar contas");
  });
});

// ---------------------------------------------------------------------------
// useCampaigns
// ---------------------------------------------------------------------------

describe("useCampaigns", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns loading state initially", () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("returns campaigns on success", async () => {
    mockGet.mockResolvedValue({ items: [sampleCampaign], total: 1, page: 1, page_size: 50 });
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0].name).toBe("Campanha Leads Julho");
    expect(result.current.data?.items[0].situation).toBe("on-track");
  });

  it("returns empty list state", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(0);
  });

  it("returns error state on failure", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar campanhas"));
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Falha ao listar campanhas");
  });

  it("passes filters to api.get", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    const { result } = renderHook(
      () => useCampaigns({ situation: "attention", status: "active" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/meta-ads/campaigns",
      expect.objectContaining({ situation: "attention", status: "active" }),
    );
  });
});

// ---------------------------------------------------------------------------
// useSpendLeadsAggregate
// ---------------------------------------------------------------------------

describe("useSpendLeadsAggregate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns aggregate data on success", async () => {
    mockGet.mockResolvedValue(sampleAggregate);
    const { result } = renderHook(
      () => useSpendLeadsAggregate("2026-05-01", "2026-06-01"),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_spend).toBe(4500.0);
    expect(result.current.data?.total_leads).toBe(90);
    expect(result.current.data?.items).toHaveLength(1);
  });

  it("returns error state on failure", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao calcular agregado"));
    const { result } = renderHook(
      () => useSpendLeadsAggregate("2026-05-01", "2026-06-01"),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("is disabled when dates are empty", () => {
    const { result } = renderHook(
      () => useSpendLeadsAggregate("", ""),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
// useSyncCampaigns
// ---------------------------------------------------------------------------

describe("useSyncCampaigns", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/meta-ads/sync with ad_account_id", async () => {
    const syncResponse = {
      synced: 5,
      skipped: 2,
      errors: 0,
      source: "fake",
    };
    mockPost.mockResolvedValue(syncResponse);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { result } = renderHook(() => useSyncCampaigns(), {
      wrapper: makeWrapper(),
    });
    result.current.mutate("aa-1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/meta-ads/sync", {
      ad_account_id: "aa-1",
    });
    expect(result.current.data?.synced).toBe(5);
    expect(result.current.data?.source).toBe("fake");
  });

  it("returns error on sync failure", async () => {
    mockPost.mockRejectedValue(new Error("Falha ao sincronizar"));
    const { result } = renderHook(() => useSyncCampaigns(), {
      wrapper: makeWrapper(),
    });
    result.current.mutate("aa-1");
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// useCreateAdAccount
// ---------------------------------------------------------------------------

describe("useCreateAdAccount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/meta-ads/ad-accounts", async () => {
    mockPost.mockResolvedValue(sampleAdAccount);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { result } = renderHook(() => useCreateAdAccount(), {
      wrapper: makeWrapper(),
    });
    result.current.mutate({
      external_account_id: "act_123456",
      name: "Conta Principal",
      status: "active",
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith(
      "/api/meta-ads/ad-accounts",
      expect.objectContaining({ external_account_id: "act_123456" }),
    );
  });
});

// ---------------------------------------------------------------------------
// useDeleteAdAccount
// ---------------------------------------------------------------------------

describe("useDeleteAdAccount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls DELETE /api/meta-ads/ad-accounts/{id}", async () => {
    mockDelete.mockResolvedValue({ ok: true, id: "aa-1" });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { result } = renderHook(() => useDeleteAdAccount(), {
      wrapper: makeWrapper(),
    });
    result.current.mutate("aa-1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith("/api/meta-ads/ad-accounts/aa-1");
  });
});

// ---------------------------------------------------------------------------
// useCreateCampaign
// ---------------------------------------------------------------------------

describe("useCreateCampaign", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/meta-ads/campaigns", async () => {
    mockPost.mockResolvedValue(sampleCampaign);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { result } = renderHook(() => useCreateCampaign(), {
      wrapper: makeWrapper(),
    });
    result.current.mutate({
      ad_account_id: "aa-1",
      external_campaign_id: "12345678",
      name: "Campanha Leads Julho",
      situation: "on-track",
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith(
      "/api/meta-ads/campaigns",
      expect.objectContaining({ name: "Campanha Leads Julho" }),
    );
  });
});

// ---------------------------------------------------------------------------
// useUpdateSituation
// ---------------------------------------------------------------------------

describe("useUpdateSituation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls PATCH /api/meta-ads/campaigns/{id}/situation", async () => {
    mockPatch.mockResolvedValue({ ...sampleCampaign, situation: "attention" });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });

    const { result } = renderHook(() => useUpdateSituation(), {
      wrapper: makeWrapper(),
    });
    result.current.mutate({ id: "camp-1", situation: "attention" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/meta-ads/campaigns/camp-1/situation",
      { situation: "attention" },
    );
  });
});
