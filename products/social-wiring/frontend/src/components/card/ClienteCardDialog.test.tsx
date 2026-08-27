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
    roteiros: [],
    onCriarRoteiro: vi.fn(),
    onRemoverRoteiro: vi.fn(),
    onGerarRoteiroPdf: vi.fn(),
    onPatchVisita: vi.fn(),
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

/** A derived, unticked checklist item — the ordinary shape. */
function item(key: string, label: string, over: Record<string, unknown> = {}) {
  return {
    key,
    label,
    concluido: false,
    origem: "derivado" as const,
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
    ...over,
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
  // No tab to open: Anexos lives on Geral now, under the parties' panels.
  it("shows the empty-anexos copy when there are no documentos", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentos: [] })} />);
    expect(screen.getByTestId("anexos-empty")).toBeTruthy();
  });

  it("🔴 offers a way to upload — the trigger was missing entirely", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentos: [] })} />);
    // Removing the generic `Adicionar` button took the ONLY thing that opened
    // the file input, and nothing replaced it — uploading was unreachable.
    // Icon-only now, so the assertion is on the name it still carries.
    const btn = screen.getByTestId("anexo-enviar-btn");
    expect(btn.getAttribute("aria-label")).toBe("Enviar anexo");
    // 🔴 The section owns its input, and this assertion says so BY SHAPE
    // rather than by id. It used to look up the shared
    // `card-anexo-file-input`, which was exactly what made per-person Anexos
    // sections impossible: every buyer's upload button opened the same
    // element and filed onto the titular. The input is found INSIDE the
    // section now, so a second section cannot borrow this one's.
    const secao = screen.getByTestId("anexos-section");
    expect(secao.querySelector('input[type="file"]')).toBeTruthy();
  });

  it("🔴 every file input belongs to exactly one owner", async () => {
    // The old form of this assertion counted ONE input in the document, which
    // stopped being true the moment the checklist rows grew their own uploads.
    // The RULE it protected is unchanged and is what is asserted here: no two
    // owners share an input, so no upload can land on the wrong record.
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          documentos: [],
          documentoChecklist: [
            item("rg", "RG"),
            item("cpf", "CPF"),
            item("email", "Email"),
          ],
          onUploadDocumentoChecklist: vi.fn(),
        })}
      />,
    );
    // Queried off `document` rather than the render container: the card is a
    // Radix Dialog and renders through a portal, so the container is empty.
    const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
    // anexos + rg + cpf, and NOT email — a typed item is never satisfied by a
    // file, so it must not own one.
    expect(inputs).toHaveLength(3);
    expect(screen.getByTestId("anexos-section").querySelectorAll('input[type="file"]'))
      .toHaveLength(1);
    expect(screen.getByTestId("documento-checklist-rg-row").querySelectorAll('input[type="file"]'))
      .toHaveLength(1);
    expect(
      screen.getByTestId("documento-checklist-email-row").querySelectorAll('input[type="file"]'),
    ).toHaveLength(0);
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
      onCriarChecklistExtra: vi.fn(),
      selectedTags: [{ id: "t1", nome: "Urgente", cor: "#eb5a46" }],
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

  /**
   * 🔴 Walks `document.body`, NOT the render container.
   *
   * The container form of this helper compared `-1` against `-1` for every id
   * and passed unconditionally: the card is a Radix Dialog and renders through
   * a portal, so nothing it asserts about is inside the container at all. The
   * order assertions below only became real when this was fixed.
   */
  function orderOf(screen: any, ids: string[]) {
    const all = Array.from(document.body.querySelectorAll("*"));
    const idx = ids.map((id) => all.indexOf(screen.getByTestId(id)));
    expect(idx.every((i) => i >= 0)).toBe(true);
    return idx;
  }

  it("🔴 Geral reads in the order the work happens", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...full()} />);

    // Etiquetas → contato → descrição → dados obrigatórios → extras →
    // anexos → checklists de trabalho. Collecting a document is not a separate
    // errand from working the card, so it is no longer a separate tab.
    const order = orderOf(screen, [
      "etiquetas-chips",
      "contato-resumo",
      "descricao-section",
      "documento-checklist-section",
      "checklist-extras-section",
      "anexos-section",
      "checklists-section",
    ]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("🔴 the required-data checklist stays ABOVE anexos", async () => {
    // The list of what must be COLLECTED, then what has arrived. Reading order
    // follows the work — the same rule the Documentos tab used to encode,
    // preserved after the tab was absorbed.
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...full()} />);

    const order = orderOf(screen, ["documento-checklist-section", "anexos-section"]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("agendamentos still live on their own tab", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...full()} />);
    expect(screen.queryByTestId("agendamentos-section")).toBeNull();
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

  /**
   * Geral, no navigation. The Documentos tab is gone: the required-data
   * checklist is on the open-on-mount subpage now, because reading "RG
   * pendente" on one screen and supplying it on another was the failure.
   */
  async function openDocumentos(overrides = {}) {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentoChecklist: ITENS, ...overrides })} />);
    return { fireEvent, screen };
  }

  describe("nome no documento (migration 071)", () => {
    const SUGESTAO_NOME = {
      valor: "JOAO PEREIRA DA SILVA",
      documento_id: "doc-rg",
      documento_nome: "rg.pdf",
      tipo_documento: "rg",
      confianca: "baixa",
      fonte: "ocr",
      rotulo: "NOME",
      valor_atual: null,
      substitui: false,
    };

    it("shows nothing at all when no document has been read", async () => {
      const { screen } = await openDocumentos();
      expect(screen.queryByTestId("nome-oficial-bloco")).toBeNull();
    });

    it("shows the document name once one has been read", async () => {
      const { screen } = await openDocumentos({
        nomeOficial: "JOAO PEREIRA DA SILVA",
        nomeRegistro: "Joao Pereira da Silva",
      });
      expect(screen.getByTestId("nome-oficial-valor").textContent).toContain(
        "JOAO PEREIRA DA SILVA",
      );
    });

    it("🔴 does not flag a divergence when the two agree apart from case and accents", async () => {
      const { screen } = await openDocumentos({
        nomeOficial: "JOAO PEREIRA DA SILVA",
        nomeRegistro: "João Pereira da Silva",
      });
      expect(screen.queryByTestId("nome-oficial-divergencia")).toBeNull();
    });

    it("reports a real divergence as information, not as an error to fix", async () => {
      const { screen } = await openDocumentos({
        nomeOficial: "JOAO PEREIRA DA SILVA",
        nomeRegistro: "Joao P",
      });
      const el = screen.getByTestId("nome-oficial-divergencia");
      expect(el.textContent).toContain("Joao P");
      // No action offered: both values are true, there is nothing to correct.
      expect(screen.queryByTestId("nome-oficial-corrigir")).toBeNull();
    });

    it("🔴 never displays the registration name as if it were the document's", async () => {
      const { screen } = await openDocumentos({
        nomeOficial: null,
        nomeRegistro: "Joao Pereira da Silva",
      });
      expect(screen.queryByTestId("nome-oficial-bloco")).toBeNull();
    });

    it("offers a low-confidence read for confirmation, keyed to nome_oficial", async () => {
      const onResolverSugestao = vi.fn();
      const { fireEvent, screen } = await openDocumentos({
        sugestoesExtras: { nome_oficial: SUGESTAO_NOME },
        onResolverSugestao,
      });
      fireEvent.click(
        screen.getByTestId("documento-checklist-nome_oficial-sugestao-confirmar"),
      );
      expect(onResolverSugestao).toHaveBeenCalledWith(
        "doc-rg",
        "confirmar",
        "nome_oficial",
      );
    });

    it("says what a suggestion would replace, before it is accepted", async () => {
      const { screen } = await openDocumentos({
        sugestoesExtras: {
          nome_oficial: {
            ...SUGESTAO_NOME,
            valor_atual: "JOAO P SILVA",
            substitui: true,
          },
        },
        onResolverSugestao: vi.fn(),
      });
      expect(
        screen.getByTestId("documento-checklist-nome_oficial-sugestao").textContent,
      ).toContain("JOAO P SILVA");
    });

    it("renders the name value verbatim rather than through the date formatter", async () => {
      const { screen } = await openDocumentos({
        sugestoesExtras: { nome_oficial: SUGESTAO_NOME },
        onResolverSugestao: vi.fn(),
      });
      expect(
        screen.getByTestId("documento-checklist-nome_oficial-sugestao-valor").textContent,
      ).toContain("JOAO PEREIRA DA SILVA");
    });
  });

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
    // `aria-checked`, not `.checked`: the row's checkbox is the design-token
    // one built on Radix (a `role="checkbox"` button), never the raw browser
    // input that ignored the theme.
    expect(
      screen.getByTestId("documento-checklist-data_nascimento").getAttribute("aria-checked"),
    ).toBe("false");
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
    expect(onResolverSugestao).toHaveBeenCalledWith("doc-1", "confirmar", "data_nascimento");

    fireEvent.click(
      screen.getByTestId("documento-checklist-data_nascimento-sugestao-descartar"),
    );
    expect(onResolverSugestao).toHaveBeenCalledWith("doc-1", "descartar", "data_nascimento");
  });

  it("no prompt renders when there is no suggestion", async () => {
    const { screen } = await openDocumentos({ onResolverSugestao: vi.fn() });
    expect(
      screen.queryByTestId("documento-checklist-data_nascimento-sugestao"),
    ).toBeNull();
  });

  it("🔴 IS on Geral — the Documentos tab it used to live on is gone", async () => {
    // This assertion is the exact inverse of the one it replaces. The old rule
    // ("the required-data checklist belongs to Documentos, not Geral") was
    // retired by the remodel, not broken by it: collecting a document is the
    // work, so the list of what is missing belongs on the screen the card
    // opens to. The tab it named no longer exists at all.
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ documentoChecklist: ITENS })} />);
    expect(screen.getByTestId("documento-checklist-section")).toBeTruthy();
    expect(screen.queryByTestId("card-subpage-tab-documentos")).toBeNull();
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
    for (const tab of ["cliente", "agendamentos", "roteiros", "campanha"]) {
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


describe("ClienteCardDialog — Compradores (migration 073)", () => {
  const parte = (over: Record<string, unknown> = {}) => ({
    id: "parte-1",
    atendimento_id: "atd-1",
    cliente_id: "cli-esposa",
    papel: "comprador",
    ordem: 0,
    observacao: null,
    created_at: "2026-08-24T00:00:00Z",
    cliente: {
      id: "cli-esposa",
      nome: "Maria",
      nome_completo: "Maria Mauricio",
      celular: "+5511977776666",
      email: null,
    },
    ...over,
  }) as any;

  it("offers Adicionar Comprador in the header when the handler is wired", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ onAdicionarComprador: vi.fn() })} />);
    expect(screen.getByTestId("adicionar-comprador-btn")).toBeTruthy();
  });

  it("fires onAdicionarComprador when clicked", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    const onAdicionar = vi.fn();
    render(<ClienteCardDialog {...baseProps({ onAdicionarComprador: onAdicionar })} />);
    fireEvent.click(screen.getByTestId("adicionar-comprador-btn"));
    expect(onAdicionar).toHaveBeenCalledTimes(1);
  });

  it("🔴 hides the Geral Compradores section entirely when nobody was added", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ compradores: [] })} />);
    // The ordinary card has one buyer. An empty heading on every one of them
    // would be furniture that means nothing.
    expect(screen.queryByTestId("compradores-section")).toBeNull();
  });

  it("shows the Geral Compradores section once a party exists", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ compradores: [parte()] })} />);
    expect(screen.getByTestId("compradores-section")).toBeTruthy();
    // 🔴 ONE list of parties, not two. Geral used to carry a contact-detail
    // list (`comprador-row-*`) AND the Documentos tab carried a paperwork
    // panel for the same people. Absorbing the tab put both on one screen,
    // where two lists of the same names is worse than either: the panel won,
    // because it holds the contact fields as well as the checklist.
    expect(screen.queryByTestId("comprador-row-parte-1")).toBeNull();
    expect(screen.getByTestId("pessoa-documentos-comprador-parte-1")).toBeTruthy();
  });

  it("fires onRemoverComprador with the PARTE id, not the person id", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    const onRemover = vi.fn();
    render(
      <ClienteCardDialog
        {...baseProps({ compradores: [parte()], onRemoverComprador: onRemover })}
      />,
    );
    fireEvent.click(screen.getByTestId("comprador-remover-parte-1"));
    // Detaching from this deal, never deleting the person — passing
    // `cliente_id` here would ask the API to remove the wrong thing.
    expect(onRemover).toHaveBeenCalledWith("parte-1");
  });

  it("🔴 the titular has no panel of their own — they ARE the card", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          compradores: [parte()],
          documentoChecklist: [item("rg", "RG")],
        })}
      />,
    );
    // The titular's checklist is Geral's own section, not a collapsible named
    // after them. Wrapping it would have hidden the card's own paperwork
    // behind a click on the screen the card opens to.
    expect(screen.queryByTestId("pessoa-documentos-titular")).toBeNull();
    expect(screen.getByTestId("documento-checklist-section")).toBeTruthy();
    // Everyone ELSE keeps a panel apiece.
    expect(screen.getByTestId("pessoa-documentos-comprador-parte-1")).toBeTruthy();
  });

  it("🔴 does not render a party's panel until it is expanded", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    const renderPanel = vi.fn(() => <div data-testid="painel-da-parte" />);
    render(
      <ClienteCardDialog
        {...baseProps({
          compradores: [parte()],
          renderDocumentosDePessoa: renderPanel,
        })}
      />,
    );
    // Load-bearing, not cosmetic: each panel runs its OWN checklist and
    // document queries, so mounting three collapsed parties would fire six
    // requests for panels nobody opened.
    expect(renderPanel).not.toHaveBeenCalled();
    expect(screen.queryByTestId("painel-da-parte")).toBeNull();

    fireEvent.click(screen.getByTestId("pessoa-documentos-toggle-comprador-parte-1"));
    expect(renderPanel).toHaveBeenCalledWith("cli-esposa");
    expect(screen.getByTestId("painel-da-parte")).toBeTruthy();
  });

  it("falls back to a visible placeholder when a party has no name", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          compradores: [
            parte({ cliente: { id: "x", nome: null, nome_completo: null, celular: null, email: null } }),
          ],
        })}
      />,
    );
    // A nameless collapsed row has nothing to read and nothing to click.
    expect(screen.getByText("Sem nome")).toBeTruthy();
  });
});

