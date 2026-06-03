/**
 * Content / Social Studio hooks — render tests for all four query states:
 *   loading → success (with data) → success (empty list) → error
 *
 * Mocking pattern mirrors useFinancial.test.tsx exactly:
 *   vi.hoisted() for shared mocks, vi.mock factories reference only hoisted vars.
 *
 * Note: localStorage is provisioned by the seed vitest.setup.ts — do not
 * re-polyfill here.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Shared mocks via vi.hoisted — initialized before vi.mock factories run
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
// Static import of the module under test (mocks above are already hoisted)
// ---------------------------------------------------------------------------

import {
  useCampaigns,
  usePosts,
  useApprovals,
  useCreateCampaign,
  useCreatePost,
  useCreateApproval,
  usePublicApproval,
  useDecideApproval,
} from "@/hooks/useConteudo";

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

const CAMPAIGN_ITEM = {
  id: "cmp-1",
  org_id: "org-1",
  client_id: null,
  name: "Campanha Junho",
  month: "2026-06",
  status: "active" as const,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const CAMPAIGN_LIST = { items: [CAMPAIGN_ITEM], total: 1, page: 1, page_size: 50 };
const EMPTY_LIST = { items: [], total: 0, page: 1, page_size: 50 };

const POST_ITEM = {
  id: "post-1",
  org_id: "org-1",
  campaign_id: "cmp-1",
  client_id: null,
  platform: "instagram" as const,
  caption: "Post de teste para Instagram",
  hashtags: "#teste #orbity",
  scheduled_for: "2026-06-15T10:00:00Z",
  status: "draft" as const,
  assignee_user_id: null,
  media_url: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const POST_LIST = { items: [POST_ITEM], total: 1, page: 1, page_size: 50 };

const APPROVAL_ITEM = {
  id: "apv-1",
  org_id: "org-1",
  post_id: "post-1",
  public_token: "tok-uuid-1234",
  status: "pending" as const,
  client_feedback: null,
  expires_at: "2026-06-22T00:00:00Z",
  decided_at: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Tests: useCampaigns
// ---------------------------------------------------------------------------

describe("useCampaigns", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state — query is in-flight", () => {
    mockGet.mockImplementation(() => new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("success state — returns campaigns list with correct shape", async () => {
    mockGet.mockResolvedValue(CAMPAIGN_LIST);
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/content/campaigns",
      expect.objectContaining({ page: 1, page_size: 50 }),
    );
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].name).toBe("Campanha Junho");
    expect(result.current.data?.items[0].month).toBe("2026-06");
    expect(result.current.data?.items[0].status).toBe("active");
    expect(result.current.data?.total).toBe(1);
  });

  it("empty state — returns zero items", async () => {
    mockGet.mockResolvedValue(EMPTY_LIST);
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(0);
    expect(result.current.data?.total).toBe(0);
  });

  it("error state — exposes error message", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar campanhas"));
    const { result } = renderHook(() => useCampaigns(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Falha ao listar campanhas");
    expect(result.current.data).toBeUndefined();
  });

  it("passes month filter as query param", async () => {
    mockGet.mockResolvedValue(CAMPAIGN_LIST);
    const { result } = renderHook(
      () => useCampaigns({ month: "2026-06" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/content/campaigns",
      expect.objectContaining({ month: "2026-06" }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: usePosts
// ---------------------------------------------------------------------------

describe("usePosts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => usePosts(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("success state — returns post items with correct shape", async () => {
    mockGet.mockResolvedValue(POST_LIST);
    const { result } = renderHook(() => usePosts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/content/posts",
      expect.objectContaining({ page: 1 }),
    );
    expect(result.current.data?.items[0].platform).toBe("instagram");
    expect(result.current.data?.items[0].caption).toBe("Post de teste para Instagram");
    expect(result.current.data?.items[0].status).toBe("draft");
    expect(result.current.data?.items[0].campaign_id).toBe("cmp-1");
  });

  it("empty state — returns zero items", async () => {
    mockGet.mockResolvedValue(EMPTY_LIST);
    const { result } = renderHook(() => usePosts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(0);
  });

  it("error state — exposes error", async () => {
    mockGet.mockRejectedValue(new Error("502 Bad Gateway"));
    const { result } = renderHook(() => usePosts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("502");
  });

  it("passes campaign_id filter as query param", async () => {
    mockGet.mockResolvedValue(POST_LIST);
    const { result } = renderHook(
      () => usePosts({ campaign_id: "cmp-1" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/content/posts",
      expect.objectContaining({ campaign_id: "cmp-1" }),
    );
  });

  it("passes platform filter as query param", async () => {
    mockGet.mockResolvedValue(POST_LIST);
    const { result } = renderHook(
      () => usePosts({ platform: "instagram" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/content/posts",
      expect.objectContaining({ platform: "instagram" }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: useApprovals
// ---------------------------------------------------------------------------

describe("useApprovals", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("success state (all org approvals) — returns approval list", async () => {
    mockGet.mockResolvedValue([APPROVAL_ITEM]);
    const { result } = renderHook(() => useApprovals(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/content/approvals");
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].public_token).toBe("tok-uuid-1234");
    expect(result.current.data?.[0].status).toBe("pending");
  });

  it("success state (post-scoped) — hits post approvals endpoint", async () => {
    mockGet.mockResolvedValue([APPROVAL_ITEM]);
    const { result } = renderHook(() => useApprovals("post-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/content/posts/post-1/approvals");
  });

  it("error state — surfaces error", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar aprovacoes"));
    const { result } = renderHook(() => useApprovals(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Tests: useCreateCampaign mutation
// ---------------------------------------------------------------------------

describe("useCreateCampaign", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/content/campaigns with payload", async () => {
    mockPost.mockResolvedValue(CAMPAIGN_ITEM);
    const { result } = renderHook(() => useCreateCampaign(), {
      wrapper: makeWrapper(),
    });
    await result.current.mutateAsync({ name: "Campanha Junho", month: "2026-06" });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/content/campaigns",
      expect.objectContaining({ name: "Campanha Junho", month: "2026-06" }),
    );
  });

  it("exposes error on failure", async () => {
    mockPost.mockRejectedValue(new Error("Falha ao criar campanha"));
    const { result } = renderHook(() => useCreateCampaign(), {
      wrapper: makeWrapper(),
    });
    await expect(
      result.current.mutateAsync({ name: "X", month: "2026-06" }),
    ).rejects.toThrow("Falha ao criar campanha");
  });
});

// ---------------------------------------------------------------------------
// Tests: useCreatePost mutation
// ---------------------------------------------------------------------------

describe("useCreatePost", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/content/posts with payload", async () => {
    mockPost.mockResolvedValue(POST_ITEM);
    const { result } = renderHook(() => useCreatePost(), {
      wrapper: makeWrapper(),
    });
    await result.current.mutateAsync({
      platform: "instagram",
      caption: "Novo post",
      status: "draft",
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/content/posts",
      expect.objectContaining({ platform: "instagram", caption: "Novo post" }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: useCreateApproval mutation
// ---------------------------------------------------------------------------

describe("useCreateApproval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls POST /api/content/posts/{postId}/approvals with expires_in_days", async () => {
    mockPost.mockResolvedValue(APPROVAL_ITEM);
    const { result } = renderHook(() => useCreateApproval(), {
      wrapper: makeWrapper(),
    });
    await result.current.mutateAsync({ postId: "post-1", expires_in_days: 7 });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/content/posts/post-1/approvals",
      expect.objectContaining({ expires_in_days: 7 }),
    );
  });

  it("uses default expires_in_days=7 when not provided", async () => {
    mockPost.mockResolvedValue(APPROVAL_ITEM);
    const { result } = renderHook(() => useCreateApproval(), {
      wrapper: makeWrapper(),
    });
    await result.current.mutateAsync({ postId: "post-1" });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/content/posts/post-1/approvals",
      expect.objectContaining({ expires_in_days: 7 }),
    );
  });
});

// ---------------------------------------------------------------------------
// Sample data — public approval
// ---------------------------------------------------------------------------

const PUBLIC_APPROVAL = {
  approval_id: "apv-pub-1",
  post_id: "post-1",
  token: "tok-pub-abc",
  status: "pending" as const,
  expires_at: "2099-06-30T00:00:00Z",
  decided_at: null,
  post: {
    id: "post-1",
    platform: "instagram" as const,
    caption: "Caption de aprovação de conteúdo",
    hashtags: "#orbity #social",
    media_url: null,
    scheduled_for: "2026-06-20T10:00:00Z",
  },
};

// ---------------------------------------------------------------------------
// Tests: usePublicApproval (no auth)
// ---------------------------------------------------------------------------

describe("usePublicApproval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state — query is in-flight", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => usePublicApproval("tok-pub-abc"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("success state — returns post + approval metadata", async () => {
    mockGet.mockResolvedValue(PUBLIC_APPROVAL);
    const { result } = renderHook(() => usePublicApproval("tok-pub-abc"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/content/approve/tok-pub-abc");
    const pub = result.current.data as typeof PUBLIC_APPROVAL;
    expect(pub.status).toBe("pending");
    expect(pub.post.platform).toBe("instagram");
    expect(pub.post.caption).toBe("Caption de aprovação de conteúdo");
  });

  it("error state — expired or not found (404/410)", async () => {
    mockGet.mockRejectedValue(new Error("Approval expired or not found"));
    const { result } = renderHook(() => usePublicApproval("tok-expired"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("expired");
  });

  it("disabled when token is null — no fetch occurs", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => usePublicApproval(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Tests: useDecideApproval mutation (no auth)
// ---------------------------------------------------------------------------

describe("useDecideApproval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("posts approval decision to correct endpoint", async () => {
    mockPost.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useDecideApproval("tok-pub-abc"), {
      wrapper: makeWrapper(),
    });
    await result.current.mutateAsync({ decision: "approved" });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/content/approve/tok-pub-abc",
      expect.objectContaining({ decision: "approved" }),
    );
  });

  it("posts revision decision with feedback", async () => {
    mockPost.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useDecideApproval("tok-pub-abc"), {
      wrapper: makeWrapper(),
    });
    await result.current.mutateAsync({ decision: "revision", feedback: "Precisa de ajustes na legenda" });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/content/approve/tok-pub-abc",
      expect.objectContaining({
        decision: "revision",
        feedback: "Precisa de ajustes na legenda",
      }),
    );
  });

  it("error state — surfaces mutation error", async () => {
    mockPost.mockRejectedValue(new Error("Falha ao registrar decisão"));
    const { result } = renderHook(() => useDecideApproval("tok-pub-abc"), {
      wrapper: makeWrapper(),
    });
    await expect(
      result.current.mutateAsync({ decision: "approved" }),
    ).rejects.toThrow("Falha ao registrar decisão");
  });
});
