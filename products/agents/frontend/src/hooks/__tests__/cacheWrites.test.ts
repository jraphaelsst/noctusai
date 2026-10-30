/**
 * Cache-write contract for every agents mutation (`KB § PATTERNS/frontend/mutation-cache-writes.md`).
 *
 * Each test holds the request IN FLIGHT (deferred promise) or answers it while the settle refetch
 * never does, so the only thing that can explain the cache is the write itself: optimistic on the
 * click, or the server's answer committed on arrival. The old invalidate-only hooks fail all of these.
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: mockPut, patch: mockPatch, delete: mockDelete },
}));

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const w = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
}

/** A promise the test resolves by hand. */
function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => (resolve = res));
  return { promise, resolve };
}

// The first dynamic import transforms the whole studio + seed-lib graph (cold: well past the 15 s test timeout).
beforeAll(async () => {
  await Promise.all([
    import("@/hooks/useApprovals"),
    import("@/hooks/useLegacyChat"),
    import("@/hooks/useChannel"),
    import("@/hooks/studio/useVersions"),
  ]);
}, 120_000);

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockReturnValue(new Promise(() => {})); // a refetch must never be what fixes the screen
});

describe("approvals", () => {
  const A = { id: "ap1" }, B = { id: "ap2" };

  it("a decided approval leaves the pending list on the click", async () => {
    const { qc, w } = setup();
    const { APPROVALS_KEY, useDecideApproval } = await import("@/hooks/useApprovals");
    qc.setQueryData(APPROVALS_KEY, { items: [A, B], total: 2 });
    mockPost.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDecideApproval(), { wrapper: w });
    void result.current.decide("ap1", true);
    await waitFor(() => expect(qc.getQueryData(APPROVALS_KEY)).toEqual({ items: [B], total: 1 }));
  });

  it("a failed decision brings the card back", async () => {
    const { qc, w } = setup();
    const { APPROVALS_KEY, useDecideApproval } = await import("@/hooks/useApprovals");
    qc.setQueryData(APPROVALS_KEY, { items: [A, B], total: 2 });
    mockPost.mockRejectedValue(new Error("409"));
    const { result } = renderHook(() => useDecideApproval(), { wrapper: w });
    await expect(result.current.decide("ap1", true)).rejects.toThrow();
    await waitFor(() => expect(qc.getQueryData(APPROVALS_KEY)).toEqual({ items: [A, B], total: 2 }));
  });

  it("the chat approval seam removes the card on the click too", async () => {
    const { qc, w } = setup();
    const { APPROVALS_KEY } = await import("@/hooks/useApprovals");
    const { useApprovalDecisionAdapter } = await import("@/hooks/useApprovals");
    qc.setQueryData(APPROVALS_KEY, { items: [A, B], total: 2 });
    mockPost.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useApprovalDecisionAdapter(), { wrapper: w });
    void result.current.decide("ap2", false);
    await waitFor(() => expect(qc.getQueryData(APPROVALS_KEY)).toEqual({ items: [A], total: 1 }));
  });
});

describe("chat conversations", () => {
  it("a new conversation is in the list from the POST answer", async () => {
    const { qc, w } = setup();
    const { useCreateConversation } = await import("@/hooks/useLegacyChat");
    const key = ["agents", "bia", "conversations"];
    qc.setQueryData(key, { items: [{ id: "c1" }], total: 1 });
    const d = deferred();
    mockPost.mockReturnValue(d.promise);
    const { result } = renderHook(() => useCreateConversation(), { wrapper: w });
    result.current.mutate({ titulo: "Oi" });
    expect(qc.getQueryData<{ items: unknown[] }>(key)?.items).toHaveLength(1); // nothing invented
    d.resolve({ id: "c2", titulo: "Oi" });
    await waitFor(() => expect(qc.getQueryData<{ items: { id: string }[] }>(key)?.items.map((c) => c.id)).toEqual(["c2", "c1"]));
  });
});

