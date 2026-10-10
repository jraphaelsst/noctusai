import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }));

import ConfirmarEmail from "./ConfirmarEmail";

function renderPage(token = "tok123") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/confirmar-email/${token}`]}>
        <Routes>
          <Route path="/confirmar-email/:token" element={<ConfirmarEmail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ConfirmarEmail (public)", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });
  afterEach(cleanup);

  it("shows the email and a confirm button for a valid token", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    renderPage();
    expect(screen.getByTestId("confirmar-email-loading")).toBeTruthy();
    expect(await screen.findByTestId("confirmar-email-address")).toHaveProperty("textContent", "ana@exemplo.com");
    expect(get).toHaveBeenCalledWith("/api/email-marketing/confirm/tok123");
  });

  it("confirm click POSTs and shows the success state", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    post.mockResolvedValue({ ok: true });
    renderPage();
    fireEvent.click(await screen.findByTestId("confirmar-email-confirm"));
    await waitFor(() => expect(screen.getByTestId("confirmar-email-success")).toBeTruthy());
    expect(post).toHaveBeenCalledWith("/api/email-marketing/confirm/tok123");
  });

  it("shows a clear error state for an invalid token (400)", async () => {
    get.mockRejectedValue(Object.assign(new Error("[400] Link de confirmação inválido ou expirado"), { status: 400 }));
    renderPage("bad");
    expect(await screen.findByTestId("confirmar-email-invalid")).toBeTruthy();
    expect(screen.queryByTestId("confirmar-email-confirm")).toBeNull();
  });

  it("keeps the confirm screen with an error when the POST fails", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    post.mockRejectedValue(new Error("boom"));
    renderPage();
    fireEvent.click(await screen.findByTestId("confirmar-email-confirm"));
    expect(await screen.findByTestId("confirmar-email-error")).toBeTruthy();
    expect(screen.getByTestId("confirmar-email-confirm")).toBeTruthy();
  });
});

describe("ConfirmarEmail — replay", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });
  afterEach(cleanup);

  it("an already-confirmed link says so", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    post.mockResolvedValue({ ok: true, already: true });
    renderPage();
    fireEvent.click(await screen.findByTestId("confirmar-email-confirm"));
    expect(await screen.findByText("E-mail já confirmado")).toBeTruthy();
  });
});