describe("ClienteCardDialog — icon actions", () => {
  it("keeps Editar reachable by name once it is icon-only", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ descricaoCorpo: "Lead interessado" })} />);
    // Trading the visible label for space must not trade away what the button
    // does — the accessible name still carries it.
    const btn = screen.getByTestId("descricao-editar-btn");
    expect(btn.getAttribute("aria-label")).toBe("Editar descrição");
    fireEvent.click(btn);
    expect(screen.getByTestId("descricao-textarea")).toBeTruthy();
  });
});

describe("ClienteCardDialog — Roteiros (migration 082)", () => {
  it("offers the Roteiros tab right after Agendamentos", async () => {
    // The rail's order is the reading order of the card, and the funnel the
    // user named is qualificação → visita.
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps()} />);

    const rail = screen.getByTestId("card-sidebar-nav");
    const chaves = Array.from(rail.querySelectorAll("[data-testid^='card-subpage-tab-']")).map(
      (el) => el.getAttribute("data-testid"),
    );
    expect(chaves).toContain("card-subpage-tab-roteiros");
    expect(chaves.indexOf("card-subpage-tab-roteiros")).toBe(
      chaves.indexOf("card-subpage-tab-agendamentos") + 1,
    );
  });

  it("is never disabled — you go there to ADD", async () => {
    // Same rule `agendamentos` and `documentos` follow: a tab disabled on an
    // empty card is a dead end, not a hint.
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ roteiros: [] })} />);
    expect((screen.getByTestId("card-subpage-tab-roteiros") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("shows the Roteiros section when the tab is opened", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps()} />);

    fireEvent.click(screen.getByTestId("card-subpage-tab-roteiros"));
    expect(screen.getByTestId("roteiros-section")).toBeTruthy();
    expect(screen.getByTestId("roteiro-criar-trigger")).toBeTruthy();
  });

  it("🔴 still renders a historical tipo='visita' agendamento as 'Visita'", async () => {
    // The Agendar button stopped OFFERING it; live rows still carry it, and
    // history must read as "Visita", never as the raw slug. This is the paired
    // half of `AgendamentoPopover.test.tsx`.
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          agendamentos: [
            {
              id: "ag-antigo",
              atendimento_id: "a1",
              quando: "2024-03-11T14:00:00Z",
              tipo: "visita" as const,
              nota: null,
              lembrete_minutos_antes: null,
              created_at: null,
            },
          ],
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("card-subpage-tab-agendamentos"));
    expect(screen.getByTestId("agendamento-ag-antigo").textContent).toContain("Visita");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// The 2026-08 remodel
// ───────────────────────────────────────────────────────────────────────────

describe("a linha unificada de um dado obrigatório", () => {
  const TEXTO = item("email", "Email");
  const DOC = item("rg", "RG");

  async function linha(overrides = {}) {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          documentoChecklist: [TEXTO, DOC],
          dadosPessoais: { email: "ana@example.com" },
          onSaveDadosPessoais: vi.fn(),
          onUploadDocumentoChecklist: vi.fn(),
          onRemoverDocumentoChecklist: vi.fn(),
          ...overrides,
        })}
      />,
    );
    return { fireEvent, screen };
  }

  it("🔴 the checkbox is the design-token one, never the browser default", async () => {
    const { screen } = await linha();
    const box = screen.getByTestId("documento-checklist-email");
    // A raw `<input type="checkbox">` ignores the theme entirely: it stayed a
    // hard white square on the dark card, and did not invert with it.
    expect(box.tagName).not.toBe("INPUT");
    expect(box.getAttribute("role")).toBe("checkbox");
    expect(box.className).toContain("bg-card");
    expect(box.className).toContain("border-border");
    expect(box.className).toContain("data-[state=checked]:bg-primary");
    // Softly rounded — not a hard square, not a pill.
    expect(box.className).toContain("rounded-[0.375rem]");
    // 🔴 Tokens only. A raw palette colour would not follow the theme, which
    // is the whole reason the browser default was wrong.
    expect(box.className).not.toMatch(/\b(bg|border|text)-(white|black|gray|blue|slate|zinc)-/);
  });

  it("shows the item, its current value and the tick on ONE row", async () => {
    const { screen } = await linha();
    const row = screen.getByTestId("documento-checklist-email-row");
    expect(row.textContent).toContain("Email");
    expect(row.textContent).toContain("ana@example.com");
    expect(row.querySelector('[data-testid="documento-checklist-email"]')).toBeTruthy();
  });

  it("strikes through a satisfied item, and keeps doing so", async () => {
    const { screen } = await linha({
      documentoChecklist: [{ ...TEXTO, concluido: true, derivado: true }],
    });
    expect(screen.getByTestId("documento-checklist-email-label").className).toContain(
      "line-through",
    );
  });

  it("🔴 edits a TEXT item in place and sends ONLY the edited field", async () => {
    const onSaveDadosPessoais = vi.fn();
    const { fireEvent, screen } = await linha({ onSaveDadosPessoais });

    fireEvent.click(screen.getByTestId("documento-checklist-email-editar"));
    const input = screen.getByTestId("documento-checklist-email-input");
    fireEvent.change(input, { target: { value: "nova@example.com" } });
    fireEvent.click(screen.getByTestId("documento-checklist-email-salvar"));

    // Only the edited key. Sending the whole shape from a row would let a
    // stale draft of one field overwrite a sibling somebody else just fixed.
    expect(onSaveDadosPessoais).toHaveBeenCalledWith({ email: "nova@example.com" });
  });

  it("an emptied field is saved as null, never as an empty string", async () => {
    const onSaveDadosPessoais = vi.fn();
    const { fireEvent, screen } = await linha({ onSaveDadosPessoais });
    fireEvent.click(screen.getByTestId("documento-checklist-email-editar"));
    fireEvent.change(screen.getByTestId("documento-checklist-email-input"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByTestId("documento-checklist-email-salvar"));
    // "never filled" and "filled with nothing" must not become the same value.
    expect(onSaveDadosPessoais).toHaveBeenCalledWith({ email: null });
  });

  it("cancelling an edit writes nothing", async () => {
    const onSaveDadosPessoais = vi.fn();
    const { fireEvent, screen } = await linha({ onSaveDadosPessoais });
    fireEvent.click(screen.getByTestId("documento-checklist-email-editar"));
    fireEvent.click(screen.getByTestId("documento-checklist-email-cancelar"));
    expect(onSaveDadosPessoais).not.toHaveBeenCalled();
    expect(screen.queryByTestId("documento-checklist-email-input")).toBeNull();
  });

  it("🔴 a TEXT item offers no upload and no trash at all", async () => {
    const { screen } = await linha();
    expect(screen.queryByTestId("documento-checklist-email-upload")).toBeNull();
    expect(screen.queryByTestId("documento-checklist-email-descartar-arquivo")).toBeNull();
  });

  it("a DOCUMENT item offers an upload and no inline editor", async () => {
    const { screen } = await linha();
    expect(screen.getByTestId("documento-checklist-rg-upload")).toBeTruthy();
    // There is nothing to type: an RG is satisfied by a file.
    expect(screen.queryByTestId("documento-checklist-rg-editar")).toBeNull();
  });

  it("🔴 the trash appears only once a file exists, and DISCARDS THE FILE", async () => {
    const onRemoverDocumentoChecklist = vi.fn();
    const comArquivo = {
      ...DOC,
      concluido: true,
      derivado: true,
      documento: {
        id: "doc-rg",
        nome_original: "rg.pdf",
        mime_type: "application/pdf",
        tamanho_bytes: 2048,
        created_at: "2026-08-24T00:00:00Z",
      },
    };

    const semArquivo = await linha();
    expect(semArquivo.screen.queryByTestId("documento-checklist-rg-descartar-arquivo")).toBeNull();
    (await import("@testing-library/react")).cleanup();

    const { fireEvent, screen } = await linha({
      documentoChecklist: [comArquivo],
      onRemoverDocumentoChecklist,
    });
    expect(screen.getByTestId("documento-checklist-rg-row").textContent).toContain("rg.pdf");
    fireEvent.click(screen.getByTestId("documento-checklist-rg-descartar-arquivo"));
    // The card STAYS; the document is deleted for a fresh upload. A mandatory
    // row is server-defined — there is no such thing as deleting "RG" from it.
    expect(onRemoverDocumentoChecklist).toHaveBeenCalledWith("doc-rg", comArquivo);
    expect(screen.getByTestId("documento-checklist-rg-row")).toBeTruthy();
  });

  it("🔴 renders without a trash when the backend has not shipped `documento` yet", async () => {
    // The field is optional on purpose: this branch and the backend slice that
    // populates it were built in parallel, and neither may assume the other.
    const { screen } = await linha({ documentoChecklist: [DOC] });
    expect(screen.getByTestId("documento-checklist-rg-row")).toBeTruthy();
    expect(screen.queryByTestId("documento-checklist-rg-descartar-arquivo")).toBeNull();
  });

  it("keeps the manual badge and the withdraw affordance on the row", async () => {
    const onToggle = vi.fn();
    const { fireEvent, screen } = await linha({
      documentoChecklist: [{ ...TEXTO, concluido: true, origem: "manual" }],
      onToggleDocumentoChecklist: onToggle,
    });
    // A tick that disagrees with the record must never read as evidence the
    // data is there — the one rule the derivation exists to protect.
    expect(
      screen.getByTestId("documento-checklist-email-manual").getAttribute("title"),
    ).toContain("pendente");
    fireEvent.click(screen.getByTestId("documento-checklist-email-limpar"));
    expect(onToggle).toHaveBeenCalledWith("email", null);
  });
});

