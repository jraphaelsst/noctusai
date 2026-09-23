/**
 * Agent Studio hooks — request shapes against CONTRACT §D1/§D2, cache
 * invalidation, and the two-signal loading projection.
 *
 * `@/lib/api` is swapped for the REAL seed `createApiClient` pointed at a
 * test base URL; `fetch` is faked at the network boundary (`fetchMock.ts`)
 * with contract-shaped fixtures. So every assertion below is about what goes
 * over the wire, not about which wrapper method was called.
 */
import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AGENT_DETAIL,
  AGENT_SUMMARY,
  CLIENT,
  CLIENT_ID,
  CLIENT_SUMMARY,
  COMPILED_DRAFT,
  COMPILED_WITH_CLIENT,
  DIFF_V1_V2,
  DRAFT_DETAIL,
  ENTRY_ID,
  FILE_ID,
  LEGACY_SUMMARY,
  SKILL_ID,
  STORED_PROMPT,
  V1_ID,
  V2_ID,
} from "@/api/studio/__fixtures__/contract";
import { installFetch, TEST_BASE_URL } from "@/api/studio/__fixtures__/fetchMock";
import { ApiError } from "@/lib/errors";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "token-de-teste" }) };
});

const A = "/api/studio/agents/estrategista";

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}
function wrap(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
}

afterEach(() => vi.unstubAllGlobals());

describe("useStudioAgents / useStudioAgent", () => {
  it("GETs the list and projects showSkeleton → false with data", async () => {
    const net = installFetch([{ method: "GET", path: "/api/studio/agents", body: { items: [AGENT_SUMMARY, LEGACY_SUMMARY] } }]);
    const { useStudioAgents } = await import("@/hooks/studio/useStudioAgents");
    const { result } = renderHook(() => useStudioAgents(), { wrapper: wrap(newClient()) });

    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(result.current.data?.map((a) => a.key)).toEqual(["estrategista", "julia"]);
    expect(result.current.isRefreshing).toBe(false);
    expect(net.calls[0]).toMatchObject({ method: "GET", path: "/api/studio/agents" });
    expect(net.unmatched).toEqual([]);
    expect(result.current).not.toHaveProperty("isLoading");
  });

  it("surfaces 409 not_studio_agent as an ApiError carrying the flat code, without retrying", async () => {
    const net = installFetch([
      {
        method: "GET",
        path: "/api/studio/agents/julia",
        status: 409,
        body: { detail: "Agente legado não é editável no Studio.", code: "not_studio_agent" },
      },
    ]);
    const { useStudioAgent } = await import("@/hooks/studio/useStudioAgents");
    const { result } = renderHook(() => useStudioAgent("julia"), {
      wrapper: wrap(new QueryClient()), // default retries ON — the hook itself must disable them
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).code).toBe("not_studio_agent");
    expect(net.calls).toHaveLength(1);
  });

  it("POSTs a new agent with {key, nome, descricao}", async () => {
    const net = installFetch([{ method: "POST", path: "/api/studio/agents", status: 201, body: AGENT_SUMMARY }]);
    const { useCreateStudioAgent } = await import("@/hooks/studio/useStudioAgents");
    const { result } = renderHook(() => useCreateStudioAgent(), { wrapper: wrap(newClient()) });
    await act(() => result.current.mutateAsync({ key: "estrategista", nome: "Estrategista", descricao: "x" }));
    expect(net.calls[0]).toMatchObject({
      method: "POST",
      path: "/api/studio/agents",
      body: { key: "estrategista", nome: "Estrategista", descricao: "x" },
    });
  });

  it("PATCHes the agent and patches the cached detail in place", async () => {
    const net = installFetch([
      { method: "GET", path: A, body: AGENT_DETAIL },
      { method: "PATCH", path: A, body: { ...AGENT_SUMMARY, publicacao_limiar: 0.9 } },
    ]);
    const { useStudioAgent, useUpdateStudioAgent } = await import("@/hooks/studio/useStudioAgents");
    const qc = newClient();
    const detail = renderHook(() => useStudioAgent("estrategista"), { wrapper: wrap(qc) });
    await waitFor(() => expect(detail.result.current.data).toBeDefined());
    const upd = renderHook(() => useUpdateStudioAgent("estrategista"), { wrapper: wrap(qc) });
    await act(() => upd.result.current.mutateAsync({ publicacao_limiar: 0.9 }));
    expect(net.calls.find((c) => c.method === "PATCH")?.body).toEqual({ publicacao_limiar: 0.9 });
    await waitFor(() => expect(detail.result.current.data?.publicacao_limiar).toBe(0.9));
    expect(detail.result.current.data?.versoes).toHaveLength(2); // detail-only field kept
  });
});

