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
vi.mock("sonner", () => ({ toast: { error: toastError } }));

vi.mock("@/hooks/useLeadsCorretores", () => ({
  useLeadCorretores: () => ({ data: [] }),
}));

const { mockCreate, mockUpdate, mockCardResumo } = vi.hoisted(() => ({
  mockCreate: { mutate: vi.fn(), isPending: false },
  mockUpdate: { mutate: vi.fn(), isPending: false },
  mockCardResumo: vi.fn(),
}));

const documentosIds: (string | null)[] = [];
const agendamentosIds: (string | null)[] = [];

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
  useDocumentoChecklist: () => ({
    data: { items: [], total: 0, concluidos: 0 },
    isPending: false,
    isFetching: false,
  }),
  useDocumentoChecklistMutation: () => ({ mutate: vi.fn(), isPending: false }),
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
  }),
  useDadosPessoaisMutation: () => ({ mutate: vi.fn(), isPending: false }),
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
  }),
}));

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
  it("não busca documentos nem agendamentos ao abrir o cartão", async () => {
    // 🔴 Abrir um cartão disparava sete leituras paralelas, várias de 1,4–2,4 s,
    // para abas que a pessoa talvez nunca abra. Abrir cartão é a interação mais
    // repetida do dia.
    documentosIds.length = 0;
    agendamentosIds.length = 0;

    await render();

    expect(documentosIds.every((id) => id === null)).toBe(true);
    expect(agendamentosIds.every((id) => id === null)).toBe(true);
  });
});
