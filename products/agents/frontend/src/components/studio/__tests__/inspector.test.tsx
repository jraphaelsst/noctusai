/**
 * The "Prompt compilado" inspector — section rendering driven by manifest
 * offsets (CONTRACT §C), source click-through, and the full CompiledTab
 * wired through the real api client with `fetch` faked at the network
 * boundary (contract-shaped fixtures).
 */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AGENT_DETAIL,
  CLIENT_ID,
  CLIENT_SUMMARY,
  COMPILED_DRAFT,
  COMPILED_WITH_CLIENT,
  DIFF_V1_V2,
  SEC_ID,
  V1_ID,
  V2_ID,
  assembleCompiled,
} from "@/api/studio/__fixtures__/contract";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import type { ManifestSection } from "@/api/studio/types";
import { segmentCompiled, sourceTarget } from "@/components/studio/compiledSegments";
import { CompiledPromptView } from "@/components/studio/CompiledPromptView";
import { lineDiff } from "@/components/studio/lineDiff";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "token-de-teste" }) };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const A = "/api/studio/agents/estrategista";

describe("segmentCompiled", () => {
  it("cuts texto exactly at the manifest offsets and drops only the \\n\\n separators", () => {
    const { segmentos, problemas } = segmentCompiled(COMPILED_DRAFT.texto, COMPILED_DRAFT.manifest);
    expect(problemas).toEqual([]);
    expect(segmentos.every((s) => s.tipo === "secao")).toBe(true);
    expect(segmentos).toHaveLength(COMPILED_DRAFT.manifest.length);
    for (const s of segmentos) {
      if (s.tipo !== "secao") continue;
      expect(s.texto).toBe(COMPILED_DRAFT.texto.slice(s.secao.inicio, s.secao.fim));
      expect(s.texto.startsWith(`# ${s.secao.titulo}`)).toBe(true);
    }
    // Rejoining the blocks with the §C separator reproduces the text byte for byte.
    expect(segmentos.map((s) => s.texto).join("\n\n")).toBe(COMPILED_DRAFT.texto);
  });

  it("orders by offset even when the manifest arrives out of order, keeping each block's manifest index", () => {
    const reversed = [...COMPILED_DRAFT.manifest].reverse();
    const { segmentos } = segmentCompiled(COMPILED_DRAFT.texto, reversed);
    const chaves = segmentos.map((s) => (s.tipo === "secao" ? s.secao.chave : "?"));
    expect(chaves).toEqual(COMPILED_DRAFT.manifest.map((m) => m.chave));
    const first = segmentos[0];
    expect(first.tipo === "secao" && first.indice).toBe(reversed.length - 1);
  });

  it("surfaces text outside every manifest range instead of hiding it", () => {
    const { texto, manifest } = assembleCompiled([
      { chave: "a", titulo: "A", origem: { tipo: "secao", id: "x", campo: null }, body: "corpo a" },
    ]);
    const withStray = `${texto}\n\ntexto solto`;
    const { segmentos } = segmentCompiled(withStray, manifest);
    const orphan = segmentos.find((s) => s.tipo === "orfao");
    expect(orphan && orphan.texto.trim()).toBe("texto solto");
  });

  it("reports out-of-range and overlapping offsets as problems", () => {
    const m = COMPILED_DRAFT.manifest;
    const bad: ManifestSection[] = [m[0], { ...m[1], inicio: m[0].fim - 3 }, { ...m[2], fim: COMPILED_DRAFT.texto.length + 50 }];
    const { problemas } = segmentCompiled(COMPILED_DRAFT.texto, bad);
    expect(problemas).toHaveLength(2);
    expect(problemas.some((p) => p.includes("sobrepõe"))).toBe(true);
    expect(problemas.some((p) => p.includes("limites inválidos"))).toBe(true);
  });

  // The backend counts offsets as Python `len(str)` — Unicode CODE POINTS.
  // An astral character (e.g. most emoji) is a surrogate PAIR in JS: 2 UTF-16
  // units but 1 backend offset. These fixtures build offsets the same way the
  // backend does (code-point counting), independent of `assembleCompiled`
  // (whose ASCII-only fixtures never exercise this).
  const cpLen = (s: string) => Array.from(s).length;

  it("slices correctly when an astral character (emoji) sits before the section", () => {
    const emoji = "🎉"; // U+1F389 — 2 UTF-16 code units, 1 code point
    const pre = `${emoji} nota solta`;
    const corpo = "Conteúdo normal da seção.";
    const bloco = `# Titulo\n\n${corpo}`;
    const texto = `${pre}\n\n${bloco}`;
    const inicio = cpLen(`${pre}\n\n`);
    const fim = cpLen(texto);
    const manifest: ManifestSection[] = [
      { chave: "sec", titulo: "Titulo", origem: { tipo: "secao", id: SEC_ID, campo: null }, inicio, fim, chars: fim - inicio, tokens: 1 },
    ];

    // A naive `texto.slice(inicio, fim)` (UTF-16 units) would land 1 unit
    // short of the block because of the surrogate pair — proving the fix
    // matters, not just that it "still works".
    expect(texto.slice(inicio, fim)).not.toBe(bloco);

    const { segmentos, problemas } = segmentCompiled(texto, manifest);
    expect(problemas).toEqual([]);
    const [orphan, secao] = segmentos;
    expect(orphan.tipo).toBe("orfao");
    expect(orphan.tipo === "orfao" && orphan.texto.trim()).toBe(pre);
    expect(secao.tipo === "secao" && secao.texto).toBe(bloco);
  });

  it("slices correctly when astral characters sit INSIDE the section body", () => {
    const emoji = "🎉🚀"; // two astral characters = 4 UTF-16 units, 2 code points
    const corpo = `Antes ${emoji} depois`;
    const bloco = `# Titulo\n\n${corpo}`;
    const texto = bloco;
    const manifest: ManifestSection[] = [
      { chave: "sec", titulo: "Titulo", origem: { tipo: "secao", id: SEC_ID, campo: null }, inicio: 0, fim: cpLen(texto), chars: cpLen(texto), tokens: 1 },
    ];

    const { segmentos, problemas } = segmentCompiled(texto, manifest);
    expect(problemas).toEqual([]);
    expect(segmentos).toHaveLength(1);
    const [secao] = segmentos;
    expect(secao.tipo === "secao" && secao.texto).toBe(bloco);
  });
});

