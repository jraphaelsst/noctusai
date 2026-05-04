/**
 * AgentDetailPage tests — renders metrics + recent events + config form
 * for one agent. Routing-aware: mounts under MemoryRouter at
 * `/agents/:name` so `useParams` resolves.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch },
}));

function withProviders(ui: React.ReactElement, initialPath = "/agents/leader") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/agents/:name" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AgentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the metrics section + config form for the named agent", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path.includes("/api/agents/leader/metrics")) {
        return Promise.resolve({
          data: {
            agent: "leader",
            scope: null,
            events: 3,
            total_cost_usd: 0.12,
            input_tokens: 4000,
            output_tokens: 800,
            avg_latency_ms: 1500,
            success_rate: 0.66,
            tool_call_distribution: { "noctus.dev.refs": 2 },
          },
        });
      }
      if (path.includes("/api/configs/default")) {
        return Promise.resolve({
          data: {
            agents: {
              leader: { model: "claude-3-7-opus", provider: "anthropic" },
            },
          },
        });
      }
      return Promise.resolve({ data: null });
    });

    const { default: AgentDetailPage } = await import("@/pages/AgentDetailPage");
    render(withProviders(<AgentDetailPage />));

    expect(await screen.findByRole("heading", { name: "leader" })).toBeInTheDocument();
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(
        expect.stringContaining("/api/agents/leader/metrics"),
        undefined,
      ),
    );

    // metrics section + recent-events empty state both rendered
    await waitFor(() => {
      expect(screen.getByTestId("metrics-section")).toBeInTheDocument();
    });
    expect(screen.getByTestId("recent-events-empty")).toBeInTheDocument();
    expect(screen.getByTestId("config-form")).toBeInTheDocument();
  });

  it("shows an error state when the metrics fetch rejects", async () => {
    mockGet.mockImplementation((path: string) => {
      if (path.includes("/api/agents/leader/metrics")) {
        return Promise.reject(new Error("boom"));
      }
      return Promise.resolve({ data: { agents: {} } });
    });

    const { default: AgentDetailPage } = await import("@/pages/AgentDetailPage");
    render(withProviders(<AgentDetailPage />));

    expect(await screen.findByText(/Failed to load agent metrics/i)).toBeInTheDocument();
  });
});
