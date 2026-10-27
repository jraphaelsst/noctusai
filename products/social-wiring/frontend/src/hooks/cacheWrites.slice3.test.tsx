/**
 * Cache-write contract for the social-wiring hooks migrated off invalidate-only (wave 2, slice 3).
 *
 * Each case asserts what the CACHE holds while the request is still in flight (optimistic) or the
 * instant the server answers while the settle refetch has not run (commit) — the behaviour the old
 * `onSuccess: invalidateQueries` hooks could not have. KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider, type QueryKey } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  upload: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({
  api,
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
  useAuthStore: () => ({ user: { id: "u1" } }),
  getAuthToken: vi.fn(),
}));

import { useArquivarAtendimento } from "./useAtendimentos";
import { useCampanhaMutations } from "./useCampanhas";
import { useRenomearBrain, CEREBRO_KEY } from "./useCerebro";
import { useDeleteConsulta } from "./useCertidoes";
import { useRenomearLinhaMatriz } from "./useCertidoesMatriz";
import { useClassificarDocumento } from "./useConversaDocumentos";
import { cardFamilyKey } from "./useCardHub";
import { useUpdateFavorecidoRegistro } from "./useFavorecidosRegistro";
import { useAtualizarImovelManual } from "./useImovelManual";
import { useSalvarCreditoConfig } from "./useJuliaCredito";
import { EQUIPE_WHATSAPP_KEY, useRemoverMembro } from "./useJuliaEquipeWhatsapp";
import { MODELOS_KEY, useCriarModelo } from "./useJuliaModelos";
import { NOTAS_KEY, useNotaMutations } from "./useJuliaConversas";
import { SOLICITACOES_KEY, useDecidirSolicitacao } from "./useJuliaOptOuts";
import { JULIA_ROTEAMENTO_KEY, useAtualizarLinha } from "./useJuliaRoteamento";
import { useLeadSourceMutations } from "./useLeadsSources";
import { useMailchimpCampaignMutations } from "./useMailchimpCampaigns";
import { useMailchimpConnectionMutations } from "./useMailchimpConnection";
import { useMailchimpContactMutations } from "./useMailchimpContacts";
import { useAtualizarContratoParte } from "./usePartes";
import { useMoverEtapa } from "./usePermutas";
import { usePropostaMutations } from "./usePropostas";
import { ROTEIROS_PENDENTES_KEY, useResponderFeedbackRoteiro } from "./useRoteirosFeedback";
import { schedulingKeys, useResolvePendingChatIdentity } from "./useScheduling";
import { API_KEYS_QUERY_KEY, useSaveApiKey } from "./useSettings";
import { useToggleAutoReply } from "./useWhatsAppConnections";
import { ESTEIRA_KEY, ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
import { useExcluirMembro, useExcluirPost } from "./geracao/useEsteira";
import { GERACAO_KEY } from "@/lib/geracaoKeys";
import { useCriarLote } from "./geracao/useHeadlines";

function defer<T = unknown>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

/** A client seeded with `entries`; its settle refetch never finishes, so the cache is exactly what the hook wrote. */
function mount<T>(useHook: () => T, entries: [QueryKey, unknown][]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  for (const [key, value] of entries) qc.setQueryData(key, value);
  vi.spyOn(qc, "invalidateQueries").mockReturnValue(new Promise(() => {}));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(useHook, { wrapper });
  return { qc, result };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  for (const fn of Object.values(api)) fn.mockReset();
});

