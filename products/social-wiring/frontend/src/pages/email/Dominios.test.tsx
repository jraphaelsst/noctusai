import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    delete: (...a: unknown[]) => del(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import EmailDominios from "./Dominios";

const RECORDS = [
  { record: "SPF", type: "TXT", name: "send.ok.example.com", value: "v=spf1 include:amazonses.com ~all" },
  { record: "DKIM", type: "TXT", name: "resend._domainkey.ok.example.com", value: "p=KEY" },
];

function domainRow(over: Record<string, unknown> = {}) {
  return {
    id: "d1",
    org_id: "o1",
    domain: "ok.example.com",
    resend_domain_id: "dom_1",
    status: "pending",
    dns_records: RECORDS,
    verified_at: null,
    created_at: "2026-10-10T00:00:00Z",
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EmailDominios />
    </QueryClientProvider>,
  );
}

describe("EmailDominios", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });
  afterEach(cleanup);

  it("shows the skeleton, then the DNS records of a pending domain", async () => {
    get.mockResolvedValue({ data: [domainRow()] });
    renderPage();
    expect(screen.getByTestId("dominios-loading")).toBeTruthy();
    const dns = await screen.findByTestId("dominio-dns-d1");
    expect(within(dns).getByText("send.ok.example.com")).toBeTruthy();
    expect(within(dns).getByText("p=KEY")).toBeTruthy();
    expect(screen.getByTestId("dominio-status-d1").textContent).toBe("Pendente");
  });

  it("hides the records of a verified domain behind the DNS toggle", async () => {
    get.mockResolvedValue({ data: [domainRow({ status: "verified", verified_at: "2026-10-10T01:00:00Z" })] });
    renderPage();
    expect((await screen.findByTestId("dominio-status-d1")).textContent).toBe("Verificado");
    expect(screen.queryByTestId("dominio-dns-d1")).toBeNull();
    fireEvent.click(screen.getByTestId("dominio-dns-toggle-d1"));
    expect(screen.getByTestId("dominio-dns-d1")).toBeTruthy();
  });

  it("Verificar calls the verify endpoint and refetches the list", async () => {
    get.mockImplementation(async (url: string) =>
      url.endsWith("/verify")
        ? { data: domainRow({ status: "verified" }) }
        : { data: [domainRow()] },
    );
    renderPage();
    fireEvent.click(await screen.findByTestId("dominio-verify-d1"));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith("/api/email-marketing/settings/domains/d1/verify"),
    );
    await waitFor(() =>
      expect(get.mock.calls.filter(([u]) => u === "/api/email-marketing/settings/domains").length).toBe(2),
    );
  });
});