describe("useVersions — draft lifecycle", () => {
  it("GETs a version by id", async () => {
    const net = installFetch([{ method: "GET", path: `${A}/versions/${V2_ID}`, body: DRAFT_DETAIL }]);
    const { useVersion } = await import("@/hooks/studio/useVersions");
    const { result } = renderHook(() => useVersion("estrategista", V2_ID), { wrapper: wrap(newClient()) });
    await waitFor(() => expect(result.current.data?.id).toBe(V2_ID));
    expect(net.calls[0].path).toBe(`${A}/versions/${V2_ID}`);
  });

  it("POSTs /draft with from_version_id (restore) and invalidates the agent list + detail", async () => {
    const net = installFetch([
      { method: "GET", path: A, body: AGENT_DETAIL },
      { method: "GET", path: "/api/studio/agents", body: { items: [AGENT_SUMMARY] } },
      { method: "POST", path: `${A}/draft`, status: 201, body: DRAFT_DETAIL },
    ]);
    const { useCreateDraft } = await import("@/hooks/studio/useVersions");
    const { useStudioAgent, useStudioAgents } = await import("@/hooks/studio/useStudioAgents");
    const qc = newClient();
    renderHook(() => useStudioAgent("estrategista"), { wrapper: wrap(qc) });
    renderHook(() => useStudioAgents(), { wrapper: wrap(qc) });
    await waitFor(() => expect(net.calls.filter((c) => c.method === "GET")).toHaveLength(2));

    const { result } = renderHook(() => useCreateDraft("estrategista"), { wrapper: wrap(qc) });
    await act(() => result.current.mutateAsync({ from_version_id: V1_ID }));
    expect(net.calls.find((c) => c.method === "POST")).toMatchObject({ path: `${A}/draft`, body: { from_version_id: V1_ID } });
    await waitFor(() => expect(net.calls.filter((c) => c.method === "GET")).toHaveLength(4));
    // The response seeds the version cache — no extra GET for it.
    expect(qc.getQueryData(["studio", "estrategista", "version", V2_ID])).toEqual(DRAFT_DETAIL);
  });

  it("DELETEs /draft (204) and drops the draft's cached version", async () => {
    const net = installFetch([{ method: "DELETE", path: `${A}/draft`, status: 204 }]);
    const { useDiscardDraft } = await import("@/hooks/studio/useVersions");
    const qc = newClient();
    qc.setQueryData(["studio", "estrategista", "version", V2_ID], DRAFT_DETAIL);
    const { result } = renderHook(() => useDiscardDraft("estrategista"), { wrapper: wrap(qc) });
    await act(() => result.current.mutateAsync({ draftId: V2_ID }));
    expect(net.calls[0]).toMatchObject({ method: "DELETE", path: `${A}/draft` });
    expect(qc.getQueryData(["studio", "estrategista", "version", V2_ID])).toBeUndefined();
  });

  it("PATCHes /draft settings with only the given fields", async () => {
    const net = installFetch([{ method: "PATCH", path: `${A}/draft`, body: { ...DRAFT_DETAIL, max_turns: 60 } }]);
    const { useUpdateDraft } = await import("@/hooks/studio/useVersions");
    const { result } = renderHook(() => useUpdateDraft("estrategista"), { wrapper: wrap(newClient()) });
    await act(() => result.current.mutateAsync({ max_turns: 60, tool_policy: { web_search: false, knowledge: true } }));
    expect(net.calls[0].body).toEqual({ max_turns: 60, tool_policy: { web_search: false, knowledge: true } });
  });

  it("PUTs the full section list and refetches this agent's compiled views", async () => {
    const secoes = DRAFT_DETAIL.secoes.map(({ id, chave, titulo, ordem, conteudo, ativo }) => ({ id, chave, titulo, ordem, conteudo, ativo }));
    const net = installFetch([
      { method: "GET", path: `${A}/versions/${V2_ID}/compiled`, body: COMPILED_DRAFT },
      { method: "PUT", path: `${A}/draft/sections`, body: DRAFT_DETAIL },
      { method: "GET", path: A, body: AGENT_DETAIL },
    ]);
    const { useSaveSections } = await import("@/hooks/studio/useVersions");
    const { useCompiled } = await import("@/hooks/studio/useCompiled");
    const qc = newClient();
    const compiled = renderHook(() => useCompiled("estrategista", V2_ID), { wrapper: wrap(qc) });
    await waitFor(() => expect(compiled.result.current.data).toBeDefined());

    const { result } = renderHook(() => useSaveSections("estrategista"), { wrapper: wrap(qc) });
    await act(() => result.current.mutateAsync({ secoes }));
    expect(net.calls.find((c) => c.method === "PUT")).toMatchObject({ path: `${A}/draft/sections`, body: { secoes } });
    await waitFor(() => expect(net.calls.filter((c) => c.path.endsWith("/compiled"))).toHaveLength(2));
    // Mid-refetch the compiled data stays rendered: refreshing, not skeleton.
    expect(compiled.result.current.showSkeleton).toBe(false);
  });

  it("POSTs publish with override_reason and exposes the flat 409 eval_required body", async () => {
    const gateBody = {
      detail: "Publicação exige avaliação aprovada no hash atual.",
      code: "eval_required",
      hash_atual: COMPILED_DRAFT.hash,
      ultima_execucao: { id: "r1", score: 0.5, limiar: 0.8, compiled_hash: "sha256:" + "0".repeat(64) },
    };
    const net = installFetch([{ method: "POST", path: `${A}/draft/publish`, status: 409, body: gateBody }]);
    const { usePublishDraft } = await import("@/hooks/studio/useVersions");
    const { result } = renderHook(() => usePublishDraft("estrategista"), { wrapper: wrap(newClient()) });
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({ notas: "v2", override_reason: "Cliente aprovou manualmente o texto." });
      } catch (e) {
        caught = e;
      }
    });
    expect(net.calls[0]).toMatchObject({
      method: "POST",
      path: `${A}/draft/publish`,
      body: { notas: "v2", override_reason: "Cliente aprovou manualmente o texto." },
    });
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("eval_required");
    expect((caught as ApiError).body).toMatchObject({ hash_atual: COMPILED_DRAFT.hash, ultima_execucao: { score: 0.5 } });
  });

  it("GETs the diff between two versions", async () => {
    const net = installFetch([{ method: "GET", path: `${A}/versions/${V1_ID}/diff/${V2_ID}`, body: DIFF_V1_V2 }]);
    const { useVersionDiff } = await import("@/hooks/studio/useVersions");
    const { result } = renderHook(() => useVersionDiff("estrategista", V1_ID, V2_ID), { wrapper: wrap(newClient()) });
    await waitFor(() => expect(result.current.data?.secoes).toHaveLength(2));
    expect(net.calls[0].path).toBe(`${A}/versions/${V1_ID}/diff/${V2_ID}`);
  });

  it("does not request a diff of a version with itself", async () => {
    const net = installFetch([]);
    const { useVersionDiff } = await import("@/hooks/studio/useVersions");
    const { result } = renderHook(() => useVersionDiff("estrategista", V1_ID, V1_ID), { wrapper: wrap(newClient()) });
    expect(result.current.data).toBeUndefined();
    expect(net.calls).toHaveLength(0);
  });
});

