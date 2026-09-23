/**
 * DocumentoChecklistSection — the mandatory "Dados obrigatórios" list.
 *
 * 🔴 THE LOAD-BEARING TEST is "keeps every row mounted during a background
 * refetch": a screen recording caught all 8 rows vanishing behind a single
 * skeleton bar on every unrelated card edit (clearing the Email field, for
 * instance) because the caller correctly gated `loading` on
 * `isPending || isFetching` (never `isLoading` — v5's is false during a
 * background refetch) but this component then treated that ONE boolean as
 * "hide everything". A mocked query object that never transitions through a
 * background refetch — `loading` always paired with an empty `items` array —
 * is exactly why that shape was invisible to any existing suite; this file's
 * first describe block simulates the transition explicitly.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import {
  DocumentoChecklistSection,
  type DocumentoChecklistSectionProps,
} from "./DocumentoChecklistSection";
import type { DocumentoChecklistItem } from "@/types/cardHub";

/** A derived, unticked checklist item — the ordinary shape. */
function item(key: string, label: string, over: Partial<DocumentoChecklistItem> = {}): DocumentoChecklistItem {
  return {
    key,
    label,
    concluido: false,
    origem: "derivado",
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
    ...over,
  };
}

const ITENS: DocumentoChecklistItem[] = [
  item("rg", "RG"),
  item("cpf", "CPF"),
  item("email", "E-mail", { concluido: true, derivado: true }),
];

function baseProps(over: Partial<DocumentoChecklistSectionProps> = {}): DocumentoChecklistSectionProps {
  return {
    items: [],
    onToggle: vi.fn(),
    ...over,
  };
}

async function renderSection(props: DocumentoChecklistSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(DocumentoChecklistSection, props));
}

describe("DocumentoChecklistSection — background refetch never unmounts rows", () => {
  it("🔴 keeps every row mounted while `loading` is true AND `items` already has data", async () => {
    // This is exactly what the OLD caller sent mid-refetch: `documentoChecklist
    // .isPending || documentoChecklist.isFetching` stays true through the
    // whole background fetch even though `documentoChecklist.data.items` is
    // still the last-good array. Before the fix this rendered ONLY the
    // skeleton bar, dropping all 8 (here 3) rows.
    const { getByTestId, queryByTestId } = await renderSection(
      baseProps({ items: ITENS, loading: true }),
    );
    expect(getByTestId(`documento-checklist-section`)).toBeTruthy();
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-cpf-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-email-row")).toBeTruthy();
    expect(queryByTestId("documento-checklist-loading")).toBeNull();
  });

  it("shows the skeleton only when there is genuinely nothing to render yet", async () => {
    const { getByTestId, queryByTestId } = await renderSection(
      baseProps({ items: [], loading: true }),
    );
    expect(getByTestId("documento-checklist-loading")).toBeTruthy();
    expect(queryByTestId("documento-checklist-section")).toBeNull();
  });

  it("never renders the empty state over rows that exist mid-refetch", async () => {
    // The `lying-loading-state` class this whole file guards against: an
    // empty/skeleton branch must never outrank live data.
    const { queryByTestId, getByTestId } = await renderSection(
      baseProps({ items: ITENS, loading: true }),
    );
    expect(queryByTestId("documento-checklist-loading")).toBeNull();
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
  });

  it("shows the subtle refreshing indicator beside the count, not over the rows", async () => {
    const { getByTestId } = await renderSection(
      baseProps({ items: ITENS, refreshing: true }),
    );
    expect(getByTestId("documento-checklist-refreshing")).toBeTruthy();
    // The count itself stays an exact match — the indicator lives beside it,
    // never inside the text a test (or an operator's eye) reads as the tally.
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
  });

  it("does not show the refreshing indicator when nothing is in flight", async () => {
    const { queryByTestId } = await renderSection(baseProps({ items: ITENS }));
    expect(queryByTestId("documento-checklist-refreshing")).toBeNull();
  });
});