describe("a listagem de dados extras", () => {
  const extra = (over: Record<string, unknown> = {}) => ({
    id: "ex-1",
    label: "Certidão de casamento",
    tipo: "texto" as const,
    valor_texto: null,
    documento: null,
    concluido: false,
    ordem: 0,
    ...over,
  });

  async function lista(overrides = {}) {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          onCriarChecklistExtra: vi.fn(),
          onRenomearChecklistExtra: vi.fn(),
          onSalvarTextoChecklistExtra: vi.fn(),
          onRemoverChecklistExtra: vi.fn(),
          onUploadChecklistExtra: vi.fn(),
          onRemoverDocumentoChecklistExtra: vi.fn(),
          ...overrides,
        })}
      />,
    );
    return { fireEvent, screen };
  }

  it("sits BELOW the mandatory list — the ad-hoc rows come after the owed ones", async () => {
    const { screen } = await lista({ documentoChecklist: [item("rg", "RG")] });
    const all = Array.from(document.body.querySelectorAll("*"));
    expect(all.indexOf(screen.getByTestId("checklist-extras-section"))).toBeGreaterThan(
      all.indexOf(screen.getByTestId("documento-checklist-section")),
    );
  });

  it("says so when there is nothing yet", async () => {
    const { screen } = await lista({ checklistExtras: [] });
    expect(screen.getByTestId("checklist-extras-empty")).toBeTruthy();
  });

  it("shows a skeleton while loading, never the empty copy over data in flight", async () => {
    const { screen } = await lista({ checklistExtras: [], checklistExtrasLoading: true });
    expect(screen.getByTestId("checklist-extras-loading")).toBeTruthy();
    expect(screen.queryByTestId("checklist-extras-empty")).toBeNull();
  });

  it("surfaces a read failure instead of rendering as empty", async () => {
    const { screen } = await lista({
      checklistExtras: [],
      checklistExtrasError: "Não foi possível carregar os dados extras.",
    });
    expect(screen.getByTestId("checklist-extras-erro")).toBeTruthy();
    expect(screen.queryByTestId("checklist-extras-empty")).toBeNull();
  });

  it("🔴 offers the two kinds as two choices, and creates the one that was picked", async () => {
    const onCriar = vi.fn();
    const { fireEvent, screen } = await lista({ onCriarChecklistExtra: onCriar });

    expect(screen.getByTestId("checklist-extras-add-texto").getAttribute("aria-label")).toBe(
      "Adicionar dado de texto",
    );
    expect(screen.getByTestId("checklist-extras-add-arquivo").getAttribute("aria-label")).toBe(
      "Adicionar dado de arquivo",
    );

    fireEvent.click(screen.getByTestId("checklist-extras-add-arquivo"));
    fireEvent.change(screen.getByTestId("checklist-extras-novo-label"), {
      target: { value: "Comprovante de renda" },
    });
    fireEvent.click(screen.getByTestId("checklist-extras-novo-salvar"));

    // The KIND is a property of the row, chosen once, so the row can render
    // the right affordance forever after.
    expect(onCriar).toHaveBeenCalledWith({
      label: "Comprovante de renda",
      tipo: "arquivo",
    });
  });

  it("refuses to create a nameless row", async () => {
    const onCriar = vi.fn();
    const { fireEvent, screen } = await lista({ onCriarChecklistExtra: onCriar });
    fireEvent.click(screen.getByTestId("checklist-extras-add-texto"));
    fireEvent.click(screen.getByTestId("checklist-extras-novo-salvar"));
    expect(onCriar).not.toHaveBeenCalled();
  });

  it("renames a row", async () => {
    const onRenomear = vi.fn();
    const { fireEvent, screen } = await lista({
      checklistExtras: [extra()],
      onRenomearChecklistExtra: onRenomear,
    });
    fireEvent.click(screen.getByTestId("checklist-extras-ex-1-renomear"));
    fireEvent.change(screen.getByTestId("checklist-extras-ex-1-label-input"), {
      target: { value: "Certidão" },
    });
    fireEvent.click(screen.getByTestId("checklist-extras-ex-1-salvar"));
    expect(onRenomear).toHaveBeenCalledWith("ex-1", "Certidão");
  });

  it("edits a TEXT row's value in place", async () => {
    const onSalvarTexto = vi.fn();
    const { fireEvent, screen } = await lista({
      checklistExtras: [extra()],
      onSalvarTextoChecklistExtra: onSalvarTexto,
    });
    fireEvent.click(screen.getByTestId("checklist-extras-ex-1-editar"));
    fireEvent.change(screen.getByTestId("checklist-extras-ex-1-valor-input"), {
      target: { value: "cartório 3" },
    });
    fireEvent.click(screen.getByTestId("checklist-extras-ex-1-salvar"));
    expect(onSalvarTexto).toHaveBeenCalledWith("ex-1", "cartório 3");
  });

  it("a FILE row uploads instead of typing, and owns its own input", async () => {
    const { screen } = await lista({
      checklistExtras: [extra({ tipo: "arquivo" })],
    });
    expect(screen.getByTestId("checklist-extras-ex-1-upload")).toBeTruthy();
    expect(screen.queryByTestId("checklist-extras-ex-1-editar")).toBeNull();
    expect(
      screen.getByTestId("checklist-extras-ex-1-row").querySelectorAll('input[type="file"]'),
    ).toHaveLength(1);
  });

  it("🔴 discarding the FILE and removing the ROW are two different buttons", async () => {
    const onRemover = vi.fn();
    const onRemoverDocumento = vi.fn();
    const { fireEvent, screen } = await lista({
      checklistExtras: [
        extra({
          tipo: "arquivo",
          concluido: true,
          documento: {
            id: "doc-9",
            nome_original: "renda.pdf",
            mime_type: "application/pdf",
            tamanho_bytes: 4096,
            created_at: "2026-08-24T00:00:00Z",
          },
        }),
      ],
      onRemoverChecklistExtra: onRemover,
      onRemoverDocumentoChecklistExtra: onRemoverDocumento,
    });

    fireEvent.click(screen.getByTestId("checklist-extras-ex-1-descartar-arquivo"));
    expect(onRemoverDocumento).toHaveBeenCalledWith("ex-1");
    expect(onRemover).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("checklist-extras-ex-1-remover"));
    expect(onRemover).toHaveBeenCalledWith("ex-1");
  });

  it("🔴 these rows ARE deletable — unlike the mandatory ones", async () => {
    const { screen } = await lista({
      checklistExtras: [extra()],
      documentoChecklist: [item("rg", "RG")],
    });
    expect(screen.getByTestId("checklist-extras-ex-1-remover")).toBeTruthy();
    // A mandatory row is server-defined; there is no button that removes it.
    expect(screen.queryByTestId("documento-checklist-rg-remover")).toBeNull();
  });

  it("🔴 the extras tick is a readout, not a control that silently fails", async () => {
    // The PATCH contract carries `label`, `valor_texto` and `ordem` — there is
    // no field for `concluido`, so it is derived. A checkbox that moved and
    // then did not persist would be a lying state.
    const { screen } = await lista({ checklistExtras: [extra({ concluido: true })] });
    const box = screen.getByTestId("checklist-extras-ex-1");
    expect(box.getAttribute("aria-checked")).toBe("true");
    expect(box.hasAttribute("disabled")).toBe(true);
    expect(box.getAttribute("title")).toContain("automaticamente");
  });
});

