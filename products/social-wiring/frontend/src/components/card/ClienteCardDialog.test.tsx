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
    agendamentos: [],
    onCreateAgendamento: vi.fn(),
    onRemoveAgendamento: vi.fn(),
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

// ── 2026-08-19 — the user's refinement pass ────────────────────────────────
//
// Each of these pins one thing that was reported as wrong against the LIVE
// card, so a regression here is a regression the user already caught once.

describe("dados do lead", () => {
  const CAMPANHA = {
    id: "2121601435435308",
    full_name: "Luciano Mauricio",
    email: "lumtluciano@hotmail.com",
    phone: "+5511985295496",
    campaign_id: "c1",
    campaign_name: "[🏠 Até R$1 Milhão] [SENSEYS]",
    form_id: "f1",
    form_name: "[Senseys] ONE10503",
    ad_id: "52533897478137",
    adset_id: "6882263048933",
    platform: "ig",
    is_organic: false,
    created_time: "2026-07-28T13:55:26Z",
    answers: { ref: "ONE10503" },
  };

  const COM_CAMPANHA = baseProps({
    nome: "Luciano Mauricio",
    atendimentos: [
      {
        id: "a1",
        titulo: "Luciano Mauricio",
        status: "aberta",
        closed_at: null,
        created_at: null,
        lead_id: null,
        meta_ads_lead_id: CAMPANHA.id,
        lead: null,
        campanha: CAMPANHA as never,
      },
    ],
  });

  it("🔴 renders the person's OWN data — the card showed only a name before", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...COM_CAMPANHA} />);

    fireEvent.click(screen.getByTestId("card-subpage-tab-cliente"));
    expect(screen.getByTestId("card-subpage-cliente")).toBeTruthy();
    expect(screen.getByText("lumtluciano@hotmail.com")).toBeTruthy();
  });

  it("files the campaign and the property under their own subpage", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...COM_CAMPANHA} />);

    fireEvent.click(screen.getByTestId("card-subpage-tab-campanha"));
    expect(screen.getByText("[🏠 Até R$1 Milhão] [SENSEYS]")).toBeTruthy();
    // The form answers ride with the campaign, not with the person.
    expect(screen.getByText("ONE10503")).toBeTruthy();
  });

  it("keeps the record data OFF the default subpage", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...COM_CAMPANHA} />);
    expect(screen.queryByTestId("card-subpage-cliente")).toBeNull();
    expect(screen.queryByTestId("card-subpage-campanha")).toBeNull();
  });

  it("disables both record subpages when the card has no origin record", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ atendimentos: [] })} />);
    // Disabled, not dropped: a rail whose items come and go per record teaches
    // the user nothing about where a thing lives.
    expect(screen.getByTestId("card-subpage-tab-cliente").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("card-subpage-tab-campanha").hasAttribute("disabled")).toBe(true);
  });
});

describe("navegação por subpáginas (barra lateral)", () => {
  it("🔴 opens on Atividade — the card is opened to DO something, not to read", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ descricaoCorpo: "Interessado" })} />);

    expect(screen.getByTestId("card-sidebar-nav")).toBeTruthy();
    expect(screen.getByTestId("card-subpage-tab-atividade").getAttribute("data-active")).toBe("true");
    expect(screen.getByTestId("descricao-section")).toBeTruthy();
  });

  it("swaps the middle pane without closing the card", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    const onClose = vi.fn();
    render(
      <ClienteCardDialog
        {...baseProps({
          onClose,
          descricaoCorpo: "Interessado",
          atendimentos: [
            {
              id: "a1",
              titulo: "x",
              status: "aberta",
              closed_at: null,
              created_at: null,
              lead_id: null,
              meta_ads_lead_id: "m1",
              lead: null,
              campanha: {
                id: "m1",
                full_name: "Ana",
                email: "ana@example.com",
                phone: null,
                campaign_id: "c1",
                campaign_name: "Campanha A",
                form_id: "f1",
                form_name: "Form A",
                ad_id: null,
                adset_id: null,
                platform: "fb",
                is_organic: false,
                created_time: null,
                answers: {},
              } as never,
            },
          ],
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("card-subpage-tab-cliente"));
    expect(screen.getByTestId("card-subpage-cliente")).toBeTruthy();
    // The working sections are hidden, not unmounted-and-remounted-elsewhere.
    expect(screen.queryByTestId("descricao-section")).toBeNull();
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("card-subpage-tab-atividade"));
    expect(screen.getByTestId("descricao-section")).toBeTruthy();
  });
});