describe("DocumentoChecklistSection — progress + rows", () => {
  it("renders one row per item and counts completion", async () => {
    const { getByTestId } = await renderSection(baseProps({ items: ITENS }));
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-cpf-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-email-row")).toBeTruthy();
  });

  it("says so when the server sends an empty list (not loading)", async () => {
    const { getByTestId } = await renderSection(baseProps({ items: [] }));
    expect(getByTestId("documento-checklist-empty")).toBeTruthy();
  });
});

describe("o item único de identidade (RG e CPF, 2026-09-23)", () => {
  const IDENTIDADE = item("identidade", "Documento de identidade (RG e CPF)", {
    documento: null,
    documentos: [
      { tipo_documento: "cin", rotulo: "CIN", upload: true, documento: null },
      { tipo_documento: "cnh", rotulo: "CNH", upload: true, documento: null },
    ],
    faltando: ["cpf"],
    faltando_rotulos: ["CPF"],
    dica: "Basta um dos dois (CIN ou CNH), desde que dele se leiam o RG e o CPF.",
  });

  it("🔴 renders as ONE row with a CIN and a CNH slot, naming the missing number", async () => {
    const { getByTestId, getAllByTestId } = await renderSection(
      baseProps({ items: [IDENTIDADE], onUploadDocumento: vi.fn() }),
    );
    expect(getAllByTestId(/-row$/)).toHaveLength(1);
    expect(getByTestId("documento-checklist-identidade-cin-upload")).toBeTruthy();
    expect(getByTestId("documento-checklist-identidade-cnh-upload")).toBeTruthy();
    expect(getByTestId("documento-checklist-identidade-faltando").textContent).toContain("CPF");
  });

  it("🔴 the RG / CPF readings are offered beside the checklist (sugestoes_extras)", async () => {
    const sugestao = {
      valor: "52.179.965-X",
      documento_id: "doc-1",
      documento_nome: "cnh.pdf",
      tipo_documento: "cnh",
      confianca: "baixa",
      fonte: "ocr",
      rotulo: "DOC. IDENTIDADE",
      valor_atual: null,
      aviso: null,
    };
    const onResolverSugestao = vi.fn();
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await renderSection(
      baseProps({
        items: [IDENTIDADE],
        sugestoesExtras: { rg: sugestao, cpf: { ...sugestao, valor: "412.954.238-98" } },
        onResolverSugestao,
      }),
    );
    expect(getByTestId("documento-checklist-rg-sugestao")).toBeTruthy();
    rtl.fireEvent.click(getByTestId("documento-checklist-cpf-sugestao-confirmar"));
    expect(onResolverSugestao).toHaveBeenCalledWith("doc-1", "confirmar", "cpf");
  });
});

describe("sugestão de RG idêntico ao CPF (migration 110)", () => {
  it("🔴 mostra o aviso quando a sugestão de RG carrega aviso=rg_igual_cpf", async () => {
    const rgComAviso = item("rg", "RG", {
      sugestao: {
        valor: "41295423898",
        documento_id: "doc-1",
        documento_nome: "rg.pdf",
        tipo_documento: "rg",
        confianca: "alta",
        fonte: "ocr",
        rotulo: "RG",
        valor_atual: null,
        aviso: "rg_igual_cpf",
      },
    });
    const { getByTestId } = await renderSection(
      baseProps({ items: [rgComAviso], onResolverSugestao: vi.fn() }),
    );
    const aviso = getByTestId("documento-checklist-rg-sugestao-aviso-rg-cpf");
    // Informational — confirming succeeds (the server refuses RG == CPF
    // nowhere, a CIN prints the CPF as its identity number).
    expect(aviso.className).not.toContain("text-destructive");
    expect(aviso.textContent).not.toContain("vai falhar");
  });

  it("não mostra o aviso para uma sugestão comum de RG", async () => {
    const rgSemAviso = item("rg", "RG", {
      sugestao: {
        valor: "12345678900",
        documento_id: "doc-1",
        documento_nome: "rg.pdf",
        tipo_documento: "rg",
        confianca: "alta",
        fonte: "ocr",
        rotulo: "RG",
        valor_atual: null,
        aviso: null,
      },
    });
    const { queryByTestId } = await renderSection(
      baseProps({ items: [rgSemAviso], onResolverSugestao: vi.fn() }),
    );
    expect(queryByTestId("documento-checklist-rg-sugestao-aviso-rg-cpf")).toBeNull();
  });
});