describe("channel tokens", () => {
  const key = ["agents", "channel", "tokens"];

  it("a minted token's row is cached WITHOUT the secret", async () => {
    const { qc, w } = setup();
    const { useMintChannelToken } = await import("@/hooks/useChannel");
    qc.setQueryData(key, []);
    mockPost.mockResolvedValue({ id: "t1", token: "pk_SECRET", prefix: "pk_abc", expires_at: "x", scopes: ["a"] });
    const { result } = renderHook(() => useMintChannelToken("julia"), { wrapper: w });
    result.current.mutate({ label: "site" });
    await waitFor(() => expect(qc.getQueryData<unknown[]>(key)).toHaveLength(1));
    expect(JSON.stringify(qc.getQueryData(key))).not.toContain("pk_SECRET");
  });

  it("a revoked token is marked revoked on the click", async () => {
    const { qc, w } = setup();
    const { useRevokeChannelToken } = await import("@/hooks/useChannel");
    qc.setQueryData(key, [{ id: "t1", revoked_at: null }]);
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRevokeChannelToken("julia"), { wrapper: w });
    result.current.mutate("t1");
    await waitFor(() =>
      expect(qc.getQueryData<{ revoked_at: string | null }[]>(key)?.[0].revoked_at).not.toBeNull(),
    );
  });
});

describe("studio — biblioteca / content tokens / conformidade", () => {
  it("pinning a library skill commits the draft's pin list from the PUT answer", async () => {
    const { qc, w } = setup();
    const { useFixarSkill } = await import("@/hooks/studio/useBiblioteca");
    const key = ["studio", "julia", "biblioteca-refs", "v1"];
    qc.setQueryData(key, { version_id: "v1", items: [] });
    const saved = { version_id: "v1", items: [{ chave: "s1", nova_versao: true }] };
    mockPut.mockResolvedValue(saved);
    const { result } = renderHook(() => useFixarSkill("julia"), { wrapper: w });
    result.current.mutate({ skill: "s1", ref: { obrigatoria_para: [], ordem: 1 } });
    await waitFor(() => expect(qc.getQueryData(key)).toEqual(saved));
  });

  it("a minted content token shows in the list without its secret; a revoked one flips on the click", async () => {
    const { qc, w } = setup();
    const { useMintContentToken, useRevokeContentToken } = await import("@/hooks/studio/useContentToken");
    const key = ["studio", "__plataforma__", "content-tokens"];
    qc.setQueryData(key, { itens: [] });
    mockPost.mockResolvedValue({ id: "k1", token: "pk_SECRET", prefix: "pk_x", expires_at: null, scopes: ["studio:content-write"] });
    const mint = renderHook(() => useMintContentToken(), { wrapper: w });
    mint.result.current.mutate({ label: "robô", expira_em_dias: null });
    await waitFor(() => expect(qc.getQueryData<{ itens: unknown[] }>(key)?.itens).toHaveLength(1));
    expect(JSON.stringify(qc.getQueryData(key))).not.toContain("pk_SECRET");

    mockDelete.mockReturnValue(new Promise(() => {}));
    const revoke = renderHook(() => useRevokeContentToken(), { wrapper: w });
    revoke.result.current.mutate("k1");
    await waitFor(() =>
      expect(qc.getQueryData<{ itens: { status: string }[] }>(key)?.itens[0].status).toBe("revogado"),
    );
  });

  it("toggling a conformance rule is drawn while the PUT is in flight", async () => {
    const { qc, w } = setup();
    const { useDefinirRegra } = await import("@/hooks/studio/useConformidade");
    const key = ["studio", "julia", "conformidade", "regras"];
    qc.setQueryData(key, { items: [{ regra: "r1", ativo: false, politica: "registrar", mensagem_correcao_texto_chave: null }] });
    mockPut.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDefinirRegra("julia"), { wrapper: w });
    result.current.mutate({ regra: "r1", ativo: true });
    await waitFor(() =>
      expect(qc.getQueryData<{ items: { ativo: boolean }[] }>(key)?.items[0].ativo).toBe(true),
    );
  });
});

