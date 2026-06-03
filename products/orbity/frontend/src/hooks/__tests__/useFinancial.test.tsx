/**
 * Financial hooks — render tests for all four query states:
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
  useContracts,
  useExpenses,
  useRevenues,
  useCashFlow,
} from "@/hooks/useFinancial";

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

const CONTRACT_ITEM = {
  id: "cid-1",
  org_id: "org-1",
  client_id: null,
  title: "Contrato Mensal Teste",
  monthly_value: 2500.0,
  billing_day: 10,
  start_date: "2026-01-01",
  end_date: null,
  status: "active" as const,
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const CONTRACT_LIST = { items: [CONTRACT_ITEM], total: 1, page: 1, page_size: 50 };
const EMPTY_LIST = { items: [], total: 0, page: 1, page_size: 50 };

const EXPENSE_ITEM = {
  id: "eid-1",
  org_id: "org-1",
  category: "servicos",
  description: "Hospedagem servidor",
  amount: 150.0,
  due_date: "2026-06-15",
  paid: false,
  paid_at: null,
  recurrence: "monthly" as const,
  installments_total: null,
  installment_n: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const REVENUE_ITEM = {
  id: "rid-1",
  org_id: "org-1",
  client_id: null,
  contract_id: "cid-1",
  reference_month: "2026-06-01",
  amount: 2500.0,
  status: "pending" as const,
  due_date: "2026-06-10",
  paid_at: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const CASH_FLOW = {
  reference_month: "2026-06-01",
  paid_revenues: 5000.0,
  paid_expenses: 1200.0,
  net: 3800.0,
  pending_revenues: 1500.0,
  overdue_revenues: 0.0,
};

// ---------------------------------------------------------------------------
// Tests: useContracts
// ---------------------------------------------------------------------------

describe("useContracts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state — query is in-flight", () => {
    mockGet.mockImplementation(() => new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useContracts(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("success state — returns items list with correct shape", async () => {
    mockGet.mockResolvedValue(CONTRACT_LIST);
    const { result } = renderHook(() => useContracts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/financial/contracts",
      expect.objectContaining({ page: 1, page_size: 50 }),
    );
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].title).toBe("Contrato Mensal Teste");
    expect(result.current.data?.items[0].monthly_value).toBe(2500.0);
    expect(result.current.data?.total).toBe(1);
  });

  it("empty state — returns zero items", async () => {
    mockGet.mockResolvedValue(EMPTY_LIST);
    const { result } = renderHook(() => useContracts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(0);
    expect(result.current.data?.total).toBe(0);
  });

  it("error state — exposes error message", async () => {
    mockGet.mockRejectedValue(new Error("Falha de rede"));
    const { result } = renderHook(() => useContracts(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Falha de rede");
    expect(result.current.data).toBeUndefined();
  });

  it("passes status filter as query param", async () => {
    mockGet.mockResolvedValue(CONTRACT_LIST);
    const { result } = renderHook(
      () => useContracts({ status: "active" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/financial/contracts",
      expect.objectContaining({ status: "active" }),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: useExpenses
// ---------------------------------------------------------------------------

describe("useExpenses", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loading state", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useExpenses(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("success state — returns expense items", async () => {
    mockGet.mockResolvedValue({ items: [EXPENSE_ITEM], total: 1, page: 1, page_size: 50 });
    const { result } = renderHook(() => useExpenses(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/financial/expenses",
      expect.objectContaining({ page: 1 }),
    );
    expect(result.current.data?.items[0].description).toBe("Hospedagem servidor");
    expect(result.current.data?.items[0].paid).toBe(false);
    expect(result.current.data?.items[0].recurrence).toBe("monthly");
  });

  it("empty state — returns zero items", async () => {
    mockGet.mockResolvedValue(EMPTY_LIST);
    const { result } = renderHook(() => useExpenses(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(0);
  });

  it("error state — exposes error", async () => {
    mockGet.mockRejectedValue(new Error("502 Bad Gateway"));
    const { result } = renderHook(() => useExpenses(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("502");
  });
});

// ---------------------------------------------------------------------------
// Tests: useRevenues
// ---------------------------------------------------------------------------

describe("useRevenues", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("success state — returns revenue items with correct shape", async () => {
    mockGet.mockResolvedValue({ items: [REVENUE_ITEM], total: 1, page: 1, page_size: 50 });
    const { result } = renderHook(() => useRevenues(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      "/api/financial/revenues",
      expect.objectContaining({ page: 1 }),
    );
    expect(result.current.data?.items[0].status).toBe("pending");
    expect(result.current.data?.items[0].amount).toBe(2500.0);
    expect(result.current.data?.items[0].contract_id).toBe("cid-1");
  });

  it("error state — surfaces error", async () => {
    mockGet.mockRejectedValue(new Error("Servidor indisponivel"));
    const { result } = renderHook(() => useRevenues(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Tests: useCashFlow
// ---------------------------------------------------------------------------

describe("useCashFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("success state — all summary fields present and correct", async () => {
    mockGet.mockResolvedValue(CASH_FLOW);
    const { result } = renderHook(() => useCashFlow("2026-06"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Hook converts "2026-06" → "2026-06-01" for the backend path param
    expect(mockGet).toHaveBeenCalledWith("/api/financial/cash-flow/2026-06-01");
    expect(result.current.data?.net).toBe(3800.0);
    expect(result.current.data?.paid_revenues).toBe(5000.0);
    expect(result.current.data?.paid_expenses).toBe(1200.0);
    expect(result.current.data?.pending_revenues).toBe(1500.0);
    expect(result.current.data?.overdue_revenues).toBe(0.0);
  });

  it("error state — network failure surfaced", async () => {
    mockGet.mockRejectedValue(new Error("Falha ao calcular fluxo de caixa"));
    const { result } = renderHook(() => useCashFlow("2026-06"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("fluxo de caixa");
  });

  it("disabled when month is empty — no fetch occurs", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    const { result } = renderHook(() => useCashFlow(""), {
      wrapper: makeWrapper(),
    });
    // enabled=false → fetchStatus=idle, never fetched
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});