describe("sugestões de estado civil / regime de bens (migration 110)", () => {
  it("oferece a sugestão de estado civil com rótulo em pt-BR", async () => {
    const { getByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        sugestoesExtras: {
          estado_civil: {
            valor: "casado",
            documento_id: "doc-2",
            documento_nome: "certidao.pdf",
            tipo_documento: "certidao_casamento",
            confianca: "alta",
            fonte: "texto",
            rotulo: "ESTADO CIVIL",
            valor_atual: null,
          },
        },
      }),
    );
    expect(
      getByTestId("documento-checklist-estado_civil-sugestao-valor").textContent,
    ).toContain("Casado(a)");
  });

  it("oferece a sugestão de regime de bens com rótulo em pt-BR — quando o registro já lê casado (this slice)", async () => {
    const { getByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        // 🔴 GATED (this slice): a regime de bens sugestão só faz sentido para
        // quem o registro CONFIRMADO já lê como casado — ver o describe
        // "sugestões de regime de bens / data do casamento são condicionadas
        // ao casamento" abaixo para o lado oposto.
        valores: { estado_civil: "casado" },
        sugestoesExtras: {
          regime_bens: {
            valor: "comunhao_parcial",
            documento_id: "doc-2",
            documento_nome: "certidao.pdf",
            tipo_documento: "certidao_casamento",
            confianca: "alta",
            fonte: "texto",
            rotulo: "comunhão parcial",
            valor_atual: null,
          },
        },
      }),
    );
    expect(
      getByTestId("documento-checklist-regime_bens-sugestao-valor").textContent,
    ).toContain("Comunhão parcial de bens");
  });

  it("não oferece nada quando não há sugestões extras de qualificação", async () => {
    const { queryByTestId } = await renderSection(
      baseProps({ items: [], onResolverSugestao: vi.fn() }),
    );
    expect(queryByTestId("documento-checklist-estado_civil-sugestao-valor")).toBeNull();
    expect(queryByTestId("documento-checklist-regime_bens-sugestao-valor")).toBeNull();
  });

  it("oferece a sugestão de nacionalidade com o valor capitalizado (migration 146)", async () => {
    const { getByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        sugestoesExtras: {
          nacionalidade: {
            valor: "brasileiro",
            documento_id: "doc-3",
            documento_nome: "cnh.pdf",
            tipo_documento: "cnh",
            confianca: "alta",
            fonte: "texto",
            rotulo: "NACIONALIDADE",
            valor_atual: null,
          },
        },
      }),
    );
    expect(
      getByTestId("documento-checklist-nacionalidade-sugestao-valor").textContent,
    ).toContain("Brasileiro");
  });

  it("oferece a sugestão de data do casamento formatada em pt-BR (migration 117 — encontrado ao lado da 145) — quando já casado (this slice)", async () => {
    const { getByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        valores: { estado_civil: "casado" },
        sugestoesExtras: {
          data_casamento: {
            valor: "2010-03-12",
            documento_id: "doc-4",
            documento_nome: "certidao.pdf",
            tipo_documento: "certidao_casamento",
            confianca: "alta",
            fonte: "texto",
            rotulo: "CASARAM-SE EM",
            valor_atual: null,
          },
        },
      }),
    );
    expect(
      getByTestId("documento-checklist-data_casamento-sugestao-valor").textContent,
    ).toContain("12/03/2010");
  });
});

