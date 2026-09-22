/**
 * CardHubDialog.test.tsx — the seed card hub's shell.
 *
 * The generic cases are ported from
 * `products/social-wiring/frontend/src/components/card/ClienteCardDialog.test.tsx`
 * (four states, etiquetas chips, descrição, anexos, checklists, composer,
 * subpage navigation, the hover rail) — rendered here through the REGISTRY a
 * product declares instead of SW's hard-coded subpages, with SW's test ids
 * (`testId="cliente-card-dialog"`) to prove the ids stay byte-identical.
 * New here: registry semantics (only the active subpage renders, toolbars
 * belong to their subpage, `onSubpageChange`), the Geral named slots, and the
 * mobile-first sheet layout.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ClipboardList, Megaphone, Route, User } from "lucide-react";

import { CardHubDialog, type CardHubDialogProps, type CardSubpage } from "./CardHubDialog";
import { GeralActions, GeralSubpage, type GeralSubpageProps } from "./GeralSubpage";
import type { Checklist, Tag } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Key = "geral" | "cliente" | "roteiros" | "campanha";

function geralProps(over: Partial<GeralSubpageProps> = {}): GeralSubpageProps {
  return {
    tags: [],
    descricao: { corpo: "", onSave: vi.fn() },
    anexos: {
      documentos: [],
      tipos: [],
      loading: false,
      onUpload: vi.fn(),
      onOpenDocumento: vi.fn(),
      onDeleteDocumento: vi.fn(),
    },
    checklists: {
      checklists: [],
      loading: false,
      onRemoveChecklist: vi.fn(),
      onAddItem: vi.fn(),
      onToggleItem: vi.fn(),
      onRemoveItem: vi.fn(),
    },
    ...over,
  };
}

function subpages(
  opts: { geral?: Partial<GeralSubpageProps>; campanhaVazia?: boolean; renderSpy?: () => void } = {},
): CardSubpage<Key>[] {
  return [
    {
      key: "geral",
      label: "Geral",
      icon: ClipboardList,
      toolbar: (
        <GeralActions
          etiquetas={{
            allTags: [],
            selectedTagIds: [],
            onToggleTag: vi.fn(),
            onCreateTag: vi.fn(),
            onEditTag: vi.fn(),
            colorBlindMode: false,
            onToggleColorBlindMode: vi.fn(),
          }}
          membros={{ allMembros: [], selectedMembroIds: [], onToggleMembro: vi.fn() }}
          onCreateChecklist={vi.fn()}
        />
      ),
      render: () => <GeralSubpage {...geralProps(opts.geral)} />,
    },
    {
      key: "cliente",
      label: "Dados do cliente",
      icon: User,
      render: () => {
        opts.renderSpy?.();
        return <div data-testid="card-subpage-cliente">cliente</div>;
      },
    },
    {
      key: "roteiros",
      label: "Roteiros",
      icon: Route,
      render: () => <div data-testid="card-subpage-roteiros">roteiros</div>,
    },
    {
      key: "campanha",
      label: "Campanha e imóvel",
      icon: Megaphone,
      isEmpty: opts.campanhaVazia ?? false,
      render: () => <div data-testid="card-subpage-campanha">campanha</div>,
    },
  ];
}

function baseProps(over: Partial<CardHubDialogProps<Key>> = {}): CardHubDialogProps<Key> {
  return {
    open: true,
    onClose: vi.fn(),
    isLoading: false,
    error: null,
    notFound: false,
    nome: "Maria Silva",
    subpages: subpages(),
    defaultSubpage: "geral",
    testId: "cliente-card-dialog",
    activity: {
      timeline: { entries: [], loading: false },
      composer: { onPost: vi.fn() },
    },
    ...over,
  };
}

const renderDialog = (props: CardHubDialogProps<Key>) => render(<CardHubDialog {...props} />);

/** `window.matchMedia` answering the sheet query as a phone of `width` px would. */
function stubViewport(width: number) {
  vi.stubGlobal("innerWidth", width);
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({
        matches: query === "(max-width: 639px)" ? width <= 639 : false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  );
}

describe("CardHubDialog — four states", () => {
  it("shows a loading skeleton, never the content, while loading", () => {
    renderDialog(baseProps({ isLoading: true }));
    expect(screen.getByTestId("cliente-card-dialog-loading")).toBeTruthy();
    expect(screen.queryByTestId("descricao-section")).toBeNull();
  });

  it("shows the error state, taking precedence over loading/notFound", () => {
    renderDialog(baseProps({ error: "boom", isLoading: true, notFound: true }));
    expect(screen.getByTestId("cliente-card-dialog-error")).toBeTruthy();
  });

  it("shows not-found when the record is gone", () => {
    renderDialog(baseProps({ notFound: true }));
    expect(screen.getByTestId("cliente-card-dialog-not-found")).toBeTruthy();
  });

  it("renders the content on success", () => {
    renderDialog(baseProps());
    // sr-only DialogTitle + visible heading.
    expect(screen.getAllByText("Maria Silva").length).toBeGreaterThan(0);
    expect(screen.getByTestId("descricao-section")).toBeTruthy();
  });

  it("derives every state testid from the root testid (seed default `card-hub-dialog`)", () => {
    renderDialog(baseProps({ testId: undefined, isLoading: true }));
    expect(screen.getByTestId("card-hub-dialog")).toBeTruthy();
    expect(screen.getByTestId("card-hub-dialog-loading")).toBeTruthy();
  });

  it("renders header actions beside the title", () => {
    renderDialog(baseProps({ headerActions: <button data-testid="acao-quadro">x</button> }));
    expect(screen.getByTestId("acao-quadro")).toBeTruthy();
  });
});

describe("GeralSubpage — etiquetas chips", () => {
  it("renders one chip per selected tag, styled with its colour", () => {
    const tags: Tag[] = [{ id: "t1", nome: "Urgente", cor: "#eb5a46" }];
    renderDialog(baseProps({ subpages: subpages({ geral: { tags } }) }));
    const chip = screen.getByTestId("etiqueta-chip-t1");
    expect(chip.textContent).toBe("Urgente");
    expect(chip.style.backgroundColor).toBeTruthy();
  });

  it("renders no Etiquetas section when there are no selected tags", () => {
    renderDialog(baseProps());
    expect(screen.queryByTestId("etiquetas-chips")).toBeNull();
  });
});

describe("GeralSubpage — Descrição", () => {
  it("shows the empty-description copy when corpo is blank", () => {
    renderDialog(baseProps());
    expect(screen.getByText("Sem descrição ainda.")).toBeTruthy();
  });

  it("shows a Mostrar mais toggle only for long descriptions", () => {
    renderDialog(
      baseProps({ subpages: subpages({ geral: { descricao: { corpo: "curto", onSave: vi.fn() } } }) }),
    );
    expect(screen.queryByTestId("descricao-mostrar-mais")).toBeNull();
    cleanup();
    renderDialog(
      baseProps({
        subpages: subpages({ geral: { descricao: { corpo: "x".repeat(300), onSave: vi.fn() } } }),
      }),
    );
    expect(screen.getByTestId("descricao-mostrar-mais")).toBeTruthy();
  });

  it("keeps Editar reachable by name once it is icon-only, and saves the draft", () => {
    const onSave = vi.fn();
    renderDialog(
      baseProps({ subpages: subpages({ geral: { descricao: { corpo: "antes", onSave } } }) }),
    );
    const editar = screen.getByTestId("descricao-editar-btn");
    expect(editar.getAttribute("aria-label")).toBe("Editar descrição");
    fireEvent.click(editar);
    fireEvent.change(screen.getByTestId("descricao-textarea"), { target: { value: "depois" } });
    fireEvent.click(screen.getByTestId("descricao-salvar-btn"));
    expect(onSave).toHaveBeenCalledWith("depois");
  });
});

describe("GeralSubpage — Anexos", () => {
  it("shows the empty-anexos copy and owns its own file input", () => {
    renderDialog(baseProps());
    expect(screen.getByTestId("anexos-empty")).toBeTruthy();
    const btn = screen.getByTestId("anexo-enviar-btn");
    expect(btn.getAttribute("aria-label")).toBe("Escolha o tipo do documento antes de enviar");
    expect(screen.getByTestId("anexos-section").querySelector('input[type="file"]')).toBeTruthy();
  });
});

describe("GeralSubpage — Checklists (multiple per card)", () => {
  const checklists: Checklist[] = [
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
  ];

  it("renders each checklist with its own % bar and fires onToggleItem with the flipped value", () => {
    const onToggleItem = vi.fn();
    renderDialog(
      baseProps({
        subpages: subpages({
          geral: { checklists: { ...geralProps().checklists, checklists, onToggleItem } },
        }),
      }),
    );
    expect(screen.getAllByTestId(/^checklist-block-/)).toHaveLength(2);
    fireEvent.click(screen.getByTestId("checklist-item-checkbox-i1"));
    expect(onToggleItem).toHaveBeenCalledWith("cl1", "i1", true);
  });

  it("adds an item on Enter and clears the input", () => {
    const onAddItem = vi.fn();
    renderDialog(
      baseProps({
        subpages: subpages({
          geral: { checklists: { ...geralProps().checklists, checklists, onAddItem } },
        }),
      }),
    );
    const input = screen.getByTestId("checklist-novo-item-cl1") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "novo" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onAddItem).toHaveBeenCalledWith("cl1", "novo");
    expect(input.value).toBe("");
  });

  it("🔴 a refetch over existing checklists never swaps them for a skeleton", () => {
    renderDialog(
      baseProps({
        subpages: subpages({
          geral: { checklists: { ...geralProps().checklists, checklists, loading: true } },
        }),
      }),
    );
    expect(screen.getAllByTestId(/^checklist-block-/)).toHaveLength(2);
    expect(screen.queryByTestId("checklists-loading")).toBeNull();
  });

  it("shows the skeleton only while there is nothing yet", () => {
    renderDialog(
      baseProps({
        subpages: subpages({ geral: { checklists: { ...geralProps().checklists, loading: true } } }),
      }),
    );
    expect(screen.getByTestId("checklists-loading")).toBeTruthy();
  });
});