describe("useVersions — skills + files", () => {
  const routes = [
    { method: "POST" as const, path: `${A}/draft/skills`, status: 201, body: DRAFT_DETAIL.skills[0] },
    { method: "PATCH" as const, path: `${A}/draft/skills/${SKILL_ID}`, body: DRAFT_DETAIL.skills[0] },
    { method: "DELETE" as const, path: `${A}/draft/skills/${SKILL_ID}`, status: 204 },
    {
      method: "PUT" as const,
      path: `${A}/draft/skills/${SKILL_ID}/files`,
      body: { id: FILE_ID, caminho: "references/arquiteturas.md", titulo: null, chars: 5 },
    },
    {
      method: "GET" as const,
      path: `${A}/skills/${SKILL_ID}/files/${FILE_ID}`,
      body: { id: FILE_ID, caminho: "references/arquiteturas.md", titulo: "Arquiteturas", conteudo: "texto" },
    },
    { method: "DELETE" as const, path: `${A}/draft/skills/${SKILL_ID}/files/${FILE_ID}`, status: 204 },
  ];

  it("hits the §D1 skill and file routes with the contract bodies", async () => {
    const net = installFetch(routes);
    const mod = await import("@/hooks/studio/useVersions");
    const qc = newClient();
    const w = wrap(qc);
    const create = renderHook(() => mod.useCreateSkill("estrategista", V2_ID), { wrapper: w });
    const update = renderHook(() => mod.useUpdateSkill("estrategista", V2_ID), { wrapper: w });
    const del = renderHook(() => mod.useDeleteSkill("estrategista", V2_ID), { wrapper: w });
    const upsert = renderHook(() => mod.useUpsertSkillFile("estrategista", V2_ID), { wrapper: w });
    const delFile = renderHook(() => mod.useDeleteSkillFile("estrategista", V2_ID), { wrapper: w });
    const file = renderHook(() => mod.useSkillFile("estrategista", SKILL_ID, FILE_ID), { wrapper: w });

    await act(() => create.result.current.mutateAsync({ nome: "roteiro-reels", descricao: "d", corpo: "c", ordem: 10, ativo: true }));
    await act(() => update.result.current.mutateAsync({ skillId: SKILL_ID, patch: { descricao: "nova" } }));
    await act(() =>
      upsert.result.current.mutateAsync({ skillId: SKILL_ID, file: { caminho: "references/arquiteturas.md", titulo: null, conteudo: "texto" } }),
    );
    await waitFor(() => expect(file.result.current.data?.conteudo).toBe("texto"));
    await act(() => delFile.result.current.mutateAsync({ skillId: SKILL_ID, fileId: FILE_ID }));
    await act(() => del.result.current.mutateAsync({ skillId: SKILL_ID }));

    const writes = net.calls.filter((c) => c.method !== "GET").map((c) => [c.method, c.path, c.body]);
    expect(writes).toEqual([
      ["POST", `${A}/draft/skills`, { nome: "roteiro-reels", descricao: "d", corpo: "c", ordem: 10, ativo: true }],
      ["PATCH", `${A}/draft/skills/${SKILL_ID}`, { descricao: "nova" }],
      ["PUT", `${A}/draft/skills/${SKILL_ID}/files`, { caminho: "references/arquiteturas.md", titulo: null, conteudo: "texto" }],
      ["DELETE", `${A}/draft/skills/${SKILL_ID}/files/${FILE_ID}`, undefined],
      ["DELETE", `${A}/draft/skills/${SKILL_ID}`, undefined],
    ]);
    // The draft version / agent detail are invalidated but have no observer
    // here, so the only GETs are the observed file's — and all were routed.
    expect(net.unmatched).toEqual([]);
  });
});

