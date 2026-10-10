/** postHub — the members PUT body field must match BE-1's `MemberSource.body_field` ("membro_ids"). */
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ put: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: (...a: unknown[]) => h.put(...a),
    delete: vi.fn(),
  },
}));
vi.mock("@/hooks/useCardHub", () => ({ uploadMultipart: vi.fn() }));

import { postHub } from "./usePostHub";

describe("postHub members", () => {
  it("PUT /posts/{id}/membros with { membro_ids }", async () => {
    h.put.mockResolvedValue({ items: [] });
    const qc = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => postHub.useSetMembrosMutation("p 1"), { wrapper });
    result.current.mutate(["u1", "u2"]);
    await waitFor(() => expect(h.put).toHaveBeenCalled());
    expect(h.put).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p%201/membros", {
      membro_ids: ["u1", "u2"],
    });
  });
});