describe("a barra lateral como hover rail", () => {
  async function rail() {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps()} />);
    return screen;
  }

  it("🔴 expands as an OVERLAY — the reserved column never changes width", async () => {
    const screen = await rail();
    const trilho = screen.getByTestId("card-sidebar-rail");
    const nav = screen.getByTestId("card-sidebar-nav");
    // The COLUMN keeps the collapsed width; the nav floats above it. A width
    // transition on the column would reflow the pane under the pointer, moving
    // the thing the user is reading on every accidental hover.
    expect(trilho.className).toContain("md:w-[3.25rem]");
    expect(trilho.className).toContain("relative");
    expect(nav.className).toContain("md:absolute");
    expect(nav.className).toContain("md:w-[3.25rem]");
    expect(nav.className).toContain("md:hover:w-56");
  });

  it("🔴 focus-within expands it too — a hover-only rail is unreachable", async () => {
    const screen = await rail();
    const nav = screen.getByTestId("card-sidebar-nav");
    expect(nav.className).toContain("md:focus-within:w-56");
    expect(
      screen.getByTestId("card-subpage-label-geral").className,
    ).toContain("md:group-focus-within:w-auto");
  });

  it("rests icon-only: the caption is in the DOM, its BOX is collapsed", async () => {
    const screen = await rail();
    const label = screen.getByTestId("card-subpage-label-cliente");
    // Present, so revealing it is a transition rather than a mount — and so
    // it never leaves the accessibility tree.
    expect(label.textContent).toBe("Dados do cliente");
    expect(label.className).toContain("md:w-0");
    expect(label.className).toContain("md:opacity-0");
    expect(label.className).toContain("md:group-hover:w-auto");
  });

  it("🔴 every rail button keeps an accessible name while collapsed", async () => {
    const screen = await rail();
    expect(screen.getByTestId("card-subpage-tab-geral").getAttribute("aria-label")).toBe(
      "Geral",
    );
    expect(screen.getByTestId("card-subpage-tab-campanha").getAttribute("aria-label")).toBe(
      "Campanha e imóvel",
    );
  });

  it("keeps the mobile horizontal strip — it is never `hidden md:flex`", async () => {
    const screen = await rail();
    // Below `md` the dialog is one column; hiding the rail would make the
    // cliente/campanha subpages unreachable on a phone, not merely restyled.
    const nav = screen.getByTestId("card-sidebar-nav");
    // Token-wise, not substring-wise: `md:overflow-x-hidden` is a legitimate
    // class that CONTAINS "hidden" while hiding nothing.
    const classes = nav.className.split(/\s+/);
    expect(classes).not.toContain("hidden");
    expect(classes).not.toContain("md:flex");
    expect(classes).toContain("overflow-x-auto");
  });

  it("keeps the disabled-tab behaviour for empty record subpages", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ atendimentos: [] })} />);
    expect((screen.getByTestId("card-subpage-tab-cliente") as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByTestId("card-subpage-tab-geral") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("🔴 no longer offers a Documentos tab", async () => {
    const screen = await rail();
    expect(screen.queryByTestId("card-subpage-tab-documentos")).toBeNull();
    // Financiamento inherits the slot it used to sit above, and keeps it.
    const chaves = Array.from(
      screen.getByTestId("card-sidebar-nav").querySelectorAll("[data-testid^='card-subpage-tab-']"),
    ).map((el) => el.getAttribute("data-testid"));
    expect(chaves.indexOf("card-subpage-tab-financiamento")).toBe(
      chaves.indexOf("card-subpage-tab-roteiros") + 1,
    );
  });
});

