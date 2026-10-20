/** TextosTab — draft-only edits, replace-set PUT shape, optimistic-lock conflict, read-only published. */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch, TEST_BASE_URL } from "@/api/studio/__fixtures__/fetchMock";
import { ACTIVE_ID, DRAFT_ID, KEY, TEXTOS, agentDetail } from "./juliaFixtures";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));

import TextosTab from "../TextosTab";

const A = `/api/studio/agents/${KEY}`;
void TEST_BASE_URL;

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><TextosTab agentKey={KEY} /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TextosTab", () => {
  it("groups by category, marks empty rows and shows 'Rascunho vs publicada'", async () => {
    installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${A}/versions/${DRAFT_ID}/textos`, body: { version_id: DRAFT_ID, itens: TEXTOS } },
      { method: "GET", path: "/api/studio/plataforma/textos", body: { itens: [] } },
    ]);
    renderTab();
    expect(await screen.findByTestId("textos-grupo-grupo")).toBeTruthy();
    expect(screen.getByTestId("textos-grupo-outro")).toBeTruthy();
    expect(screen.getByTestId("conteudo-estado").textContent).toContain("Rascunho v2");
    expect(screen.getByText("vazio")).toBeTruthy();
  });

  it("PUTs the whole set (no ids) after a compare-before-write and refetches", async () => {
    const net = installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${A}/versions/${DRAFT_ID}/textos`, body: { version_id: DRAFT_ID, itens: TEXTOS } },
      { method: "PUT", path: `${A}/draft/textos`, body: { version_id: DRAFT_ID, itens: TEXTOS } },
      { method: "GET", path: "/api/studio/plataforma/textos", body: { itens: [] } },
    ]);
    renderTab();
    const area = (await screen.findByLabelText("grupo.dois")) as HTMLTextAreaElement;
    fireEvent.change(area, { target: { value: "novo texto sintético" } });
    fireEvent.click(screen.getByTestId("textos-salvar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    const put = net.calls.find((c) => c.method === "PUT")!;
    expect(put.body).toEqual({
      itens: [
        { chave: "grupo.um", conteudo: "texto sintético um" },
        { chave: "grupo.dois", conteudo: "novo texto sintético" },
        { chave: "outro.tres", conteudo: "texto sintético três" },
      ],
    });
    // The compare-before-write read happened BEFORE the write.
    const gets = net.calls.filter((c) => c.method === "GET" && c.path.endsWith("/textos") && c.path.includes("versions"));
    expect(gets.length).toBeGreaterThanOrEqual(2);
    expect(net.unmatched).toEqual([]);
  });

  it("surfaces an optimistic-lock conflict and never PUTs when the server moved", async () => {
    let reads = 0;
    const net = installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${A}/versions/${DRAFT_ID}/textos`, body: { version_id: DRAFT_ID, itens: TEXTOS } },
      { method: "GET", path: "/api/studio/plataforma/textos", body: { itens: [] } },
    ]);
    // Swap the textos route after the first load: the server moved under the form.
    const original = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.pathname.endsWith(`/versions/${DRAFT_ID}/textos`)) {
        reads += 1;
        if (reads > 1) {
          return new Response(JSON.stringify({ version_id: DRAFT_ID, itens: [{ id: "t9", chave: "grupo.um", conteudo: "alterado por outra pessoa" }] }), { status: 200, headers: { "content-type": "application/json" } });
        }
      }
      return original(input, init);
    }));
    renderTab();
    const area = (await screen.findByLabelText("grupo.dois")) as HTMLTextAreaElement;
    fireEvent.change(area, { target: { value: "edição local" } });
    fireEvent.click(screen.getByTestId("textos-salvar"));
    expect((await screen.findByTestId("conteudo-erro")).textContent).toContain("Outra pessoa alterou este rascunho");
    expect(net.calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("is read-only on a published version and offers 'Criar rascunho'", async () => {
    installFetch([
      { method: "GET", path: A, body: agentDetail({}, false) },
      { method: "GET", path: `${A}/versions/${ACTIVE_ID}/textos`, body: { version_id: ACTIVE_ID, itens: TEXTOS } },
      { method: "GET", path: "/api/studio/plataforma/textos", body: { itens: [] } },
    ]);
    renderTab();
    expect(await screen.findByTestId("conteudo-criar-rascunho")).toBeTruthy();
    expect(screen.getByTestId("conteudo-estado").textContent).toContain("somente leitura");
    expect(screen.queryByTestId("textos-salvar")).toBeNull();
    expect((screen.getByLabelText("grupo.um") as HTMLTextAreaElement).readOnly).toBe(true);
  });

  it("shows the restricted state for a non platform admin (403)", async () => {
    installFetch([
      { method: "GET", path: A, body: agentDetail() },
      { method: "GET", path: `${A}/versions/${DRAFT_ID}/textos`, status: 403, body: { detail: "x", code: "platform_admin_required" } },
    ]);
    renderTab();
    expect((await screen.findByTestId("studio-restrito")).textContent).toContain("administradores da plataforma");
  });
});