describe("🔴 sugestões de regime de bens / data do casamento são condicionadas ao casamento (this slice)", () => {
  const regimeBensSugestao = {
    valor: "comunhao_parcial",
    documento_id: "doc-2",
    documento_nome: "certidao.pdf",
    tipo_documento: "certidao_casamento",
    confianca: "alta",
    fonte: "texto",
    rotulo: "comunhão parcial",
    valor_atual: null,
  } as const;

  const dataCasamentoSugestao = {
    valor: "2010-03-12",
    documento_id: "doc-4",
    documento_nome: "certidao.pdf",
    tipo_documento: "certidao_casamento",
    confianca: "alta",
    fonte: "texto",
    rotulo: "CASARAM-SE EM",
    valor_atual: null,
  } as const;

  it("🔴 suprime AMBAS quando o registro não lê casado — nada é perguntado a quem é solteiro", async () => {
    const { queryByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        valores: { estado_civil: "solteiro" },
        sugestoesExtras: {
          regime_bens: regimeBensSugestao,
          data_casamento: dataCasamentoSugestao,
        },
      }),
    );
    expect(queryByTestId("documento-checklist-regime_bens-sugestao-valor")).toBeNull();
    expect(queryByTestId("documento-checklist-data_casamento-sugestao-valor")).toBeNull();
  });

  it("suprime AMBAS quando ainda não há estado_civil confirmado no registro", async () => {
    const { queryByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        sugestoesExtras: {
          regime_bens: regimeBensSugestao,
          data_casamento: dataCasamentoSugestao,
        },
      }),
    );
    expect(queryByTestId("documento-checklist-regime_bens-sugestao-valor")).toBeNull();
    expect(queryByTestId("documento-checklist-data_casamento-sugestao-valor")).toBeNull();
  });

  it("mostra regime de bens mas NÃO data de casamento para união estável (sem casamento a datar)", async () => {
    const { getByTestId, queryByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        valores: { estado_civil: "uniao_estavel" },
        sugestoesExtras: {
          regime_bens: regimeBensSugestao,
          data_casamento: dataCasamentoSugestao,
        },
      }),
    );
    expect(getByTestId("documento-checklist-regime_bens-sugestao-valor")).toBeTruthy();
    expect(queryByTestId("documento-checklist-data_casamento-sugestao-valor")).toBeNull();
  });

  it("mostra AMBAS quando o registro já lê casado", async () => {
    const { getByTestId } = await renderSection(
      baseProps({
        items: [],
        onResolverSugestao: vi.fn(),
        valores: { estado_civil: "Casado(a)" },
        sugestoesExtras: {
          regime_bens: regimeBensSugestao,
          data_casamento: dataCasamentoSugestao,
        },
      }),
    );
    expect(getByTestId("documento-checklist-regime_bens-sugestao-valor")).toBeTruthy();
    expect(getByTestId("documento-checklist-data_casamento-sugestao-valor")).toBeTruthy();
  });
});

describe("hideHeader — quando um bloco dobrável já nomeia a seção", () => {
  it("drops the title and the progress count, keeping the rows and the bar", async () => {
    // The card wraps this in a collapsible that carries BOTH the words and
    // the count in its own header (so the count stays legible while closed).
    // Rendering them again one line below would be the same heading twice.
    const { getByTestId, queryByTestId, queryByText } = await renderSection(
      baseProps({ items: ITENS, hideHeader: true }),
    );
    expect(queryByText("Dados obrigatórios")).toBeNull();
    expect(queryByTestId("documento-checklist-progresso")).toBeNull();
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
  });

  it("keeps its own header by default — PessoaDocumentosPanel renders it flat", async () => {
    const { getByTestId, getByText } = await renderSection(baseProps({ items: ITENS }));
    expect(getByText("Dados obrigatórios")).toBeTruthy();
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
  });
});