describe("useVersions — skill files batch upload (CONTRACT.md §G item 2)", () => {
  it("PUTs {arquivos} to the files/batch route, one call per mutateAsync", async () => {
    const response = {
      resultados: [
        { caminho: "references/a.md", status: "criado", id: "f-a" },
        { caminho: "references/b.md", status: "atualizado", id: "f-b" },
      ],
      criados: 1,
      atualizados: 1,
      erros: 0,
    };
    const net = installFetch([{ method: "PUT" as const, path: `${A}/draft/skills/${SKILL_ID}/files/batch`, body: response }]);
    const { useBatchUpsertSkillFiles } = await import("@/hooks/studio/useVersions");
    const qc = newClient();
    const batch = renderHook(() => useBatchUpsertSkillFiles("estrategista", V2_ID), { wrapper: wrap(qc) });

    const arquivos = [
      { caminho: "references/a.md", titulo: "A", conteudo: "conteúdo a" },
      { caminho: "references/b.md", titulo: "B", conteudo: "conteúdo b" },
    ];
    const result = await act(() => batch.result.current.mutateAsync({ skillId: SKILL_ID, arquivos }));

    expect(net.calls.map((c) => [c.method, c.path, c.body])).toEqual([["PUT", `${A}/draft/skills/${SKILL_ID}/files/batch`, { arquivos }]]);
    expect(result).toEqual(response);
  });

  it("surfaces a whole-call failure (e.g. 409 version_immutable) as a rejection, not a partial response", async () => {
    const net = installFetch([
      {
        method: "PUT" as const,
        path: `${A}/draft/skills/${SKILL_ID}/files/batch`,
        status: 409,
        body: { detail: "A versão não é mais um rascunho.", code: "version_immutable" },
      },
    ]);
    const { useBatchUpsertSkillFiles } = await import("@/hooks/studio/useVersions");
    const qc = newClient();
    const batch = renderHook(() => useBatchUpsertSkillFiles("estrategista", V2_ID), { wrapper: wrap(qc) });

    await expect(
      act(() =>
        batch.result.current.mutateAsync({ skillId: SKILL_ID, arquivos: [{ caminho: "references/a.md", conteudo: "x" }] }),
      ),
    ).rejects.toMatchObject({ status: 409 });
    expect(net.unmatched).toEqual([]);
  });
});