describe("sourceTarget", () => {
  const [identidade, , skills, ferramentas] = COMPILED_DRAFT.manifest;
  const cliente = COMPILED_WITH_CLIENT.manifest[COMPILED_WITH_CLIENT.manifest.length - 1];

  it("links author sections to the Prompt tab by id + chave", () => {
    expect(sourceTarget(identidade)).toMatchObject({ tab: "prompt", params: { secao: SEC_ID, chave: "identidade" } });
  });
  it("links the §C auto blocks by their pinned titles", () => {
    expect(sourceTarget(skills)?.tab).toBe("skills");
    expect(sourceTarget(ferramentas)?.tab).toBe("configuracoes");
    expect(sourceTarget(cliente, CLIENT_ID)).toMatchObject({ tab: "clientes", params: { cliente: CLIENT_ID } });
  });
  it("returns null for an unknown auto block rather than guessing", () => {
    expect(sourceTarget({ ...skills, titulo: "Outra coisa" })).toBeNull();
  });
});

describe("CompiledPromptView", () => {
  it("renders one labelled block per manifest entry with the sliced text", () => {
    render(<CompiledPromptView texto={COMPILED_DRAFT.texto} manifest={COMPILED_DRAFT.manifest} />);
    const blocks = screen.getAllByTestId("compiled-section");
    expect(blocks).toHaveLength(COMPILED_DRAFT.manifest.length);
    blocks.forEach((el, i) => {
      const m = COMPILED_DRAFT.manifest[i];
      expect(el.getAttribute("data-chave")).toBe(m.chave);
      expect(el.getAttribute("data-inicio")).toBe(String(m.inicio));
      expect(el.getAttribute("data-fim")).toBe(String(m.fim));
      expect(el.querySelector("pre")?.textContent).toBe(COMPILED_DRAFT.texto.slice(m.inicio, m.fim));
      expect(within(el).getByText(`~${m.tokens} tokens`, { exact: false })).toBeTruthy();
    });
    expect(screen.queryByTestId("compiled-orphan")).toBeNull();
  });

  it("calls onOpenSource with the block's source target", () => {
    const onOpen = vi.fn();
    render(<CompiledPromptView texto={COMPILED_DRAFT.texto} manifest={COMPILED_DRAFT.manifest} onOpenSource={onOpen} />);
    fireEvent.click(screen.getAllByTestId("compiled-open-source")[0]);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ tab: "prompt", params: { secao: SEC_ID, chave: "identidade" } }));
  });

  // The Agent SDK wraps every launch with a fixed identity line + a
  // generated `# Environment` block that the compiler cannot see or hash
  // (tech-lead runtime finding) — the inspector must show both, honestly
  // labelled as outside the hash/token count.
  it("renders the runtime prefix and suffix blocks, outside the manifest sections", () => {
    render(<CompiledPromptView texto={COMPILED_DRAFT.texto} manifest={COMPILED_DRAFT.manifest} />);
    const prefix = screen.getByTestId("runtime-prefix-block");
    expect(prefix.textContent).toContain("You are a Claude agent, built on Anthropic's Claude Agent SDK.");
    expect(prefix.textContent).toContain("não faz parte do hash");
    const suffix = screen.getByTestId("runtime-suffix-block");
    expect(suffix.textContent).toContain("Environment");
    expect(suffix.textContent).toContain("não faz parte do hash");
    expect(screen.getByTestId("runtime-preamble-tokens").textContent).toContain("+60");
  });
});

