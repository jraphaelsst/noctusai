/**
 * AgentsPage tests — renders the grid from the listAgents response.
 *
 * Mocks `@noctusai/seed/infra` at the seed boundary (per the canonical
 * pattern in products/mailing/frontend/src/hooks/__tests__/useAI.test.ts)
 * so no real network or supabase wiring is required.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
}));

function withProviders(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders an agent card per row in the response", async () => {
    mockGet.mockResolvedValue({
      data: [
        { name: "leader", model: "claude-3-7-opus", last_24h_events: 12, last_24h_cost: 0.42, success_rate: 0.91 },
        { name: "backend_engineer", model: "claude-3-7-sonnet", last_24h_events: 5, last_24h_cost: 0.07, success_rate: 1.0 },
      ],
    });

    const { default: AgentsPage } = await import("@/pages/AgentsPage");
    render(withProviders(<AgentsPage />));

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/api/agents"));
    expect(await screen.findByText("leader")).toBeInTheDocument();
    expect(screen.getByText("backend_engineer")).toBeInTheDocument();

    const cards = screen.getAllByTestId("agent-card");
    expect(cards).toHaveLength(2);
  });

  it("surfaces an error envelope when fetch rejects", async () => {
    mockGet.mockRejectedValue(new Error("Servidor indisponivel"));

    const { default: AgentsPage } = await import("@/pages/AgentsPage");
    render(withProviders(<AgentsPage />));

    expect(await screen.findByText(/Failed to load agents/i)).toBeInTheDocument();
  });

  it("renders zero cards when the API returns an empty list", async () => {
    mockGet.mockResolvedValue({ data: [] });

    const { default: AgentsPage } = await import("@/pages/AgentsPage");
    render(withProviders(<AgentsPage />));

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(screen.queryAllByTestId("agent-card")).toHaveLength(0);
  });
});
