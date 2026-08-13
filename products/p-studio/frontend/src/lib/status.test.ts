/**
 * Sistema de status por cor (spec § 9).
 *
 * O risco real aqui é deriva: o backend é dono das listas canônicas de etapa,
 * e o frontend mantém uma cópia para pintar. Se o backend ganhar uma etapa e
 * o mapa daqui não acompanhar, `TOM_X[etapa]` devolve `undefined`,
 * `COR_STATUS[undefined]` devolve `undefined` e a bolinha da coluna some sem
 * erro nenhum no console. Os testes de completude abaixo transformam essa
 * falha silenciosa numa falha de teste.
 *
 * As listas esperadas são transcritas do backend:
 *   app/schemas/negocios.py   → ETAPAS
 *   app/schemas/producoes.py  → ETAPAS
 *   app/schemas/financeiro.py → STATUS_LABELS
 */
import { describe, expect, it } from "vitest";

import {
  CATEGORIAS_EQUIPAMENTO,
  CATEGORIAS_SERVICO,
  CLASSES_STATUS,
  COR_STATUS,
  FORMAS_PAGAMENTO,
  LABEL_CATEGORIA_EQUIPAMENTO,
  LABEL_FORMA_PAGAMENTO,
  LABEL_PADRAO_IMOVEL,
  LABEL_STATUS_CAPTACAO,
  LABEL_TIPO_IMOVEL,
  PADROES_IMOVEL,
  TIPOS_IMOVEL,
  TOM_CAPTACAO,
  TOM_FINANCEIRO,
  TOM_NEGOCIO,
  TOM_PRODUCAO,
  type TomStatus,
} from "@/lib/status";

const TONS: TomStatus[] = [
  "lead", "scheduled", "captured", "editing",
  "delivered", "received", "late", "cancelled",
];

// Espelhos das listas canônicas do backend.
const ETAPAS_NEGOCIO = [
  "novo_lead", "orcamento", "negociacao", "aprovado", "agendamento",
  "producao", "entregue", "recebido", "arquivado",
];
const ETAPAS_PRODUCAO = [
  "agendado", "captado", "backup", "selecao",
  "edicao", "revisao", "entregue", "arquivado",
];
const STATUS_FINANCEIRO = ["a_faturar", "faturado", "recebido", "atrasado", "cancelado"];
const STATUS_CAPTACAO = ["agendado", "captado", "cancelado"];

// ── completude dos tons ───────────────────────────────────────────────────

describe("cobertura dos oito tons", () => {
  it("toda etapa do funil comercial tem tom", () => {
    expect(Object.keys(TOM_NEGOCIO).sort()).toEqual([...ETAPAS_NEGOCIO].sort());
  });

  it("toda etapa de produção tem tom", () => {
    expect(Object.keys(TOM_PRODUCAO).sort()).toEqual([...ETAPAS_PRODUCAO].sort());
  });

  it("todo status financeiro exibido tem tom, inclusive o derivado", () => {
    expect(Object.keys(TOM_FINANCEIRO).sort()).toEqual([...STATUS_FINANCEIRO].sort());
    expect(TOM_FINANCEIRO.atrasado).toBe("late");
  });

  it("todo status de captação tem tom", () => {
    expect(Object.keys(TOM_CAPTACAO).sort()).toEqual([...STATUS_CAPTACAO].sort());
  });

  it("todo tom referenciado existe em CLASSES_STATUS e COR_STATUS", () => {
    const usados = new Set<string>([
      ...Object.values(TOM_NEGOCIO),
      ...Object.values(TOM_PRODUCAO),
      ...Object.values(TOM_FINANCEIRO),
      ...Object.values(TOM_CAPTACAO),
    ]);
    for (const tom of usados) {
      expect(CLASSES_STATUS[tom as TomStatus], `classe do tom ${tom}`).toBeTruthy();
      expect(COR_STATUS[tom as TomStatus], `cor do tom ${tom}`).toBeTruthy();
    }
  });

  it("os oito tons têm classe e cor", () => {
    for (const tom of TONS) {
      expect(CLASSES_STATUS[tom]).toBeTruthy();
      expect(COR_STATUS[tom]).toBeTruthy();
    }
    expect(Object.keys(CLASSES_STATUS)).toHaveLength(8);
    expect(Object.keys(COR_STATUS)).toHaveLength(8);
  });
});