describe("useCompiled / usePromptByHash", () => {
  it("GETs /compiled without client_id when no client is selected", async () => {
    const net = installFetch([{ method: "GET", path: `${A}/versions/${V2_ID}/compiled`, body: COMPILED_DRAFT }]);
    const { useCompiled } = await import("@/hooks/studio/useCompiled");
    const { result } = renderHook(() => useCompiled("estrategista", V2_ID, null), { wrapper: wrap(newClient()) });
    await waitFor(() => expect(result.current.data?.hash).toBe(COMPILED_DRAFT.hash));
    expect(net.calls[0].search.has("client_id")).toBe(false);
  });

  it("passes client_id and keeps the previous compile visible while the client changes", async () => {
    const net = installFetch([{ method: "GET", path: `${A}/versions/${V2_ID}/compiled`, body: COMPILED_WITH_CLIENT }]);
    const { useCompiled } = await import("@/hooks/studio/useCompiled");
    const qc = newClient();
    qc.setQueryData(["studio", "estrategista", "compiled", V2_ID, "__sem_cliente__"], COMPILED_DRAFT);
    const { result, rerender } = renderHook(({ c }: { c: string | null }) => useCompiled("estrategista", V2_ID, c), {
      wrapper: wrap(qc),
      initialProps: { c: null as string | null },
    });
    expect(result.current.data?.client_id).toBeNull();
    rerender({ c: CLIENT_ID });
    // placeholderData: the old compile stays on screen, flagged as placeholder, no skeleton.
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data).toBeDefined();
    await waitFor(() => expect(result.current.data?.client_id).toBe(CLIENT_ID));
    expect(net.calls[net.calls.length - 1]?.search.get("client_id")).toBe(CLIENT_ID);
  });

  it("GETs /api/studio/prompts/{hash} with the hash path-encoded", async () => {
    const encoded = `/api/studio/prompts/${encodeURIComponent(STORED_PROMPT.hash)}`;
    const net = installFetch([{ method: "GET", path: encoded, body: STORED_PROMPT }]);
    const { usePromptByHash } = await import("@/hooks/studio/useCompiled");
    const { result } = renderHook(() => usePromptByHash(STORED_PROMPT.hash), { wrapper: wrap(newClient()) });
    await waitFor(() => expect(result.current.data?.texto).toBe(STORED_PROMPT.texto));
    expect(net.calls[0].path).toBe(encoded);
    expect(TEST_BASE_URL).toMatch(/^http/);
  });
});