describe("GeralSubpage — named slots", () => {
  it("🔴 renders each slot at its named point in the work order", () => {
    renderDialog(
      baseProps({
        subpages: subpages({
          geral: {
            tags: [{ id: "t1", nome: "A", cor: "#000" }],
            slots: {
              afterTags: <div data-testid="slot-after-tags" />,
              afterDescricao: <div data-testid="slot-after-descricao" />,
              beforeAnexos: <div data-testid="slot-before-anexos" />,
            },
          },
        }),
      }),
    );
    const ordem = [
      "etiquetas-chips",
      "slot-after-tags",
      "descricao-section",
      "slot-after-descricao",
      "slot-before-anexos",
      "anexos-section",
    ].map((id) => screen.getByTestId(id));
    for (let i = 1; i < ordem.length; i++) {
      // DOCUMENT_POSITION_FOLLOWING = 4
      expect(ordem[i - 1].compareDocumentPosition(ordem[i]) & 4).toBe(4);
    }
  });
});

describe("CardHubDialog — Comentários composer", () => {
  it("posts the composed comment and clears the box", () => {
    const onPost = vi.fn();
    renderDialog(baseProps({ activity: { timeline: { entries: [], loading: false }, composer: { onPost } } }));
    const textarea = screen.getByTestId("comentario-textarea") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Ligar amanhã" } });
    fireEvent.click(screen.getByTestId("comentario-enviar-btn"));
    expect(onPost).toHaveBeenCalledWith("Ligar amanhã");
    expect(screen.queryByTestId("comentario-enviar-btn")).toBeNull();
  });

  it("🔴 the composer KEPT its word — the post action is not icon-only", () => {
    renderDialog(baseProps());
    fireEvent.change(screen.getByTestId("comentario-textarea"), { target: { value: "x" } });
    expect(screen.getByTestId("comentario-enviar-btn").textContent).toBe("Comentar");
  });

  it("renders the timeline in the activity pane", () => {
    renderDialog(baseProps());
    expect(screen.getByTestId("cliente-card-dialog-activity").textContent).toContain(
      "Comentários e atividade",
    );
    expect(screen.getByTestId("timeline-empty")).toBeTruthy();
  });
});