// ── forma das classes ─────────────────────────────────────────────────────

describe("classes utilitárias", () => {
  it("seguem o padrão bg/text/border do protótipo", () => {
    expect(CLASSES_STATUS.late).toBe(
      "bg-status-late/15 text-status-late border-status-late/30"
    );
  });

  it("cancelled usa text-foreground porque o cinza não teria contraste", () => {
    expect(CLASSES_STATUS.cancelled).toContain("text-foreground");
  });

  it("toda classe usa a opacidade 15 no fundo e 30 na borda", () => {
    for (const tom of TONS) {
      expect(CLASSES_STATUS[tom]).toMatch(/bg-status-[a-z]+\/15/);
      expect(CLASSES_STATUS[tom]).toMatch(/border-status-[a-z]+\/30/);
    }
  });

  it("as cores sólidas são oklch com variável CSS", () => {
    for (const tom of TONS) {
      expect(COR_STATUS[tom]).toMatch(/^oklch\(var\(--status-[a-z]+\)\)$/);
    }
  });
});

// ── semântica compartilhada entre pipelines ───────────────────────────────

describe("vocabulário visual comum aos três pipelines", () => {
  it("entregue é o mesmo tom no comercial e na produção", () => {
    expect(TOM_NEGOCIO.entregue).toBe(TOM_PRODUCAO.entregue);
    expect(TOM_NEGOCIO.entregue).toBe("delivered");
  });

  it("arquivado é neutro nos dois pipelines", () => {
    expect(TOM_NEGOCIO.arquivado).toBe("cancelled");
    expect(TOM_PRODUCAO.arquivado).toBe("cancelled");
  });

  it("recebido é verde tanto no funil quanto no financeiro", () => {
    expect(TOM_NEGOCIO.recebido).toBe("received");
    expect(TOM_FINANCEIRO.recebido).toBe("received");
  });

  it("captado é o mesmo tom na captação e na produção", () => {
    expect(TOM_CAPTACAO.captado).toBe(TOM_PRODUCAO.captado);
  });

  it("só o atrasado usa o tom de alerta", () => {
    const comAlerta = Object.entries(TOM_FINANCEIRO)
      .filter(([, tom]) => tom === "late")
      .map(([k]) => k);
    expect(comAlerta).toEqual(["atrasado"]);
  });
});

// ── dicionários de rótulo ─────────────────────────────────────────────────

describe("rótulos", () => {
  it("toda opção de forma de pagamento tem rótulo", () => {
    for (const f of FORMAS_PAGAMENTO) expect(LABEL_FORMA_PAGAMENTO[f]).toBeTruthy();
  });

  it("toda opção de tipo de imóvel tem rótulo", () => {
    for (const t of TIPOS_IMOVEL) expect(LABEL_TIPO_IMOVEL[t]).toBeTruthy();
  });

  it("todo padrão de imóvel tem rótulo", () => {
    for (const p of PADROES_IMOVEL) expect(LABEL_PADRAO_IMOVEL[p]).toBeTruthy();
  });

  it("toda categoria de equipamento tem rótulo", () => {
    for (const c of CATEGORIAS_EQUIPAMENTO) {
      expect(LABEL_CATEGORIA_EQUIPAMENTO[c]).toBeTruthy();
    }
  });

  it("todo status de captação tem rótulo", () => {
    for (const s of STATUS_CAPTACAO) expect(LABEL_STATUS_CAPTACAO[s]).toBeTruthy();
  });

  it("não há rótulo órfão sem opção correspondente", () => {
    expect(Object.keys(LABEL_FORMA_PAGAMENTO).sort()).toEqual([...FORMAS_PAGAMENTO].sort());
    expect(Object.keys(LABEL_TIPO_IMOVEL).sort()).toEqual([...TIPOS_IMOVEL].sort());
    expect(Object.keys(LABEL_CATEGORIA_EQUIPAMENTO).sort()).toEqual(
      [...CATEGORIAS_EQUIPAMENTO].sort()
    );
  });

  it("as categorias de serviço são as observadas na operação", () => {
    expect(CATEGORIAS_SERVICO).toContain("Fotografia");
    expect(CATEGORIAS_SERVICO).toContain("Aéreo");
  });
});
