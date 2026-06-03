/**
 * useRelatorios hooks — render tests covering all four query states:
 *   loading → success (with data) → success (empty list) → error
 *
 * Mocking pattern:
 *   vi.mock factories CANNOT reference variables declared in the module scope
 *   because vitest hoists vi.mock() calls above all variable declarations.
 *   Solution: use vi.hoisted() to create shared mock functions so they are
 *   initialized before the factory runs.
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
  useReports,
  useReport,
  useReportSnapshots,
  usePublicReport,
} from "@/hooks/useRelatorios";

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

const REPORT_ITEM = {
  id: "rep-1",
  org_id: "org-1",
  client_id: null,
  name: "Relatório Q1 2026",
  public_token: "pub-tok-abc-123",
  period_start: "2026-01-01",
  period_end: "2026-03-31",
  config: {},
  status: "draft" as const,
  expires_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const PUBLISHED_REPORT = {
  ...REPORT_ITEM,
  id: "rep-2",
  name: "Relatório Q2 Publicado",
  status: "published" as const,
};

const SNAPSHOT_ITEM = {
  id: "snap-1",
  org_id: "org-1",
  report_id: "rep-1",
  generated_at: "2026-06-01T10:00:00Z",
  payload: {
    leads: 42,
    revenues: 15000.0,
    expenses: 4800.0,
  },
};

const PUBLIC_REPORT = {
  report_id: "rep-2",
  name: "Relatório Q2 Publicado",
  period_start: "2026-04-01",
  period_end: "2026-06-30",
  status: "published",
  expires_at: null,
  snapshot_id: "snap-2",
  generated_at: "2026-06-01T12:00:00Z",
  payload: { leads: 18, revenues: 8500 },
};

// ---------------------------------------------------------------------------
// Tests: useReports
// ---------------------------------------------------------------------------

describe("useReports", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state — query is in-flight", () => {
    mockGet.mockImplementation(() => new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useReports(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("success state — returns list with correct shape", async () => {
    mockGet.mockResolvedValue([REPORT_ITEM]);
    const { result } = renderHook(() => useReports(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/reports",
      expect.objectContaining({}),
    );
    expect(Array.isArray(result.current.data)).toBe(true);
    const items = result.current.data as typeof REPORT_ITEM[];
    expect(items).toHaveLength(1);
    expect(items[0].name).toBe("Relatório Q1 2026");
    expect(items[0].status).toBe("draft");
    expect(items[0].public_token).toBe("pub-tok-abc-123");
  });

  it("empty state — returns empty array", async () => {
    mockGet.mockResolvedValue([]);
    const { result } = renderHook(() => useReports(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(Array.isArray(result.current.data)).toBe(true);
    expect((result.current.data as unknown[]).length).toBe(0);
  });

  it("error state — exposes error message", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar relatórios"));
    const { result } = renderHook(() => useReports(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("Falha ao listar relatórios");
    expect(result.current.data).toBeUndefined();
  });

  it("passes status filter as query param", async () => {
    mockGet.mockResolvedValue([PUBLISHED_REPORT]);
    const { result } = renderHook(
      () => useReports({ status: "published" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/reports",
      expect.objectContaining({ status: "published" }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: useReport (single)
// ---------------------------------------------------------------------------

describe("useReport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("success state — returns single report", async () => {
    mockGet.mockResolvedValue(REPORT_ITEM);
    const { result } = renderHook(() => useReport("rep-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/reports/rep-1");
    const report = result.current.data as typeof REPORT_ITEM;
    expect(report.name).toBe("Relatório Q1 2026");
    expect(report.period_start).toBe("2026-01-01");
    expect(report.period_end).toBe("2026-03-31");
  });

  it("disabled when id is null — no fetch occurs", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useReport(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("error state — surfaces 404", async () => {
    mockGet.mockRejectedValue(new Error("Relatório não encontrado"));
    const { result } = renderHook(() => useReport("rep-nonexistent"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("não encontrado");
  });
});

// ---------------------------------------------------------------------------
// Tests: useReportSnapshots
// ---------------------------------------------------------------------------

describe("useReportSnapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useReportSnapshots("rep-1"), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("success state — returns snapshots with payload", async () => {
    mockGet.mockResolvedValue([SNAPSHOT_ITEM]);
    const { result } = renderHook(() => useReportSnapshots("rep-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/reports/rep-1/snapshots");
    const snaps = result.current.data as typeof SNAPSHOT_ITEM[];
    expect(snaps).toHaveLength(1);
    expect(snaps[0].payload.leads).toBe(42);
    expect(snaps[0].payload.revenues).toBe(15000.0);
    expect(snaps[0].payload.expenses).toBe(4800.0);
  });

  it("empty state — returns empty array (no snapshots yet)", async () => {
    mockGet.mockResolvedValue([]);
    const { result } = renderHook(() => useReportSnapshots("rep-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect((result.current.data as unknown[]).length).toBe(0);
  });

  it("error state — surfaces error", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao listar snapshots"));
    const { result } = renderHook(() => useReportSnapshots("rep-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("snapshots");
  });

  it("disabled when reportId is null — no fetch occurs", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useReportSnapshots(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Tests: usePublicReport (no auth)
// ---------------------------------------------------------------------------

describe("usePublicReport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("success state — returns public report with snapshot payload", async () => {
    mockGet.mockResolvedValue(PUBLIC_REPORT);
    const { result } = renderHook(() => usePublicReport("pub-tok-xyz"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/reports/public/pub-tok-xyz");
    const pub = result.current.data as typeof PUBLIC_REPORT;
    expect(pub.name).toBe("Relatório Q2 Publicado");
    expect(pub.status).toBe("published");
    expect(pub.payload.leads).toBe(18);
    expect(pub.snapshot_id).toBe("snap-2");
  });

  it("error state — not found or expired (404)", async () => {
    mockGet.mockRejectedValue(
      new Error("Relatório não encontrado, não publicado ou expirado"),
    );
    const { result } = renderHook(() => usePublicReport("tok-expired"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("expirado");
  });

  it("disabled when token is null — no fetch occurs", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => usePublicReport(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});