describe("ordem das seções", () => {
  it("🔴 descrição → agendamento → checklist → anexos, in that order", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { container } = render(
      <ClienteCardDialog
        {...baseProps({
          descricaoCorpo: "Lead interessado em imóvel",
          agendamentos: [
            {
              id: "ag1",
              atendimento_id: "a1",
              quando: "2099-08-20T12:00:00Z",
              tipo: "visita",
              nota: null,
              lembrete_minutos_antes: 60,
              created_at: null,
            },
          ],
          checklists: [
            { id: "c1", titulo: "Checklist", posicao: 0, itens: [] } as never,
          ],
          documentos: [
            {
              id: "d1",
              nome_arquivo: "anuncios.pdf",
              tamanho_bytes: 3072,
              created_at: "2026-08-19T19:20:00Z",
              tipo_documento: "outro",
            } as never,
          ],
        })}
      />,
    );
    // By testid, not by text: "Checklist" is BOTH the toolbar button and the
    // section heading, so getByText was ambiguous — the assertion has to name
    // the sections themselves.
    const all = Array.from(container.querySelectorAll("*"));
    const at = (testId: string) => all.indexOf(screen.getByTestId(testId));
    const order = [
      at("descricao-section"),
      at("agendamentos-section"),
      at("checklists-section"),
      at("anexos-section"),
    ];
    expect(order).toEqual([...order].sort((a, b) => a - b));
    // anexos LAST, explicitly — the whole point of the reorder
    expect(order[3]).toBe(Math.max(...order));
  });
});

describe("agendamentos", () => {
  const AG = (over: Record<string, unknown> = {}) => ({
    id: "ag1",
    atendimento_id: "a1",
    quando: "2099-08-20T12:00:00Z",
    tipo: "visita" as const,
    nota: null,
    lembrete_minutos_antes: 60,
    created_at: null,
    ...over,
  });

  it("🔴 shows the reminder — it was stored and scheduled but never displayed", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ agendamentos: [AG()] })} />);
    expect(screen.getByTestId("agendamento-lembrete").textContent).toContain("1 hora antes");
  });

  it("🔴 lists MANY — the old model could hold exactly one", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          agendamentos: [
            AG({ id: "ag1", quando: "2099-08-20T12:00:00Z" }),
            AG({ id: "ag2", quando: "2099-08-25T15:00:00Z", tipo: "ligacao" }),
          ],
        })}
      />,
    );
    expect(screen.getByTestId("agendamento-ag1")).toBeTruthy();
    expect(screen.getByTestId("agendamento-ag2")).toBeTruthy();
  });

  it("is absent when none are booked, rather than an empty heading", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ agendamentos: [] })} />);
    expect(screen.queryByTestId("agendamentos-section")).toBeNull();
  });

  it("removing one calls back with its id", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onRemoveAgendamento = vi.fn();
    render(
      <ClienteCardDialog {...baseProps({ agendamentos: [AG()], onRemoveAgendamento })} />,
    );
    fireEvent.click(screen.getByTestId("agendamento-remover-ag1"));
    expect(onRemoveAgendamento).toHaveBeenCalledWith("ag1");
  });
});

describe("o botão Adicionar", () => {
  it("🔴 is gone — it was a second, generic route to the specific buttons", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps()} />);
    expect(screen.queryByTestId("adicionar-trigger")).toBeNull();
    // the specific ones must all still be there
    // `datas-trigger` became `agendamento-trigger` when the single-slot Datas
    // popover was replaced by one that ADDS appointments (migration 061).
    for (const id of ["etiquetas-trigger", "agendamento-trigger", "membros-trigger"]) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
  });
});