describe("CardHubDialog — subpage registry", () => {
  it("🔴 opens on the default subpage and renders ONLY it", () => {
    const renderSpy = vi.fn();
    renderDialog(baseProps({ subpages: subpages({ renderSpy }) }));
    expect(screen.getByTestId("card-subpage-tab-geral").getAttribute("data-active")).toBe("true");
    expect(screen.getByTestId("descricao-section")).toBeTruthy();
    // A subpage nobody opened costs nothing — its render thunk never ran.
    expect(renderSpy).not.toHaveBeenCalled();
  });

  it("defaults to the FIRST registered subpage when none is named", () => {
    renderDialog(baseProps({ defaultSubpage: undefined }));
    expect(screen.getByTestId("card-subpage-tab-geral").getAttribute("data-active")).toBe("true");
  });

  it("renders the rail in registry order", () => {
    renderDialog(baseProps());
    const chaves = Array.from(
      screen.getByTestId("card-sidebar-nav").querySelectorAll("[data-testid^='card-subpage-tab-']"),
    ).map((el) => el.getAttribute("data-testid"));
    expect(chaves).toEqual([
      "card-subpage-tab-geral",
      "card-subpage-tab-cliente",
      "card-subpage-tab-roteiros",
      "card-subpage-tab-campanha",
    ]);
  });

  it("swaps the middle pane without closing the card, and reports the selection", () => {
    const onClose = vi.fn();
    const onSubpageChange = vi.fn();
    renderDialog(baseProps({ onClose, onSubpageChange }));
    fireEvent.click(screen.getByTestId("card-subpage-tab-cliente"));
    expect(screen.getByTestId("card-subpage-cliente")).toBeTruthy();
    expect(screen.queryByTestId("descricao-section")).toBeNull();
    expect(onSubpageChange).toHaveBeenCalledWith("cliente");
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("card-subpage-tab-geral"));
    expect(screen.getByTestId("descricao-section")).toBeTruthy();
  });

  it("🔴 a subpage's toolbar belongs to it — Geral's actions show nowhere else", () => {
    renderDialog(baseProps());
    expect(screen.getByTestId("etiquetas-trigger")).toBeTruthy();
    expect(screen.getByTestId("checklist-trigger")).toBeTruthy();
    expect(screen.getByTestId("membros-trigger")).toBeTruthy();
    fireEvent.click(screen.getByTestId("card-subpage-tab-roteiros"));
    expect(screen.queryByTestId("etiquetas-trigger")).toBeNull();
  });

  it("an empty subpage is disabled, never dropped", () => {
    renderDialog(baseProps({ subpages: subpages({ campanhaVazia: true }) }));
    expect((screen.getByTestId("card-subpage-tab-campanha") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("card-subpage-tab-geral") as HTMLButtonElement).disabled).toBe(false);
  });

  it("GeralActions inserts a product action after Etiquetas", () => {
    const toolbar = (
      <GeralActions
        etiquetas={{
          allTags: [],
          selectedTagIds: [],
          onToggleTag: vi.fn(),
          onCreateTag: vi.fn(),
          onEditTag: vi.fn(),
          colorBlindMode: false,
          onToggleColorBlindMode: vi.fn(),
        }}
        membros={{ allMembros: [], selectedMembroIds: [], onToggleMembro: vi.fn() }}
        onCreateChecklist={vi.fn()}
        afterEtiquetas={<button data-testid="agendar-trigger">Agendar</button>}
      />
    );
    const [geral, ...rest] = subpages();
    renderDialog(baseProps({ subpages: [{ ...geral, toolbar }, ...rest] }));
    const ids = Array.from(screen.getByTestId("card-geral-actions").querySelectorAll("button"))
      .map((b) => b.getAttribute("data-testid"))
      .filter(Boolean);
    expect(ids).toEqual(["etiquetas-trigger", "agendar-trigger", "checklist-trigger", "membros-trigger"]);
  });
});

