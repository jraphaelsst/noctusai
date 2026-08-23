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
    documentoChecklist: [],
    onToggleDocumentoChecklist: vi.fn(),
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
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentos: [] })} />);
    fireEvent.click(screen.getByTestId("card-subpage-tab-documentos"));
    expect(screen.getByTestId("anexos-empty")).toBeTruthy();
  });

  it("🔴 offers a way to upload — the trigger was missing entirely", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentos: [] })} />);
    fireEvent.click(screen.getByTestId("card-subpage-tab-documentos"));
    // Removing the generic `Adicionar` button took the ONLY thing that opened
    // the file input, and nothing replaced it — uploading was unreachable.
    expect(screen.getByTestId("anexo-enviar-btn")).toBeTruthy();
    expect(document.getElementById("card-anexo-file-input")).toBeTruthy();
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
    expect(screen.getByTestId("card-subpage-tab-geral").getAttribute("data-active")).toBe("true");
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

    fireEvent.click(screen.getByTestId("card-subpage-tab-geral"));
    expect(screen.getByTestId("descricao-section")).toBeTruthy();
  });
});

describe("ordem das seções", () => {
  const AG = {
    id: "ag1",
    atendimento_id: "a1",
    quando: "2099-08-20T12:00:00Z",
    tipo: "visita",
    nota: null,
    lembrete_minutos_antes: 60,
    created_at: null,
  };
  const DOC = {
    id: "d1",
    nome_arquivo: "anuncios.pdf",
    tamanho_bytes: 3072,
    created_at: "2026-08-19T19:20:00Z",
    tipo_documento: "outro",
  };

  function full() {
    return baseProps({
      descricaoCorpo: "Lead interessado em imóvel",
      agendamentos: [AG as never],
      checklists: [{ id: "c1", titulo: "Checklist", posicao: 0, itens: [] } as never],
      documentos: [DOC as never],
      documentoChecklist: [
        {
          key: "nome_completo",
          label: "Nome Completo",
          concluido: false,
          origem: "derivado" as const,
          derivado: false,
          sugestao: null,
          concluido_em: null,
          concluido_por: null,
        },
      ],
    });
  }

  function orderOf(container: HTMLElement, screen: any, ids: string[]) {
    const all = Array.from(container.querySelectorAll("*"));
    return ids.map((id) => all.indexOf(screen.getByTestId(id)));
  }

  it("Geral keeps descrição → checklist; agendamentos and anexos moved out", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { container } = render(<ClienteCardDialog {...full()} />);

    const order = orderOf(container, screen, ["descricao-section", "checklists-section"]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    // They are not merely reordered — they are on other tabs now.
    expect(screen.queryByTestId("agendamentos-section")).toBeNull();
    expect(screen.queryByTestId("anexos-section")).toBeNull();
  });

  it("🔴 Documentos puts the required-data checklist ABOVE anexos", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    const { container } = render(<ClienteCardDialog {...full()} />);
    fireEvent.click(screen.getByTestId("card-subpage-tab-documentos"));

    const order = orderOf(container, screen, [
      "documento-checklist-section",
      "anexos-section",
    ]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});

describe("dados obrigatórios (checklist permanente)", () => {
  const ITENS = [
    { key: "nome_completo", label: "Nome Completo" },
    { key: "email", label: "Email" },
    { key: "data_nascimento", label: "Data de Nascimento" },
    { key: "genero", label: "Gênero" },
    { key: "rg", label: "RG" },
    { key: "cpf", label: "CPF" },
  ].map((i) => ({
    ...i,
    concluido: false,
    // Ticks are DERIVED (migration 068); `manual` only appears once a human
    // has forced one, which is what the override tests below exercise.
    origem: "derivado" as const,
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
  }));

  async function openDocumentos(overrides = {}) {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentoChecklist: ITENS, ...overrides })} />);
    fireEvent.click(screen.getByTestId("card-subpage-tab-documentos"));
    return { fireEvent, screen };
  }

  it("🔴 renders the six the user asked for, in order", async () => {
    const { screen } = await openDocumentos();
    const labels = ITENS.map((i) => i.label);
    for (const label of labels) expect(screen.getByLabelText(label)).toBeTruthy();
    expect(screen.getByTestId("documento-checklist-progresso").textContent).toBe("0/6");
  });

  it("ticking one calls back with its key", async () => {
    const onToggleDocumentoChecklist = vi.fn();
    const { fireEvent, screen } = await openDocumentos({ onToggleDocumentoChecklist });
    fireEvent.click(screen.getByTestId("documento-checklist-cpf"));
    expect(onToggleDocumentoChecklist).toHaveBeenCalledWith("cpf", true);
  });

  it("shows progress from what is already ticked", async () => {
    const ticked = ITENS.map((i) =>
      i.key === "rg" || i.key === "cpf"
        ? { ...i, concluido: true, derivado: true }
        : i,
    );
    const { screen } = await openDocumentos({ documentoChecklist: ticked });
    expect(screen.getByTestId("documento-checklist-progresso").textContent).toBe("2/6");
  });

  it("a derived tick carries no manual badge and no withdraw button", async () => {
    const ticked = ITENS.map((i) =>
      i.key === "rg" ? { ...i, concluido: true, derivado: true } : i,
    );
    const { screen } = await openDocumentos({ documentoChecklist: ticked });
    expect(screen.queryByTestId("documento-checklist-rg-manual")).toBeNull();
    expect(screen.queryByTestId("documento-checklist-rg-limpar")).toBeNull();
  });

  it("🔴 an override that disagrees with the data is labelled, not silent", async () => {
    // A tick the record does not support must never read as evidence that the
    // data is there — that is the whole failure the derivation removes, and
    // the one case where a human can still reintroduce it deliberately.
    const forced = ITENS.map((i) =>
      i.key === "genero" ? { ...i, concluido: true, origem: "manual" as const } : i,
    );
    const { screen } = await openDocumentos({ documentoChecklist: forced });
    const badge = screen.getByTestId("documento-checklist-genero-manual");
    expect(badge.getAttribute("title")).toContain("pendente");
  });

  it("withdrawing an override hands the item back to the data", async () => {
    const onToggleDocumentoChecklist = vi.fn();
    const forced = ITENS.map((i) =>
      i.key === "email" ? { ...i, concluido: true, origem: "manual" as const } : i,
    );
    const { fireEvent, screen } = await openDocumentos({
      documentoChecklist: forced,
      onToggleDocumentoChecklist,
    });
    fireEvent.click(screen.getByTestId("documento-checklist-email-limpar"));
    expect(onToggleDocumentoChecklist).toHaveBeenCalledWith("email", null);
  });

  const SUGESTAO = {
    valor: "1980-05-12",
    documento_id: "doc-1",
    documento_nome: "rg.pdf",
    tipo_documento: "rg",
    confianca: "baixa",
    fonte: "ocr",
    rotulo: "DATA DE NASCIMENTO",
  };

  function withSugestao() {
    return ITENS.map((i) =>
      i.key === "data_nascimento" ? { ...i, sugestao: SUGESTAO } : i,
    );
  }

  it("🔴 a low-confidence read renders as a question, not as a filled field", async () => {
    // The item must still read as NOT done: anything that looks already-applied
    // gets confirmed by reflex, which is the failure this whole path prevents.
    const { screen } = await openDocumentos({
      documentoChecklist: withSugestao(),
      onResolverSugestao: vi.fn(),
    });
    expect(
      (screen.getByTestId("documento-checklist-data_nascimento") as HTMLInputElement)
        .checked,
    ).toBe(false);
    expect(screen.getByTestId("documento-checklist-progresso").textContent).toBe("0/6");
    expect(screen.getByTestId("documento-checklist-data_nascimento-sugestao")).toBeTruthy();
  });

  it("names the document and the source so the operator knows what to doubt", async () => {
    const { screen } = await openDocumentos({
      documentoChecklist: withSugestao(),
      onResolverSugestao: vi.fn(),
    });
    const box = screen.getByTestId("documento-checklist-data_nascimento-sugestao");
    expect(box.textContent).toContain("rg.pdf");
    expect(box.textContent).toContain("OCR");
    expect(box.textContent).toContain("DATA DE NASCIMENTO");
  });

  it("🔴 renders the date as DD/MM/YYYY without a timezone shift", async () => {
    // `new Date("1980-05-12")` is UTC midnight rendered locally, which shows
    // as the 11th anywhere west of UTC — a birthday off by one on the exact
    // screen where someone is checking it against a document.
    const { screen } = await openDocumentos({
      documentoChecklist: withSugestao(),
      onResolverSugestao: vi.fn(),
    });
    expect(
      screen.getByTestId("documento-checklist-data_nascimento-sugestao-valor").textContent,
    ).toContain("12/05/1980");
  });

  it("confirming and discarding each call back with the document id", async () => {
    const onResolverSugestao = vi.fn();
    const { fireEvent, screen } = await openDocumentos({
      documentoChecklist: withSugestao(),
      onResolverSugestao,
    });
    fireEvent.click(
      screen.getByTestId("documento-checklist-data_nascimento-sugestao-confirmar"),
    );
    expect(onResolverSugestao).toHaveBeenCalledWith("doc-1", "confirmar");

    fireEvent.click(
      screen.getByTestId("documento-checklist-data_nascimento-sugestao-descartar"),
    );
    expect(onResolverSugestao).toHaveBeenCalledWith("doc-1", "descartar");
  });

  it("no prompt renders when there is no suggestion", async () => {
    const { screen } = await openDocumentos({ onResolverSugestao: vi.fn() });
    expect(
      screen.queryByTestId("documento-checklist-data_nascimento-sugestao"),
    ).toBeNull();
  });

  it("is NOT on Geral — it belongs to Documentos", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentoChecklist: ITENS })} />);
    expect(screen.queryByTestId("documento-checklist-section")).toBeNull();
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

  /** Agendamentos own a TAB now — every assertion below has to go there first. */
  async function openAgendamentos(overrides: Record<string, unknown> = {}) {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps(overrides as never)} />);
    fireEvent.click(screen.getByTestId("card-subpage-tab-agendamentos"));
    return { fireEvent, screen };
  }

  it("🔴 shows the reminder — it was stored and scheduled but never displayed", async () => {
    const { screen } = await openAgendamentos({ agendamentos: [AG()] });
    expect(screen.getByTestId("agendamento-lembrete").textContent).toContain("1 hora antes");
  });

  it("🔴 lists MANY — the old model could hold exactly one", async () => {
    const { screen } = await openAgendamentos({
      agendamentos: [
        AG({ id: "ag1", quando: "2099-08-20T12:00:00Z" }),
        AG({ id: "ag2", quando: "2099-08-25T15:00:00Z", tipo: "ligacao" }),
      ],
    });
    expect(screen.getByTestId("agendamento-ag1")).toBeTruthy();
    expect(screen.getByTestId("agendamento-ag2")).toBeTruthy();
  });

  it("🔴 an empty tab still offers a way to book — it is not a dead end", async () => {
    const { screen } = await openAgendamentos({ agendamentos: [] });
    // This USED to render nothing, which was right while it was one section
    // among several on Geral. On its own tab that is a blank page with no
    // trigger, so the heading + empty copy now stay.
    expect(screen.getByTestId("agendamentos-section")).toBeTruthy();
    expect(screen.getByTestId("agendamentos-empty")).toBeTruthy();
  });

  it("removing one calls back with its id", async () => {
    const onRemoveAgendamento = vi.fn();
    const { fireEvent, screen } = await openAgendamentos({
      agendamentos: [AG()],
      onRemoveAgendamento,
    });
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


describe("a barra de ações pertence ao Geral", () => {
  async function open(tab: string) {
    const { cleanup, fireEvent, render, screen } = await import("@testing-library/react");
    // Cleanup FIRST: this helper is called in a loop, and a previous render
    // left on the document makes `queryByTestId` find the Geral row that the
    // assertion is trying to prove absent.
    cleanup();
    // A record is required, not decoration: with no atendimentos the cliente
    // and campanha tabs render DISABLED, the click is a no-op, and the test
    // would assert against Geral while believing it had navigated away.
    render(
      <ClienteCardDialog
        {...baseProps({
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
    if (tab !== "geral") fireEvent.click(screen.getByTestId(`card-subpage-tab-${tab}`));
    return screen;
  }

  it("🔴 Etiquetas and Agendar show on Geral", async () => {
    const screen = await open("geral");
    expect(screen.getByTestId("etiquetas-trigger")).toBeTruthy();
    expect(screen.getByTestId("agendamento-trigger")).toBeTruthy();
  });

  it("🔴 and nowhere else — a quick-action row over an unrelated tab is noise", async () => {
    for (const tab of ["cliente", "agendamentos", "documentos", "campanha"]) {
      const screen = await open(tab);
      expect(screen.queryByTestId("etiquetas-trigger")).toBeNull();
    }
  });

  it("the Agendamentos tab carries its OWN trigger, so booking stays reachable", async () => {
    const screen = await open("agendamentos");
    // Same popover component, rendered by the section instead of the row.
    expect(screen.getByTestId("agendamento-trigger")).toBeTruthy();
  });
});
