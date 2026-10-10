import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }));

import Descadastro from "./Descadastro";

function renderPage(token = "tok123") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/descadastro/${token}`]}>
        <Routes>
          <Route path="/descadastro/:token" element={<Descadastro />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Descadastro (public)", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });
  afterEach(cleanup);

  it("shows the email and a confirm button for a valid token", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    renderPage();
    expect(screen.getByTestId("descadastro-loading")).toBeTruthy();
    expect(await screen.findByTestId("descadastro-email")).toHaveProperty("textContent", "ana@exemplo.com");
    expect(get).toHaveBeenCalledWith("/api/email-marketing/unsubscribe/tok123");
  });

  it("confirm click POSTs and shows the success state", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    post.mockResolvedValue({ ok: true });
    renderPage();
    fireEvent.click(await screen.findByTestId("descadastro-confirm"));
    await waitFor(() => expect(screen.getByTestId("descadastro-success")).toBeTruthy());
    expect(post).toHaveBeenCalledWith("/api/email-marketing/unsubscribe/tok123");
  });

  it("shows a clear error state for an invalid token (400)", async () => {
    get.mockRejectedValue(Object.assign(new Error("[400] Link de descadastro invalido"), { status: 400 }));
    renderPage("bad");
    expect(await screen.findByTestId("descadastro-invalid")).toBeTruthy();
    expect(screen.queryByTestId("descadastro-confirm")).toBeNull();
  });

  it("keeps the confirm screen with an error when the POST fails", async () => {
    get.mockResolvedValue({ email: "ana@exemplo.com", valid: true });
    post.mockRejectedValue(new Error("boom"));
    renderPage();
    fireEvent.click(await screen.findByTestId("descadastro-confirm"));
    expect(await screen.findByTestId("descadastro-error")).toBeTruthy();
    expect(screen.getByTestId("descadastro-confirm")).toBeTruthy();
  });
});