describe("optimistic: the change is drawn while the request is in flight", () => {
  it("esteira: excluir membro leaves the equipe list", async () => {
    const key = [...ESTEIRA_KEY, "equipe", false];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useExcluirMembro(), [[key, [{ id: "m1" }, { id: "m2" }]]]);
    act(() => result.current.mutate("m1"));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "m2" }]));
  });

  it("esteira: excluir post leaves its board column and the count follows", async () => {
    const key = [ESTEIRA_PIPELINE_KEY, {}];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useExcluirPost(), [
      [key, [{ etapa: "a", cards: [{ id: "p1" }, { id: "p2" }], total: 2 }]],
    ]);
    act(() => result.current.mutate("p1"));
    await waitFor(() =>
      expect(qc.getQueryData(key)).toEqual([{ etapa: "a", cards: [{ id: "p2" }], total: 1 }]),
    );
  });

  it("atendimentos: arquivar takes the card off the funil board", async () => {
    const key = ["sw-funil", {}];
    api.patch.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useArquivarAtendimento(), [
      [key, [{ cards: [{ id: "a1" }, { id: "a2" }], total: 2 }]],
    ]);
    act(() => result.current.mutate("a1"));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ cards: [{ id: "a2" }], total: 1 }]));
  });

  it("campanhas: remover", async () => {
    const key = ["sw", "campanhas", "lista"];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useCampanhaMutations(), [[key, [{ id: "c1" }, { id: "c2" }]]]);
    act(() => result.current.remover.mutate({ id: "c1" }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "c2" }]));
  });

  it("cerebro: renomear brain shows the new name in the marca's list", async () => {
    const key = [...CEREBRO_KEY, "m1", "brains"];
    api.patch.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useRenomearBrain(), [[key, [{ id: "b1", name: "a" }]]]);
    act(() => result.current.mutate({ id: "b1", name: "b" }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "b1", name: "b" }]));
  });

  it("certidões: excluir consulta leaves every cached filter of the list", async () => {
    const key = ["certidao-consultas", { busca: "x" }];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useDeleteConsulta(), [[key, [{ id: "q1" }, { id: "q2" }]]]);
    act(() => result.current.mutate("q1"));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "q2" }]));
  });

  it("matriz: renomear a linha customizada relabels it", async () => {
    const key = ["sw", "clientes", "c1", "certidoes", "matriz"];
    api.patch.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useRenomearLinhaMatriz("c1"), [
      [key, { linhas: [{ id: "l1", rotulo: "Outras: a" }], colunas: [] }],
    ]);
    act(() => result.current.mutate({ linhaId: "l1", nome: "b" }));
    await waitFor(() =>
      expect(qc.getQueryData(key)).toEqual({ linhas: [{ id: "l1", rotulo: "Outras: b" }], colunas: [] }),
    );
  });

  it("conversa: classificar documento leaves the triage list", async () => {
    const key = [...cardFamilyKey("c1"), "documentos-a-classificar"];
    api.post.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useClassificarDocumento("c1"), [
      [key, { items: [{ id: "d1" }, { id: "d2" }], total: 2 }],
    ]);
    act(() => result.current.mutate({ documentoId: "d1", tipo: "rg" }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [{ id: "d2" }], total: 1 }));
  });

  it("julia: remover membro da equipe", async () => {
    const key = [...EQUIPE_WHATSAPP_KEY, "lista"];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useRemoverMembro(), [
      [key, { items: [{ id: "a" }, { id: "b" }], papeis: [], operadores: [] }],
    ]);
    act(() => result.current.mutate({ id: "a" }));
    await waitFor(() =>
      expect(qc.getQueryData(key)).toEqual({ items: [{ id: "b" }], papeis: [], operadores: [] }),
    );
  });

  it("julia: decidir solicitação marks the status on the page", async () => {
    const key = [...SOLICITACOES_KEY, "", 1];
    api.patch.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useDecidirSolicitacao(), [
      [key, { items: [{ id: "s1", status: "aberta" }], total: 1 }],
    ]);
    act(() => result.current.mutate({ id: "s1", status: "atendida" }));
    await waitFor(() =>
      expect(qc.getQueryData(key)).toEqual({ items: [{ id: "s1", status: "atendida" }], total: 1 }),
    );
  });

  it("julia: roteamento — the line's switch flips at once", async () => {
    api.put.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useAtualizarLinha(), [
      [JULIA_ROTEAMENTO_KEY, { linhas: [{ connection_id: "c1", alimenta: false }], agents_url: null }],
    ]);
    act(() => result.current.mutate({ connectionId: "c1", body: { alimenta: true } }));
    await waitFor(() =>
      expect(qc.getQueryData(JULIA_ROTEAMENTO_KEY)).toEqual({
        linhas: [{ connection_id: "c1", alimenta: true }],
        agents_url: null,
      }),
    );
  });

  it("leads: remover origem", async () => {
    const key = ["leads", "sources"];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useLeadSourceMutations(), [[key, [{ id: "s1" }, { id: "s2" }]]]);
    act(() => result.current.remove.mutate({ id: "s1" }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "s2" }]));
  });

  it("mailchimp: remover campanha leaves the page and the total follows", async () => {
    const key = ["mailchimp", "campaigns", undefined];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useMailchimpCampaignMutations(), [
      [key, { items: [{ id: "1" }, { id: "2" }], total: 2 }],
    ]);
    act(() => result.current.remove.mutate("1"));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [{ id: "2" }], total: 1 }));
  });

  it("mailchimp: desconectar marks the connection as not connected", async () => {
    const key = ["mailchimp", "connection"];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useMailchimpConnectionMutations(), [
      [key, { connected: true, server_prefix: "us1", audience_id: "a", audience_name: "A" }],
    ]);
    act(() => result.current.remove.mutate());
    await waitFor(() =>
      expect(qc.getQueryData(key)).toEqual({
        connected: false,
        server_prefix: null,
        audience_id: null,
        audience_name: null,
      }),
    );
  });

  it("mailchimp: arquivar contato (rows keyed by email)", async () => {
    const key = ["mailchimp", "contacts", undefined];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useMailchimpContactMutations(), [
      [key, { items: [{ email: "a@x.com" }, { email: "b@x.com" }], total: 2 }],
    ]);
    act(() => result.current.archive.mutate("a@x.com"));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [{ email: "b@x.com" }], total: 1 }));
  });

  it("permutas: mover etapa shows the new stage on the match", async () => {
    const key = ["sw", "permutas", "matches", { etapa: null }];
    api.patch.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useMoverEtapa(), [[key, [{ id: "m1", etapa: "novo" }]]]);
    act(() => result.current.mutate({ matchId: "m1", etapa: "visita" as never }));
    // Any move off `rejeitado` clears the rejection reason server-side, so the
    // cache write nulls the three motivo fields too — a card must never keep
    // showing a reason for a match that is no longer rejected.
    await waitFor(() =>
      expect(qc.getQueryData(key)).toEqual([
        {
          id: "m1",
          etapa: "visita",
          motivo_rejeicao: null,
          motivo_rejeicao_detalhe: null,
          motivo_lado: null,
        },
      ]),
    );
  });

  it("propostas: excluir", async () => {
    const key = ["sw", "clientes", "c1", "propostas", "list"];
    api.delete.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => usePropostaMutations("c1"), [[key, [{ id: "p1" }, { id: "p2" }]]]);
    act(() => result.current.excluir.mutate({ id: "p1" }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "p2" }]));
  });

  it("whatsapp: auto-reply toggle flips on the line", async () => {
    const key = ["whatsapp", "connections"];
    api.put.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useToggleAutoReply(), [[key, [{ id: "l1", auto_reply_enabled: false }]]]);
    act(() => result.current.mutate({ id: "l1", enabled: true }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "l1", auto_reply_enabled: true }]));
  });

  it("roteiros: responder feedback takes the roteiro off the pendentes queue", async () => {
    api.post.mockReturnValue(defer().promise);
    const { qc, result } = mount(() => useResponderFeedbackRoteiro("c1"), [
      [ROTEIROS_PENDENTES_KEY, [{ roteiro_id: "r1" }, { roteiro_id: "r2" }]],
    ]);
    act(() => result.current.mutate({ roteiroId: "r1", body: {} as never }));
    await waitFor(() => expect(qc.getQueryData(ROTEIROS_PENDENTES_KEY)).toEqual([{ roteiro_id: "r2" }]));
  });
});

