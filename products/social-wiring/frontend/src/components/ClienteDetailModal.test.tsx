/**
 * ClienteDetailModal.test.tsx — the description-vs-comentário branch the
 * coordinator asked to be verified explicitly: create (tipo: "descricao")
 * when the card has none yet, update-by-id when it does, the composer
 * always creates with tipo "comentario", and a rejected mutation (the
 * backend's 409 on a duplicate descricao, in particular) surfaces via a
 * toast with the server's own message rather than reading as a network
 * failure.
 *
 * `ClienteCardDialog` (the real presentational organ, already covered by
 * its own test file) is stubbed here to a thin control surface — this
 * file is about the CONTAINER's wiring, not the dialog's rendering.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError, warning: vi.fn() } }));

vi.mock("@/hooks/useLeadsCorretores", () => ({
  useLeadCorretores: () => ({ data: [] }),
}));

// Owner-directive card actions (Arquivar / Excluir) — sibling of the
// `useContratoMutations`/`useImoveisBusca` mocks below: reached even though
// `ClienteCardDialog` itself is stubbed, because `ClienteDetailModal` calls
// these hooks directly (not just through props the stub renders).
vi.mock("@/hooks/useAtendimentos", () => ({
  useArquivarAtendimento: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useClientes", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useClientes")>(
    "@/hooks/useClientes",
  );
  return {
    ...actual,
    useClienteMutations: () => ({
      update: { mutate: vi.fn(), isPending: false },
      remove: { mutate: vi.fn(), isPending: false },
    }),
  };
});

// `useAuthStore`/`resolveSSOContext` — the "is this caller an admin"
// UI-convenience gate for the Excluir icon. Mirrors
// `ConflitosPendentesPanel.test.tsx`'s exact mock shape (the SAME two
// modules gating the SAME kind of admin-only affordance). Non-admin by
// default (`user_metadata: {}`).
vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: { user_metadata: {} } }),
}));

vi.mock("@noctusai/lib", () => ({
  resolveSSOContext: (metadata: any) => {
    const m = metadata || {};
    return {
      isProductAdmin: m.org_role === "owner" || m.org_role === "admin",
      org: { role: m.org_role ?? "member" },
    };
  },
}));

const { mockCreate, mockUpdate, mockCardResumo, mockDocumentoChecklist } = vi.hoisted(() => ({
  mockCreate: { mutate: vi.fn(), isPending: false },
  mockUpdate: { mutate: vi.fn(), isPending: false },
  mockCardResumo: vi.fn(),
  mockDocumentoChecklist: vi.fn(() => ({
    data: { items: [], total: 0, concluidos: 0, valores: {} as Record<string, unknown> },
    isPending: false,
    isFetching: false,
  })),
}));

const documentosIds: (string | null)[] = [];
const extrasIds: (string | null)[] = [];
const agendamentosIds: (string | null)[] = [];
const roteirosIds: (string | null)[] = [];

vi.mock("@/hooks/useCardHub", () => ({
  useCardResumo: (id: string | null) => mockCardResumo(id),
  useTimeline: () => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  }),
  flattenTimeline: () => [],
  useTags: () => ({ data: [] }),
  useChecklists: () => ({ data: [], isPending: false, isFetching: false }),
  useDocumentos: (id: string | null) => {
    documentosIds.push(id);
    return { data: [], isPending: false, isFetching: false };
  },
  // Bug 2 (prod card 755253934) — the polling/invalidation side effect;
  // this suite covers routing/fetch-shape only, not the poll itself (see
  // `useCardHub.test.ts` for that).
  useExtracaoPollingInvalidation: () => {},
  useDocumentoChecklist: () => mockDocumentoChecklist(),
  useDocumentoChecklistMutation: () => ({ mutate: vi.fn(), isPending: false }),
  // Checklist extras — the operator-created rows the remodel added beside the
  // server-defined six. Records its id for the tab-scoping assertion below.
  useChecklistExtras: (id: string | null) => {
    extrasIds.push(id);
    return { data: [], isPending: false, isFetching: false, isError: false };
  },
  useChecklistExtraMutations: () => ({
    criar: { mutate: vi.fn(), isPending: false },
    atualizar: { mutate: vi.fn(), isPending: false },
    remover: { mutate: vi.fn(), isPending: false },
    uploadDocumento: { mutate: vi.fn(), isPending: false },
    removerDocumento: { mutate: vi.fn(), isPending: false },
  }),
  useExtracaoSugestaoMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useTiposDocumento: () => ({ data: [] }),
  useCompradores: () => ({
    data: { items: [], total: 0, atendimento_id: null },
    isPending: false,
    isFetching: false,
  }),
  useCompradorMutations: () => ({
    adicionar: { mutate: vi.fn(), isPending: false },
    remover: { mutate: vi.fn(), isPending: false },
    // `variables` is part of the contract this modal reads, not decoration:
    // it derives `papelSalvandoParteId` from it so ONE role select is
    // disabled while it saves, rather than every one on the card.
    atualizarPapel: { mutate: vi.fn(), isPending: false, variables: undefined },
  }),
  useDadosPessoaisMutation: () => ({ mutate: vi.fn(), isPending: false }),
  // Durable pending-state read (owner directive, 2026-09-19) —
  // `ClienteDetailModal`'s `renderConflitosPendentes` thunk + its
  // `dadosPessoaisPendente` prop both read this.
  useConflitosPendentes: () => ({ data: [] }),
  useNotaMutations: () => ({ create: mockCreate, update: mockUpdate, remove: { mutate: vi.fn() } }),
  useTagCatalogMutations: () => ({
    create: { mutate: vi.fn() },
    update: { mutate: vi.fn() },
    remove: { mutate: vi.fn() },
  }),
  useSetClienteTagsMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useSetCardMembrosMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useAgendamentos: (id: string | null) => {
    agendamentosIds.push(id);
    return { data: [], isPending: false, isFetching: false };
  },
  useAgendamentoMutations: () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  }),
  // Roteiros (migration 082). `useRoteiros` records its id for the same
  // tab-scoped-fetching assertion `useAgendamentos`/`useDocumentos` carry:
  // the tab must be `null` until it has been opened.
  useRoteiros: (id: string | null) => {
    roteirosIds.push(id);
    return { data: [], isPending: false, isFetching: false, isError: false };
  },
  useRoteiroMutations: () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
    reorder: { mutate: vi.fn(), isPending: false },
    patchVisita: { mutate: vi.fn(), isPending: false },
  }),
  baixarRoteiroPdf: vi.fn(),
  // Consumed by `CriarRoteiroDialog`, which this container renders as a
  // sibling of the card — so it is reached even though the card itself is
  // stubbed below.
  useImoveisBusca: () => ({
    data: { items: [] },
    isPending: false,
    isFetching: false,
    isError: false,
  }),
  useChecklistMutations: () => ({
    createChecklist: { mutate: vi.fn() },
    removeChecklist: { mutate: vi.fn() },
    addItem: { mutate: vi.fn() },
    toggleItem: { mutate: vi.fn() },
    removeItem: { mutate: vi.fn() },
  }),
  useDocumentoMutations: () => ({
    upload: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn() },
    getUrl: { mutate: vi.fn() },
    reextrair: { mutate: vi.fn(), isPending: false, variables: undefined },
  }),
}));

// `useContratoMutations` — only `create` is read here (`NovoContratoDialog`
// is a sibling reached even though the card itself is stubbed, same as
// `CriarRoteiroDialog`/`useImoveisBusca` above). `importActual` keeps every
// constant/label/validator `NovoContratoDialog` also imports from this
// module real, so only the hook itself is faked.
vi.mock("@/hooks/useContratos", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useContratos")>(
    "@/hooks/useContratos",
  );
  return {
    ...actual,
    useContratoMutations: () => ({
      create: { mutate: vi.fn(), isPending: false },
      addVersao: { mutate: vi.fn(), isPending: false },
      patch: { mutate: vi.fn(), isPending: false },
      deleteVersao: { mutate: vi.fn(), isPending: false },
      deleteContrato: { mutate: vi.fn(), isPending: false },
      getUrl: { mutate: vi.fn(), mutateAsync: vi.fn() },
    }),
  };
});

// Thin control surface over the real presentational dialog: exposes just
// the description save + comentário post affordances this file exercises.
vi.mock("@/components/card/ClienteCardDialog", async () => {
  const React = await import("react");
  return {
    ClienteCardDialog: (props: any) =>
      React.createElement(
        "div",
        null,
        React.createElement(
          "button",
          { "data-testid": "save-descricao", onClick: () => props.onSaveDescricao("nova descrição") },
          "save",
        ),
        React.createElement(
          "button",
          { "data-testid": "post-comentario", onClick: () => props.onPostComentario("um comentário") },
          "post",
        ),
        React.createElement("span", { "data-testid": "descricao-corpo" }, props.descricaoCorpo),
        React.createElement(
          "span",
          { "data-testid": "dados-pessoais-probe" },
          JSON.stringify(props.dadosPessoais ?? null),
        ),
      ),
  };
});

import { ClienteDetailModal } from "./ClienteDetailModal";

async function render() {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(
    React.createElement(ClienteDetailModal, { clienteId: "cl1", open: true, onClose: vi.fn() }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ClienteDetailModal — Descrição vs. Comentários (backend tipo discriminator)", () => {
  it("creates with tipo: descricao when the card has no description yet", async () => {
    mockCardResumo.mockReturnValue({
      data: {
        cliente: { nome: "Maria Silva" },
        tags: [],
        membros: [],
        descricao: null,
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("save-descricao"));

    expect(mockCreate.mutate).toHaveBeenCalledWith(
      { corpo: "nova descrição", tipo: "descricao" },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
    expect(mockUpdate.mutate).not.toHaveBeenCalled();
  });

  it("updates-by-id when the card already has a description", async () => {
    mockCardResumo.mockReturnValue({
      data: {
        cliente: { nome: "Maria Silva" },
        tags: [],
        membros: [],
        descricao: { id: "desc1", corpo: "descrição atual", editado_em: null },
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("save-descricao"));

    expect(mockUpdate.mutate).toHaveBeenCalledWith(
      { notaId: "desc1", corpo: "nova descrição" },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
    expect(mockCreate.mutate).not.toHaveBeenCalled();
  });

  it("renders CardResumo.descricao.corpo, never a value derived from the timeline", async () => {
    mockCardResumo.mockReturnValue({
      data: {
        cliente: { nome: "Maria Silva" },
        tags: [],
        membros: [],
        descricao: { id: "desc1", corpo: "a descrição real", editado_em: null },
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await render();
    expect(getByTestId("descricao-corpo").textContent).toBe("a descrição real");
  });

  it("the composer always creates with tipo: comentario, never touching the description", async () => {
    mockCardResumo.mockReturnValue({
      data: {
        cliente: { nome: "Maria Silva" },
        tags: [],
        membros: [],
        descricao: { id: "desc1", corpo: "descrição atual", editado_em: null },
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("post-comentario"));

    expect(mockCreate.mutate).toHaveBeenCalledWith(
      { corpo: "um comentário", tipo: "comentario" },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });
});

describe("ClienteDetailModal — a rejected mutation surfaces the server's own message", () => {
  it("shows the backend's 409 message on a duplicate descricao create, via a toast — never a silent failure", async () => {
    mockCardResumo.mockReturnValue({
      data: {
        cliente: { nome: "Maria Silva" },
        tags: [],
        membros: [],
        descricao: null,
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("save-descricao"));

    const onError = mockCreate.mutate.mock.calls[0][1].onError;
    onError(new Error("[409] Este cliente já possui uma descrição — edite a existente em vez de criar outra."));

    expect(toastError).toHaveBeenCalledWith(
      "[409] Este cliente já possui uma descrição — edite a existente em vez de criar outra.",
    );
  });

  it("falls back to a Portuguese generic message when the thrown value carries none", async () => {
    mockCardResumo.mockReturnValue({
      data: {
        cliente: { nome: "Maria Silva" },
        tags: [],
        membros: [],
        descricao: null,
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("save-descricao"));

    const onError = mockCreate.mutate.mock.calls[0][1].onError;
    onError({});

    expect(toastError).toHaveBeenCalledWith("Não foi possível criar a descrição.");
  });
});

// ─── Carregamento por aba (2026-08-25) ──────────────────────────────────────
describe("ClienteDetailModal — só busca a aba que foi aberta", () => {
  it("não busca agendamentos nem roteiros ao abrir o cartão", async () => {
    // 🔴 Abrir um cartão disparava sete leituras paralelas, várias de 1,4–2,4 s,
    // para abas que a pessoa talvez nunca abra. Abrir cartão é a interação mais
    // repetida do dia. O mecanismo continua valendo para as abas que restaram.
    agendamentosIds.length = 0;
    roteirosIds.length = 0;

    await render();

    expect(agendamentosIds.every((id) => id === null)).toBe(true);
    expect(roteirosIds.every((id) => id === null)).toBe(true);
  });

  it("🔴 busca SIM documentos e dados extras — eles agora são do Geral", async () => {
    // A metade "documentos" desta regra foi APOSENTADA pela remodelagem, não
    // quebrada por ela: a aba Documentos deixou de existir e o Geral — que
    // abre junto com o cartão — absorveu a lista obrigatória, os arquivos e as
    // linhas extras. É o custo, assumido, de pôr o trabalho na primeira tela.
    documentosIds.length = 0;
    extrasIds.length = 0;

    await render();

    expect(documentosIds.some((id) => id === "cl1")).toBe(true);
    expect(extrasIds.some((id) => id === "cl1")).toBe(true);
  });
});

describe("ClienteDetailModal — dadosPessoais prefill (qualificação civil)", () => {
  it("🔴 prefills qualificação civil fields the checklist never tracks, from the already-fetched cliente row", async () => {
    // The bug: `documentoChecklist.data?.valores` alone (the OLD prop value)
    // only ever carries the checklist's own eight items
    // (nome_completo/celular/email/data_nascimento/profissao/genero/rg/cpf)
    // — nome_oficial, rg_orgao_expedidor, nacionalidade, estado_civil,
    // regime_bens and endereço were NEVER in it, so a cliente with all of
    // them already on file reopened to a blank form.
    mockCardResumo.mockReturnValue({
      data: {
        cliente: {
          id: "cl1",
          nome: "Maria Silva",
          nome_oficial: "Maria da Silva Santos",
          rg: "12.345.678-9",
          rg_orgao_expedidor: "IIGDR-SP",
          nacionalidade: "brasileira",
          estado_civil: "Casado(a)",
          regime_bens: "Comunhão parcial de bens",
          endereco_cep: "01310-100",
          endereco_logradouro: "Av. Paulista",
          endereco_numero: "1000",
          endereco_bairro: "Bela Vista",
          endereco_cidade: "São Paulo",
          endereco_uf: "SP",
        },
        tags: [],
        membros: [],
        descricao: null,
        datas: {},
        badges: {},
        atendimentos: [],
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    mockDocumentoChecklist.mockReturnValue({
      data: {
        items: [],
        total: 0,
        concluidos: 0,
        valores: { nome_completo: "Maria Silva", celular: "+5511999999999" },
      },
      isPending: false,
      isFetching: false,
    });

    const { getByTestId } = await render();
    const probe = JSON.parse(getByTestId("dados-pessoais-probe").textContent ?? "null");

    // From the checklist (its own derivation precedence — never overridden
    // by the raw cliente row).
    expect(probe.nome_completo).toBe("Maria Silva");
    expect(probe.celular).toBe("+5511999999999");
    // From `card.data.cliente` — absent from the checklist's `valores`
    // entirely, and this is what used to come back blank.
    expect(probe.nome_oficial).toBe("Maria da Silva Santos");
    expect(probe.rg).toBe("12.345.678-9");
    expect(probe.rg_orgao_expedidor).toBe("IIGDR-SP");
    expect(probe.nacionalidade).toBe("brasileira");
    expect(probe.estado_civil).toBe("Casado(a)");
    expect(probe.regime_bens).toBe("Comunhão parcial de bens");
    expect(probe.endereco_logradouro).toBe("Av. Paulista");
    expect(probe.endereco_cidade).toBe("São Paulo");
  });
});