describe("useClients (§D2)", () => {
  it("lists, reads, creates and edits entries on the §D2 routes", async () => {
    const C = `${A}/clients`;
    const net = installFetch([
      { method: "GET", path: C, body: { items: [CLIENT_SUMMARY] } },
      { method: "GET", path: `${C}/${CLIENT_ID}`, body: CLIENT },
      { method: "POST", path: C, status: 201, body: CLIENT },
      { method: "PATCH", path: `${C}/${CLIENT_ID}`, body: CLIENT },
      { method: "POST", path: `${C}/${CLIENT_ID}/entries`, status: 201, body: CLIENT.entradas[0] },
      { method: "PATCH", path: `${C}/${CLIENT_ID}/entries/${ENTRY_ID}`, body: CLIENT.entradas[0] },
      { method: "DELETE", path: `${C}/${CLIENT_ID}/entries/${ENTRY_ID}`, status: 204 },
    ]);
    const mod = await import("@/hooks/studio/useClients");
    const w = wrap(newClient());
    const list = renderHook(() => mod.useClients("estrategista"), { wrapper: w });
    const one = renderHook(() => mod.useClient("estrategista", CLIENT_ID), { wrapper: w });
    await waitFor(() => expect(list.result.current.data?.[0].total_entradas).toBe(1));
    await waitFor(() => expect(one.result.current.data?.entradas).toHaveLength(1));

    const create = renderHook(() => mod.useCreateClient("estrategista"), { wrapper: w });
    const update = renderHook(() => mod.useUpdateClient("estrategista"), { wrapper: w });
    const addEntry = renderHook(() => mod.useCreateClientEntry("estrategista"), { wrapper: w });
    const editEntry = renderHook(() => mod.useUpdateClientEntry("estrategista"), { wrapper: w });
    const delEntry = renderHook(() => mod.useDeleteClientEntry("estrategista"), { wrapper: w });
    await act(() => create.result.current.mutateAsync({ slug: "cliente-exemplo", nome: "Cliente Exemplo" }));
    await act(() => update.result.current.mutateAsync({ clientId: CLIENT_ID, patch: { resumo: "novo" } }));
    await act(() => addEntry.result.current.mutateAsync({ clientId: CLIENT_ID, entry: { tipo: "trava", titulo: "Não usar gírias" } }));
    await act(() => editEntry.result.current.mutateAsync({ clientId: CLIENT_ID, entryId: ENTRY_ID, patch: { status: "arquivado" } }));
    await act(() => delEntry.result.current.mutateAsync({ clientId: CLIENT_ID, entryId: ENTRY_ID }));

    const writes = net.calls.filter((c) => c.method !== "GET").map((c) => [c.method, c.path, c.body]);
    expect(writes).toEqual([
      ["POST", C, { slug: "cliente-exemplo", nome: "Cliente Exemplo" }],
      ["PATCH", `${C}/${CLIENT_ID}`, { resumo: "novo" }],
      ["POST", `${C}/${CLIENT_ID}/entries`, { tipo: "trava", titulo: "Não usar gírias" }],
      ["PATCH", `${C}/${CLIENT_ID}/entries/${ENTRY_ID}`, { status: "arquivado" }],
      ["DELETE", `${C}/${CLIENT_ID}/entries/${ENTRY_ID}`, undefined],
    ]);
    // Entry writes refetch the observed client detail.
    await waitFor(() => expect(net.calls.filter((c) => c.method === "GET" && c.path === `${C}/${CLIENT_ID}`).length).toBeGreaterThan(1));
    expect(net.unmatched).toEqual([]);
  });
});