describe("studio — content set / org specs / platform texts", () => {
  it("saving a draft set commits the server's set into that version's read", async () => {
    const { qc, w } = setup();
    const { useSaveDraftSet } = await import("@/hooks/studio/useConteudo");
    const key = ["studio", "julia", "conteudo", "textos", "v1"];
    qc.setQueryData(key, { version_id: "v1", itens: [] });
    mockGet.mockResolvedValueOnce({ version_id: "v1", itens: [] }); // the compare-before-write read
    mockGet.mockReturnValue(new Promise(() => {}));
    const saved = { version_id: "v1", itens: [{ id: "t1", chave: "a", texto: "x" }] };
    mockPut.mockResolvedValue(saved);
    const { result } = renderHook(() => useSaveDraftSet("julia", "textos", "v1"), { wrapper: w });
    result.current.mutate({ itens: [], baseSnapshot: "[]" });
    await waitFor(() => expect(qc.getQueryData(key)).toEqual(saved));
  });

  it("org specs and platform texts are committed from the PUT answers", async () => {
    const { qc, w } = setup();
    const { useUpdateOrgSpecs, useSetPlataformaTextos } = await import("@/hooks/studio/useConteudo");
    qc.setQueryData(["studio", "julia", "org-specs"], { valores: [] });
    mockPut.mockResolvedValueOnce({ valores: [{ chave: "a", valor: "1" }] });
    const specs = renderHook(() => useUpdateOrgSpecs("julia"), { wrapper: w });
    specs.result.current.mutate({ valores: { a: "1" } });
    await waitFor(() =>
      expect(qc.getQueryData(["studio", "julia", "org-specs"])).toEqual({ valores: [{ chave: "a", valor: "1" }] }),
    );

    qc.setQueryData(["studio", "__plataforma__", "textos"], { itens: [] });
    mockPut.mockResolvedValueOnce({ itens: [{ chave: "t", texto: "oi" }] });
    const textos = renderHook(() => useSetPlataformaTextos(), { wrapper: w });
    textos.result.current.mutate({ itens: { t: "oi" } });
    await waitFor(() =>
      expect(qc.getQueryData(["studio", "__plataforma__", "textos"])).toEqual({ itens: [{ chave: "t", texto: "oi" }] }),
    );
  });
});

describe("studio — clients", () => {
  const key = ["studio", "julia", "clients", "c1"];
  const entry = { id: "e1", tipo: "nota", titulo: "T", conteudo: "x", status: "ativa", created_at: "t" };

  it("a new entry is in the client's detail from the POST answer; a deleted one leaves on the click", async () => {
    const { qc, w } = setup();
    const { useCreateClientEntry, useDeleteClientEntry } = await import("@/hooks/studio/useClients");
    qc.setQueryData(key, { id: "c1", entradas: [] });
    mockPost.mockResolvedValue(entry);
    const create = renderHook(() => useCreateClientEntry("julia"), { wrapper: w });
    create.result.current.mutate({ clientId: "c1", entry: { tipo: "nota", titulo: "T" } as never });
    await waitFor(() => expect(qc.getQueryData<{ entradas: unknown[] }>(key)?.entradas).toEqual([entry]));

    mockDelete.mockReturnValue(new Promise(() => {}));
    const del = renderHook(() => useDeleteClientEntry("julia"), { wrapper: w });
    del.result.current.mutate({ clientId: "c1", entryId: "e1" });
    await waitFor(() => expect(qc.getQueryData<{ entradas: unknown[] }>(key)?.entradas).toEqual([]));
  });

  it("an edited entry is drawn while the PATCH is in flight", async () => {
    const { qc, w } = setup();
    const { useUpdateClientEntry } = await import("@/hooks/studio/useClients");
    qc.setQueryData(key, { id: "c1", entradas: [entry] });
    mockPatch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useUpdateClientEntry("julia"), { wrapper: w });
    result.current.mutate({ clientId: "c1", entryId: "e1", patch: { titulo: "Novo" } });
    await waitFor(() =>
      expect(qc.getQueryData<{ entradas: { titulo: string }[] }>(key)?.entradas[0].titulo).toBe("Novo"),
    );
  });
});

describe("studio — evals / knowledge", () => {
  const evalCase = { id: "e1", slug: "s", titulo: "T" };

  it("eval cases: create commits, update is drawn, delete leaves on the click", async () => {
    const { qc, w } = setup();
    const { useCreateEvalCase, useUpdateEvalCase, useDeleteEvalCase } = await import("@/hooks/studio/useEvals");
    const key = ["studio", "julia", "evals", "cases"];
    qc.setQueryData(key, { items: [] });
    mockPost.mockResolvedValue(evalCase);
    const create = renderHook(() => useCreateEvalCase("julia"), { wrapper: w });
    create.result.current.mutate({ slug: "s", titulo: "T" } as never);
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [evalCase] }));

    mockPatch.mockReturnValue(new Promise(() => {}));
    const update = renderHook(() => useUpdateEvalCase("julia"), { wrapper: w });
    update.result.current.mutate({ caseId: "e1", patch: { titulo: "Novo" } });
    await waitFor(() =>
      expect(qc.getQueryData<{ items: { titulo: string }[] }>(key)?.items[0].titulo).toBe("Novo"),
    );

    mockDelete.mockReturnValue(new Promise(() => {}));
    const del = renderHook(() => useDeleteEvalCase("julia"), { wrapper: w });
    del.result.current.mutate("e1");
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [] }));
  });

  it("a created / edited knowledge collection is committed into the collections list", async () => {
    const { qc, w } = setup();
    const { useCreateKnowledgeCollection, useUpdateKnowledgeCollection } = await import("@/hooks/studio/useKnowledge");
    const key = ["studio", "julia", "knowledge", "collections"];
    qc.setQueryData(key, { colecoes: [] });
    const col = { id: "k1", slug: "a", nome: "A", tag: null, descricao: "", ordem: 1, total_documentos: 0 };
    mockPost.mockResolvedValue(col);
    const create = renderHook(() => useCreateKnowledgeCollection("julia"), { wrapper: w });
    create.result.current.mutate({ slug: "a", nome: "A" });
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ colecoes: [col] }));

    mockPatch.mockResolvedValue({ ...col, nome: "B" });
    const update = renderHook(() => useUpdateKnowledgeCollection("julia"), { wrapper: w });
    update.result.current.mutate({ collectionId: "k1", patch: { nome: "B" } });
    await waitFor(() =>
      expect(qc.getQueryData<{ colecoes: { nome: string }[] }>(key)?.colecoes[0].nome).toBe("B"),
    );
  });
});

