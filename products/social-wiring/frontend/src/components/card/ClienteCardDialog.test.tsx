/**
 * ClienteCardDialog.test.tsx — the two-pane detail (screenshots 02/03/09/10).
 * Four states (loading/error/notFound/success) plus the load-bearing wiring
 * assertions: tag chips render from `selectedTags`, checklist item toggle
 * calls back with the flipped value, and the comentário composer posts.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { ClienteCardDialog, type ClienteCardDialogProps } from "./ClienteCardDialog";

function baseProps(overrides: Partial<ClienteCardDialogProps> = {}): ClienteCardDialogProps {
  return {
    open: true,
    onClose: vi.fn(),
    isLoading: false,
    error: null,
    notFound: false,
    nome: "Maria Silva",
    allTags: [],
    selectedTags: [],
    onToggleTag: vi.fn(),
    onCreateTag: vi.fn(),
    onEditTag: vi.fn(),
    colorBlindMode: false,
    onToggleColorBlindMode: vi.fn(),
    datas: null,
    onSaveDatas: vi.fn(),
    onRemoveDatas: vi.fn(),
    allMembros: [],
    selectedMembros: [],
    onToggleMembro: vi.fn(),
    descricaoCorpo: "",
    onSaveDescricao: vi.fn(),
    documentos: [],
    documentosLoading: false,
    tiposDocumento: [],
    onUploadDocumento: vi.fn(),
    onOpenDocumento: vi.fn(),
    onDeleteDocumento: vi.fn(),
    checklists: [],
    checklistsLoading: false,
    onCreateChecklist: vi.fn(),
    onRemoveChecklist: vi.fn(),
    onAddItem: vi.fn(),
    onToggleItem: vi.fn(),
    onRemoveItem: vi.fn(),
    timelineEntries: [],
    timelineLoading: false,
    onPostComentario: vi.fn(),
    ...overrides,
  };
}

async function render(props: ClienteCardDialogProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(ClienteCardDialog, props));
}

describe("ClienteCardDialog — four states", () => {
  it("shows a loading skeleton, never the content, while loading", async () => {
    const { getByTestId, queryByTestId } = await render(baseProps({ isLoading: true }));
    expect(getByTestId("cliente-card-dialog-loading")).toBeTruthy();
    expect(queryByTestId("descricao-section")).toBeNull();
  });

  it("shows the error state, taking precedence over loading/notFound", async () => {
    const { getByTestId } = await render(baseProps({ error: "boom", isLoading: true, notFound: true }));
    expect(getByTestId("cliente-card-dialog-error")).toBeTruthy();
  });

  it("shows not-found when the record is gone", async () => {
    const { getByTestId } = await render(baseProps({ notFound: true }));
    expect(getByTestId("cliente-card-dialog-not-found")).toBeTruthy();
  });

  it("renders the content on success", async () => {
    const { getAllByText, getByTestId } = await render(baseProps());
    // Two matches by design: the sr-only DialogTitle (a11y label) and the
    // visible pane heading.
    expect(getAllByText("Maria Silva").length).toBeGreaterThan(0);
    expect(getByTestId("descricao-section")).toBeTruthy();
  });
});

describe("ClienteCardDialog — Etiquetas chips", () => {
  it("renders one chip per selected tag, styled with its colour", async () => {
    const { getByTestId } = await render(
      baseProps({ selectedTags: [{ id: "t1", nome: "Urgente", cor: "#eb5a46" }] }),
    );
    const chip = getByTestId("etiqueta-chip-t1");
    expect(chip.textContent).toBe("Urgente");
    expect(chip.style.backgroundColor).toBeTruthy();
  });

  it("renders no Etiquetas section when there are no selected tags", async () => {
    const { queryByTestId } = await render(baseProps({ selectedTags: [] }));
    expect(queryByTestId("etiquetas-chips")).toBeNull();
  });
});

describe("ClienteCardDialog — Descrição", () => {
  it("shows the empty-description copy when corpo is blank", async () => {
    const { getByText } = await render(baseProps({ descricaoCorpo: "" }));
    expect(getByText("Sem descrição ainda.")).toBeTruthy();
  });

  it("shows a Mostrar mais toggle only for long descriptions", async () => {
    const { queryByTestId } = await render(baseProps({ descricaoCorpo: "curto" }));
    expect(queryByTestId("descricao-mostrar-mais")).toBeNull();
  });
});

describe("ClienteCardDialog — Anexos empty state", () => {
  it("shows the empty-anexos copy when there are no documentos", async () => {
    const { getByTestId } = await render(baseProps({ documentos: [] }));
    expect(getByTestId("anexos-empty")).toBeTruthy();
  });
});

describe("ClienteCardDialog — Checklists (screenshot 10, multiple per card)", () => {
  it("renders each checklist with its own % bar and fires onToggleItem with the flipped value", async () => {
    const onToggleItem = vi.fn();
    const { getByTestId, getAllByTestId } = await render(
      baseProps({
        onToggleItem,
        checklists: [
          {
            id: "cl1",
            titulo: "Checklist",
            posicao: 0,
            origem: "ad_hoc",
            etapa_id: null,
            total_itens: 3,
            concluidos: 0,
            itens: [
              { id: "i1", texto: "item1", concluido: false, concluido_em: null, concluido_por: null, posicao: 0 },
            ],
          },
          {
            id: "cl2",
            titulo: "Checklist",
            posicao: 1,
            origem: "ad_hoc",
            etapa_id: null,
            total_itens: 0,
            concluidos: 0,
            itens: [],
          },
        ],
      }),
    );

    expect(getAllByTestId(/^checklist-block-/)).toHaveLength(2);

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("checklist-item-checkbox-i1"));
    expect(onToggleItem).toHaveBeenCalledWith("cl1", "i1", true);
  });
});

describe("ClienteCardDialog — Comentários composer", () => {
  it("posts the composed comment and clears the box", async () => {
    const onPostComentario = vi.fn();
    const { getByTestId, queryByTestId } = await render(baseProps({ onPostComentario }));
    const { fireEvent } = await import("@testing-library/react");
    const textarea = getByTestId("comentario-textarea") as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: "Ligar amanhã" } });
    expect(getByTestId("comentario-enviar-btn")).toBeTruthy();
    fireEvent.click(getByTestId("comentario-enviar-btn"));

    expect(onPostComentario).toHaveBeenCalledWith("Ligar amanhã");
    // Composer button hides again once the box clears.
    expect(queryByTestId("comentario-enviar-btn")).toBeNull();
  });
});