describe("legendas nos botões (ícone + tooltip)", () => {
  it("🔴 every icon-only action still says what it does, by name", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          onAdicionarComprador: vi.fn(),
          descricaoCorpo: "Lead interessado",
          documentos: [],
        })}
      />,
    );
    // A tooltip is NOT an accessible name — it is invisible to a screen reader
    // and to a keyboard. Each of these carries the caption on `aria-label` too.
    const esperado: [string, string][] = [
      ["adicionar-comprador-btn", "Adicionar Comprador"],
      ["anexo-enviar-btn", "Enviar anexo"],
      ["descricao-editar-btn", "Editar descrição"],
      ["etiquetas-trigger", "Etiquetas"],
      ["agendamento-trigger", "Agendar"],
      ["checklist-trigger", "Checklist"],
      ["membros-trigger", "Membros"],
    ];
    for (const [testId, caption] of esperado) {
      expect(screen.getByTestId(testId).getAttribute("aria-label")).toBe(caption);
      expect(screen.getByTestId(testId).textContent).toBe("");
    }
  });

  it("🔴 the extracted-value pair KEPT its words", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          documentoChecklist: [
            item("data_nascimento", "Data de Nascimento", {
              sugestao: {
                valor: "1980-05-12",
                documento_id: "doc-1",
                documento_nome: "rg.pdf",
                tipo_documento: "rg",
                confianca: "baixa",
                fonte: "ocr",
                rotulo: "DATA DE NASCIMENTO",
              },
            }),
          ],
          onResolverSugestao: vi.fn(),
        })}
      />,
    );
    // Two bare glyphs here would be confirmed by reflex, which is the exact
    // failure the low-confidence path exists to prevent. Anything that looks
    // already-applied gets accepted without being read.
    expect(
      screen.getByTestId("documento-checklist-data_nascimento-sugestao-confirmar").textContent,
    ).toBe("Confirmar");
    expect(
      screen.getByTestId("documento-checklist-data_nascimento-sugestao-descartar").textContent,
    ).toBe("Descartar");
  });

  it("🔴 the comment composer KEPT its word too", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps()} />);
    fireEvent.change(screen.getByTestId("comentario-textarea"), {
      target: { value: "meia frase" },
    });
    // The one control whose misfire is public: a half-written note lands on
    // the client's activity feed for the whole team to read.
    expect(screen.getByTestId("comentario-enviar-btn").textContent).toBe("Comentar");
  });
});