describe("studio — versions, skills, qualification standard", () => {
  const skill = { id: "s1", nome: "n", descricao: "", corpo: "", ordem: 1, ativo: true, arquivos: [] };
  const draftKey = ["studio", "julia", "version", "d1"];

  it("skills are committed into the draft's version from the route answers", async () => {
    const { qc, w } = setup();
    const { useCreateSkill, useUpdateSkill, useDeleteSkill } = await import("@/hooks/studio/useVersions");
    qc.setQueryData(draftKey, { id: "d1", skills: [] });
    mockPost.mockResolvedValue(skill);
    const create = renderHook(() => useCreateSkill("julia", "d1"), { wrapper: w });
    create.result.current.mutate({ nome: "n", descricao: "", corpo: "" });
    await waitFor(() => expect(qc.getQueryData<{ skills: unknown[] }>(draftKey)?.skills).toEqual([skill]));

    mockPatch.mockResolvedValue({ ...skill, nome: "novo" });
    const update = renderHook(() => useUpdateSkill("julia", "d1"), { wrapper: w });
    update.result.current.mutate({ skillId: "s1", patch: { nome: "novo" } });
    await waitFor(() => expect(qc.getQueryData<{ skills: { nome: string }[] }>(draftKey)?.skills[0].nome).toBe("novo"));

    mockDelete.mockResolvedValue(null);
    const del = renderHook(() => useDeleteSkill("julia", "d1"), { wrapper: w });
    del.result.current.mutate({ skillId: "s1" });
    await waitFor(() => expect(qc.getQueryData<{ skills: unknown[] }>(draftKey)?.skills).toEqual([]));
  });

  it("saving sections seeds the draft's version from the PUT answer", async () => {
    const { qc, w } = setup();
    const { useSaveSections } = await import("@/hooks/studio/useVersions");
    const saved = { id: "d1", secoes: [{ id: "x" }], skills: [] };
    mockPut.mockResolvedValue(saved);
    const { result } = renderHook(() => useSaveSections("julia"), { wrapper: w });
    result.current.mutate({ secoes: [] } as never);
    await waitFor(() => expect(qc.getQueryData(draftKey)).toEqual(saved));
  });

  it("a qualification-standard write commits the full version; a discarded draft leaves the list on the click", async () => {
    const { qc, w } = setup();
    const { useSalvarParametros, useDescartarRascunhoPadrao } = await import("@/hooks/studio/useQualificacao");
    const vkey = ["studio", "__qualificacao__", "versao", "q1"];
    const lkey = ["studio", "__qualificacao__", "p", "versoes"];
    qc.setQueryData(vkey, { id: "q1", parametros: {} });
    mockPut.mockResolvedValue({ id: "q1", parametros: { limiar: 7 } });
    const save = renderHook(() => useSalvarParametros("p", "q1"), { wrapper: w });
    save.result.current.mutate({ limiar: 7 } as never);
    await waitFor(() => expect(qc.getQueryData(vkey)).toEqual({ id: "q1", parametros: { limiar: 7 } }));

    qc.setQueryData(lkey, { items: [{ id: "q1" }, { id: "q0" }] });
    mockDelete.mockReturnValue(new Promise(() => {}));
    const del = renderHook(() => useDescartarRascunhoPadrao("p"), { wrapper: w });
    del.result.current.mutate({ versaoId: "q1" });
    await waitFor(() => expect(qc.getQueryData(lkey)).toEqual({ items: [{ id: "q0" }] }));
  });
});