describe("lineDiff", () => {
  it("aligns equal, changed, removed and added lines", () => {
    const d = lineDiff("a\nb\nc", "a\nB\nc\nd");
    expect(d.linhas.map((l) => l.tipo)).toEqual(["igual", "alterada", "igual", "adicionada"]);
    expect(d.adicionadas).toBe(2);
    expect(d.removidas).toBe(1);
  });
});

// ── Full tab through the network boundary ─────────────────────────────────────

function LocationProbe() {
  const loc = useLocation();
  return <output data-testid="location">{`${loc.pathname}${loc.search}`}</output>;
}

async function renderCompiledTab(initial = "/studio/estrategista?tab=compilado") {
  const CompiledTab = (await import("@/pages/studio/tabs/CompiledTab")).default;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route
            path="/studio/:key"
            element={
              <>
                <CompiledTab agentKey="estrategista" />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const TAB_ROUTES = [
  { method: "GET" as const, path: A, body: AGENT_DETAIL },
  { method: "GET" as const, path: `${A}/clients`, body: { items: [CLIENT_SUMMARY] } },
  { method: "GET" as const, path: `${A}/versions/${V2_ID}/compiled`, body: COMPILED_DRAFT },
  { method: "GET" as const, path: `${A}/versions/${V1_ID}/diff/${V2_ID}`, body: DIFF_V1_V2 },
];

describe("CompiledTab (inspector)", () => {
  it("defaults to the draft and renders hash, tokens, token bar, warnings, sections and the on-demand layer", async () => {
    const net = installFetch(TAB_ROUTES);
    await renderCompiledTab();

    await waitFor(() => expect(screen.getAllByTestId("compiled-section")).toHaveLength(COMPILED_DRAFT.manifest.length));
    expect(net.calls.find((c) => c.path.endsWith("/compiled"))?.path).toBe(`${A}/versions/${V2_ID}/compiled`);
    expect(screen.getByTestId("compiled-hash").getAttribute("title")).toBe(COMPILED_DRAFT.hash);
    expect(screen.getByTestId("compiled-tokens").textContent).toContain(String(COMPILED_DRAFT.tokens_estimados));
    expect(screen.getByTestId("section-token-bar")).toBeTruthy();
    expect(within(screen.getByTestId("compiled-avisos")).getByText(COMPILED_DRAFT.avisos[0].mensagem)).toBeTruthy();
    expect(screen.getAllByTestId("sob-demanda-item")).toHaveLength(COMPILED_DRAFT.sob_demanda.length);
    expect(net.unmatched).toEqual([]);
  });

  it("'Comparar com publicada' requests the diff active → selected and renders it", async () => {
    const net = installFetch(TAB_ROUTES);
    await renderCompiledTab();
    fireEvent.click(await screen.findByTestId("compiled-compare-toggle"));
    await waitFor(() => expect(screen.getByTestId("version-diff")).toBeTruthy());
    expect(net.calls.some((c) => c.path === `${A}/versions/${V1_ID}/diff/${V2_ID}`)).toBe(true);
    expect(screen.getByTestId("compiled-diff")).toBeTruthy();
  });

  it("selecting a client recompiles with client_id", async () => {
    const net = installFetch([
      ...TAB_ROUTES.filter((r) => !r.path.endsWith("/compiled")),
      { method: "GET", path: `${A}/versions/${V2_ID}/compiled`, body: COMPILED_WITH_CLIENT },
    ]);
    await renderCompiledTab();
    const select = (await screen.findByTestId("compiled-client-select")) as HTMLSelectElement;
    await waitFor(() => expect(select.disabled).toBe(false));
    fireEvent.change(select, { target: { value: CLIENT_ID } });
    await waitFor(() => expect(net.calls.some((c) => c.search.get("client_id") === CLIENT_ID)).toBe(true));
    await waitFor(() => expect(screen.getAllByTestId("compiled-section")).toHaveLength(COMPILED_WITH_CLIENT.manifest.length));
  });

  it("click-through navigates to the Prompt tab with the section deep link", async () => {
    installFetch(TAB_ROUTES);
    await renderCompiledTab();
    const buttons = await screen.findAllByTestId("compiled-open-source");
    fireEvent.click(buttons[0]);
    await waitFor(() =>
      expect(screen.getByTestId("location").textContent).toBe(`/studio/estrategista?tab=prompt&secao=${SEC_ID}&chave=identidade`),
    );
  });

  it("shows the error state with the backend's message when the compile fails", async () => {
    installFetch([
      ...TAB_ROUTES.filter((r) => !r.path.endsWith("/compiled")),
      { method: "GET", path: `${A}/versions/${V2_ID}/compiled`, status: 404, body: { detail: "Versão não encontrada.", code: "version_not_found" } },
    ]);
    await renderCompiledTab();
    expect((await screen.findByTestId("studio-error")).textContent).toContain("Versão não encontrada.");
  });
});