describe("CardSidebarNav — the hover rail (desktop, SW parity)", () => {
  it("🔴 expands as an OVERLAY — the reserved column never changes width", () => {
    renderDialog(baseProps());
    const trilho = screen.getByTestId("card-sidebar-rail");
    const nav = screen.getByTestId("card-sidebar-nav");
    expect(trilho.className).toContain("md:w-[3.25rem]");
    expect(trilho.className).toContain("relative");
    expect(nav.className).toContain("md:absolute");
    expect(nav.className).toContain("md:hover:w-56");
  });

  it("🔴 KEYBOARD focus expands it too — `has-[:focus-visible]`, not `focus-within`", () => {
    renderDialog(baseProps());
    const nav = screen.getByTestId("card-sidebar-nav");
    expect(nav.className).toContain("md:has-[:focus-visible]:w-56");
    expect(nav.className).not.toContain("md:focus-within:w-56");
    expect(screen.getByTestId("card-subpage-label-geral").className).toContain(
      "md:group-has-[:focus-visible]:w-auto",
    );
  });

  it("🔴 every rail button keeps an accessible name while collapsed", () => {
    renderDialog(baseProps());
    expect(screen.getByTestId("card-subpage-tab-geral").getAttribute("aria-label")).toBe("Geral");
    expect(screen.getByTestId("card-subpage-label-cliente").textContent).toBe("Dados do cliente");
  });
});

