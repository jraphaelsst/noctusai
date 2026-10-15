/**
 * The public client-approval page. Born from the 2026-10-15 live smoke: the page
 * read `data.status` / `data.post.*` while the backend (`PublicApprovalView`)
 * returns a FLAT `approval_status` shape — every link showed "Decisão já
 * registrada" and no client could ever approve. Fixtures here mirror the
 * backend payload exactly.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom";

const { mockApproval, mockMutate } = vi.hoisted(() => ({
  mockApproval: vi.fn(),
  mockMutate: vi.fn(),
}));

vi.mock("@/hooks/useConteudo", () => ({
  usePublicApproval: () => mockApproval(),
  useDecideApproval: () => ({ mutate: mockMutate, isPending: false, isError: false }),
}));

import AprovacaoPublica from "../AprovacaoPublica";

const pendingPayload = {
  approval_id: "apv-1",
  post_id: "post-1",
  platform: "instagram",
  caption: "Legenda para aprovar",
  hashtags: null,
  media_url: null,
  scheduled_for: null,
  approval_status: "pending",
  expires_at: "2099-01-01T00:00:00Z",
};

const ok = (data: unknown) => ({ data, isPending: false, isLoading: false, isError: false, error: null });

const renderIt = () =>
  render(
    <MemoryRouter initialEntries={["/aprovar/tok-1"]}>
      <Routes>
        <Route path="/aprovar/:token" element={<AprovacaoPublica />} />
      </Routes>
    </MemoryRouter>,
  );

describe("AprovacaoPublica", () => {
  beforeEach(() => {
    mockApproval.mockReset();
    mockMutate.mockReset();
  });

  it("pending approval shows the post and the decision buttons", () => {
    mockApproval.mockReturnValue(ok(pendingPayload));
    renderIt();
    expect(screen.getByText("Legenda para aprovar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Aprovar/ })).toBeInTheDocument();
    expect(screen.queryByText("Decisão já registrada")).not.toBeInTheDocument();
  });

  it("an already-decided approval shows the terminal state", () => {
    mockApproval.mockReturnValue(ok({ ...pendingPayload, approval_status: "approved" }));
    renderIt();
    expect(screen.getByText("Decisão já registrada")).toBeInTheDocument();
  });

  it("only claims the team was notified when the backend says so", async () => {
    mockApproval.mockReturnValue(ok(pendingPayload));
    mockMutate.mockImplementation((_vars, opts) => opts.onSuccess({ ok: true, team_notified: 0 }));
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: /Aprovar/ }));
    await waitFor(() => expect(screen.getByText("Conteúdo aprovado!")).toBeInTheDocument());
    expect(screen.getByText("Ótimo! Sua aprovação foi registrada.")).toBeInTheDocument();
    expect(screen.queryByText(/equipe foi notificada/)).not.toBeInTheDocument();
  });

  it("confirms the notification when at least one teammate was notified", async () => {
    mockApproval.mockReturnValue(ok(pendingPayload));
    mockMutate.mockImplementation((_vars, opts) => opts.onSuccess({ ok: true, team_notified: 2 }));
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: /Aprovar/ }));
    await waitFor(() => expect(screen.getByText(/equipe foi notificada/)).toBeInTheDocument());
  });
});