describe("a aba Dados do cliente ganhou um editor", () => {
  const COM_REGISTRO = {
    atendimentos: [
      {
        id: "a1",
        titulo: "Ana",
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
        },
      },
    ],
  } as any;

  it("🔴 is no longer read-only", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({ ...COM_REGISTRO, onSaveDadosPessoais: vi.fn() })}
      />,
    );
    fireEvent.click(screen.getByTestId("card-subpage-tab-cliente"));
    // It showed what the record holds and offered nowhere to change it, so
    // correcting a mistyped email meant leaving the card.
    expect(screen.getByTestId("dados-pessoais-editar-btn").getAttribute("aria-label")).toBe(
      "Editar dados",
    );
    expect(screen.getByTestId("card-subpage-cliente")).toBeTruthy();
  });

  it("🔴 reuses the SAME form and the SAME write path", async () => {
    const onSaveDadosPessoais = vi.fn();
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          ...COM_REGISTRO,
          dadosPessoais: { email: "ana@example.com" },
          onSaveDadosPessoais,
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("card-subpage-tab-cliente"));
    fireEvent.click(screen.getByTestId("dados-pessoais-editar-btn"));
    fireEvent.change(screen.getByTestId("dados-pessoais-nome"), {
      target: { value: "Ana Souza" },
    });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    // A second editor for one set of columns would be two ways to write the
    // same value, and one of them would be wrong first.
    expect(onSaveDadosPessoais).toHaveBeenCalledWith(
      expect.objectContaining({ nome_completo: "Ana Souza" }),
    );
  });

  it("offers no editor when the container wired no save path", async () => {
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ ...COM_REGISTRO })} />);
    fireEvent.click(screen.getByTestId("card-subpage-tab-cliente"));
    expect(screen.queryByTestId("dados-pessoais-editar-btn")).toBeNull();
  });
});

describe("o resumo de contato no topo do Geral", () => {
  it("shows nome · celular · email as one-line rows", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ClienteCardDialog
        {...baseProps({
          dadosPessoais: {
            nome_completo: "Ana Souza",
            celular: "+5511999998888",
            email: "ana@example.com",
          },
        })}
      />,
    );
    const resumo = screen.getByTestId("contato-resumo");
    expect(resumo.textContent).toContain("Ana Souza");
    expect(resumo.textContent).toContain("+5511999998888");
    expect(resumo.textContent).toContain("ana@example.com");
  });

  it("an absent value says so rather than rendering a blank cell", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<ClienteCardDialog {...baseProps({ dadosPessoais: {} })} />);
    // A blank beside a label reads as a rendering bug, not as missing data.
    expect(screen.getByTestId("contato-celular").textContent).toContain("—");
  });
});