describe("CardHubDialog — mobile-first (R0)", () => {
  it("🔴 renders as a full-screen sheet at a 390px viewport", () => {
    stubViewport(390);
    renderDialog(baseProps());
    const dialog = screen.getByTestId("cliente-card-dialog");
    expect(dialog.getAttribute("data-layout")).toBe("sheet");
    const classes = dialog.className.split(/\s+/);
    // Full viewport, frameless, one scrolling column.
    expect(classes).toEqual(
      expect.arrayContaining([
        "max-sm:h-[100dvh]",
        "max-sm:w-screen",
        "max-sm:max-w-none",
        "max-sm:rounded-none",
        "max-sm:overflow-y-auto",
      ]),
    );
    // Single column below `md`: the activity pane stacks below the subpage.
    expect(classes).toContain("grid-cols-1");
  });

  it("🔴 the rail becomes a sticky, horizontally scrollable tab strip with 40px targets", () => {
    stubViewport(390);
    renderDialog(baseProps());
    const trilho = screen.getByTestId("card-sidebar-rail").className.split(/\s+/);
    expect(trilho).toEqual(expect.arrayContaining(["max-sm:sticky", "max-sm:top-0"]));
    const nav = screen.getByTestId("card-sidebar-nav").className.split(/\s+/);
    expect(nav).toContain("overflow-x-auto");
    const tab = screen.getByTestId("card-subpage-tab-geral").className.split(/\s+/);
    expect(tab).toEqual(
      expect.arrayContaining(["max-sm:min-h-10", "max-sm:shrink-0", "max-sm:whitespace-nowrap"]),
    );
  });

  it("icon actions meet the 40px touch floor below `sm`", () => {
    stubViewport(390);
    renderDialog(baseProps({ subpages: subpages({ geral: { descricao: { corpo: "x", onSave: vi.fn() } } }) }));
    for (const id of ["descricao-editar-btn", "etiquetas-trigger", "anexo-enviar-btn"]) {
      expect(screen.getByTestId(id).className.split(/\s+/)).toEqual(
        expect.arrayContaining(["max-sm:min-h-10", "max-sm:min-w-10"]),
      );
    }
  });

  it("🔴 desktop keeps SW's dialog classes unchanged (≥640px)", () => {
    stubViewport(1280);
    renderDialog(baseProps());
    const dialog = screen.getByTestId("cliente-card-dialog");
    expect(dialog.getAttribute("data-layout")).toBe("dialog");
    const desktop = dialog.className
      .split(/\s+/)
      .filter((c) => !c.startsWith("max-sm:"))
      .join(" ");
    for (const c of [
      "grid",
      "h-[90vh]",
      "w-[90vw]",
      "max-w-[90vw]",
      "grid-cols-1",
      "gap-0",
      "overflow-hidden",
      "p-0",
      "md:grid-cols-[3.25rem_1fr_360px]",
    ]) {
      expect(desktop.split(" ")).toContain(c);
    }
  });

  it("reads as desktop when matchMedia is unavailable (CSS still switches in a browser)", () => {
    vi.stubGlobal("matchMedia", undefined);
    renderDialog(baseProps());
    expect(screen.getByTestId("cliente-card-dialog").getAttribute("data-layout")).toBe("dialog");
  });
});