describe("commit: the server's answer is in the cache before the settle refetch", () => {
  it("headlines: a new lote is the first row of the marca's lotes", async () => {
    const key = [...GERACAO_KEY, "headlines", "m1", "lotes", "", 0];
    api.post.mockResolvedValue({ data: { id: "l1", status: "criando" } });
    const { qc, result } = mount(() => useCriarLote(), [[key, { items: [{ id: "l0" }], total: 1 }]]);
    act(() => result.current.mutate({ marca_id: "m1", origem: "form_me", variaveis: [], somente_pesquisa: false, criatividade: "media" } as never));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ items: [{ id: "l1", status: "criando" }, { id: "l0" }], total: 2 }));
  });

  it("favorecidos: update patches the non-sensitive fields of the masked row", async () => {
    const key = ["sw", "favorecidos", "list", "", "ativos"];
    api.patch.mockResolvedValue({ id: "f1", nome: "B", tipo_pessoa: "PF", banco: "X", pix_tipo: null, ativo: true, cpf_cnpj: "123" });
    const { qc, result } = mount(() => useUpdateFavorecidoRegistro(), [
      [key, { items: [{ id: "f1", nome: "A", cpf_cnpj_mascarado: "***", ativo: true }] }],
    ]);
    act(() => result.current.mutate({ id: "f1", patch: { nome: "B" } }));
    const row = () => (qc.getQueryData(key) as { items: Record<string, unknown>[] }).items[0];
    await waitFor(() => expect(row().nome).toBe("B"));
    expect(row().cpf_cnpj_mascarado).toBe("***");
    expect(row()).not.toHaveProperty("cpf_cnpj"); // clear PII never reaches the list cache
  });

  it("imóvel manual: atualizar lands in the catalog page (by código) and the detail", async () => {
    const page = ["sw", "imoveis", {}];
    const detail = ["sw", "imoveis", "detail", "A1"];
    api.patch.mockResolvedValue({ codigo: "A1", titulo: "novo" });
    const { qc, result } = mount(() => useAtualizarImovelManual("A1"), [
      [page, { items: [{ codigo: "A1", titulo: "velho" }], total: 1 }],
      [detail, { codigo: "A1", titulo: "velho" }],
    ]);
    act(() => result.current.mutate({ titulo: "novo" }));
    await waitFor(() =>
      expect((qc.getQueryData(page) as { items: { titulo: string }[] }).items[0].titulo).toBe("novo"),
    );
    expect((qc.getQueryData(detail) as { titulo: string }).titulo).toBe("novo");
  });

  it("julia crédito: salvar config", async () => {
    const key = ["julia", "credito", "config"];
    api.put.mockResolvedValue({ data: { ativo: true, provider: "x", apenas_aluguel: false } });
    const { qc, result } = mount(() => useSalvarCreditoConfig(), [[key, { ativo: false, provider: null, apenas_aluguel: false }]]);
    act(() => result.current.mutate({ ativo: true, provider: "x", apenas_aluguel: false }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual({ ativo: true, provider: "x", apenas_aluguel: false }));
  });

  it("julia modelos: criar", async () => {
    api.post.mockResolvedValue({ data: { id: "m1", nome: "N" } });
    const { qc, result } = mount(() => useCriarModelo(), [[MODELOS_KEY, []]]);
    act(() => result.current.mutate({ nome: "N", categoria: "Visita", conteudo: "x" }));
    await waitFor(() => expect(qc.getQueryData(MODELOS_KEY)).toEqual([{ id: "m1", nome: "N" }]));
  });

  it("julia notas: a new nota goes on top (the API lists newest first)", async () => {
    const key = [...NOTAS_KEY, "c1"];
    api.post.mockResolvedValue({ data: { id: "n1", texto: "novo" } });
    const { qc, result } = mount(() => useNotaMutations("c1"), [[key, [{ id: "n0", texto: "velho" }]]]);
    act(() => result.current.criar.mutate({ texto: "novo" }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "n1", texto: "novo" }, { id: "n0", texto: "velho" }]));
  });

  it("partes: o contrato da parte (NIRE) entra na linha da parte", async () => {
    const key = ["sw", "clientes", "c1", "partes", null];
    api.patch.mockResolvedValue({ id: "p1", pj_nire: "123" });
    const { qc, result } = mount(() => useAtualizarContratoParte("c1"), [
      [key, { items: [{ parte_id: "p1", pj_nire: null, pj_sede: null }], total: 1 }],
    ]);
    act(() => result.current.mutate({ parteId: "p1", patch: { pj_nire: "123" } }));
    await waitFor(() => expect((qc.getQueryData(key) as { items: { pj_nire: string }[] }).items[0].pj_nire).toBe("123"));
  });

  it("agendamentos de chat: resolver identidade pendente", async () => {
    const key = schedulingKeys.pendingIdentities();
    api.patch.mockResolvedValue({ id: "i1", status: "resolved" });
    const { qc, result } = mount(() => useResolvePendingChatIdentity(), [[key, [{ id: "i1", status: "pending" }]]]);
    act(() => result.current.mutate({ id: "i1", status: "resolved" as never }));
    await waitFor(() => expect(qc.getQueryData(key)).toEqual([{ id: "i1", status: "resolved" }]));
  });

  it("settings: salvar chave replaces the status row (keyed by key)", async () => {
    api.put.mockResolvedValue({ key: "k", label: "K", configured: true });
    const { qc, result } = mount(() => useSaveApiKey(), [
      [API_KEYS_QUERY_KEY, { items: [{ key: "k", label: "K", configured: false }], total: 1 }],
    ]);
    act(() => result.current.mutate({ key: "k", value: "v" }));
    await waitFor(() =>
      expect(qc.getQueryData(API_KEYS_QUERY_KEY)).toEqual({
        items: [{ key: "k", label: "K", configured: true }],
        total: 1,
      }),
    );
  });
});
