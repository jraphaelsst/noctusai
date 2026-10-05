import { describe, expect, it } from "vitest";

import { destinoDoBloqueio, destinoEfetivo } from "./destinoDoContrato";
import type { GeracaoDestino } from "./GeradorContratoSection";

const card = (ancora: string, alvo: string | null = null): GeracaoDestino => ({
  tela: `card_${ancora}`,
  rota: "/clientes",
  ancora,
  alvo,
  ids: { cliente_id: "c1" },
});
const matriculas: GeracaoDestino = {
  tela: "matriculas",
  rota: "/matriculas",
  ancora: null,
  alvo: null,
  ids: { cliente_id: "c1", contrato_id: "k1", imovel_codigo: "AP1" },
};

describe("destinoEfetivo", () => {
  it.each([
    ["negociacao.valor_negociado", "negociacao", "valor-negociado"],
    ["negociacao.parcelas", "negociacao", "negest-parcelas"],
    ["negociacao.parcela_sinal", "negociacao", "negest-parcelas"],
    ["negociacao.parcela.p1.forma_pagamento", "negociacao", "negest-parcelas"],
    ["negociacao.parcela.p1.divisao.2.valor", "negociacao", "negest-parcelas"],
    ["negociacao.posse_prazo_dias", "negociacao", "termos-posse-prazo"],
    ["negociacao.posse_marco", "negociacao", "termos-posse-marco"],
    ["negociacao.onus_quitacao", "negociacao", "termos-onus-quitacao"],
    ["negociacao.onus_prazo_dias", "negociacao", "termos-onus-prazo"],
    ["negociacao.onus_baixa_protocolo_em", "negociacao", "termos-onus-baixa-protocolo"],
    ["financiamento.situacao", "financiamento", "financiamento-situacao"],
    ["financiamento", "financiamento", "financiamento-situacao"],
  ])("%s lands on %s › #%s", (campo, ancora, alvo) => {
    expect(destinoEfetivo(card(ancora), campo).alvo).toBe(alvo);
  });

  it("never overrides a control the backend already named", () => {
    const d = card("negociacao", "termos-ad-corpus-resposta");
    expect(destinoEfetivo(d, "negociacao.valor_negociado")).toBe(d);
  });

  it("leaves a campo with no known control on its screen", () => {
    const d = card("negociacao");
    expect(destinoEfetivo(d, "negociacao.intermediario.i1.creci")).toBe(d);
  });

  it("re-points matricula.atos at the contract's act selection on the Contratos tab", () => {
    const d = destinoEfetivo(matriculas, "matricula.atos");
    expect(d).toMatchObject({ tela: "card_contratos", ancora: "contratos", alvo: "contrato-matricula-atos" });
  });

  it.each([
    ["matricula.titulo_aquisitivo", "imovel-titulo-aquisitivo"],
    ["matricula.titulo_aquisitivo_texto", "imovel-titulo-aquisitivo"],
    ["matricula.onus_credor", "imovel-onus-credor"],
  ])("re-points %s at the imóvel page section", (campo, alvo) => {
    const d = destinoEfetivo(matriculas, campo);
    expect(d).toMatchObject({ tela: "imovel", rota: "/imoveis/AP1", alvo });
  });

  it("names the endereço-do-registro control when the destino is already the imóvel page", () => {
    const imovel: GeracaoDestino = { tela: "imovel", rota: "/imoveis/AP1", ancora: null, alvo: null, ids: { imovel_codigo: "AP1" } };
    expect(destinoEfetivo(imovel, "imovel.endereco_registro_texto").alvo).toBe("imovel-endereco-registro");
    expect(destinoEfetivo(imovel, "imovel.numero_matricula")).toBe(imovel);
  });

  it("keeps a matricula falta it cannot place on the list route", () => {
    expect(destinoEfetivo(matriculas, "matricula.onus_fonte")).toBe(matriculas);
  });
});

describe("destinoDoBloqueio", () => {
  it("points the FGTS-not-marked blocker at the FGTS switch on the Financiamento tab", () => {
    expect(destinoDoBloqueio("FGTS_NAO_MARCADO_NO_FINANCIAMENTO")).toMatchObject({
      tela: "card_financiamento",
      ancora: "financiamento",
      alvo: "fgts-financiamento",
    });
  });

  it.each([
    ["FINANCIAMENTO_RECUSADO", "financiamento", "financiamento-situacao"],
    ["FINANCIAMENTO_SITUACAO_DESCONHECIDA", "financiamento", "financiamento-situacao"],
    ["FGTS_MAIOR_QUE_PARCELA", "negociacao", "negest-parcelas"],
    ["VALOR_FGTS_FORA_DO_FINANCIAMENTO", "negociacao", "negest-parcelas"],
    ["SOMA_PARCELAS_DIFERENTE_DO_PRECO", "negociacao", "negest-parcelas"],
    ["SINAIS_NAO_CONSECUTIVOS", "negociacao", "negest-parcelas"],
    ["SINAL_EM_PARCELAS_COM_DIVISAO", "negociacao", "negest-parcelas"],
    ["MAIS_DE_UM_SINAL", "negociacao", "negest-parcelas"],
    ["POSSE_MARCO_PARTE_DO_SINAL", "negociacao", "termos-posse-marco"],
    ["POSSE_MARCO_PARCELA_DESCONHECIDA", "negociacao", "termos-posse-marco"],
    ["ONUS_QUITACAO_SEM_PARCELA_SALDO", "negociacao", "termos-onus-quitacao"],
    ["ONUS_BAIXA_PROTOCOLO_POSTERIOR", "negociacao", "termos-onus-baixa-protocolo"],
  ])("%s -> %s › #%s", (codigo, ancora, alvo) => {
    expect(destinoDoBloqueio(codigo)).toMatchObject({ ancora, alvo, tela: `card_${ancora}` });
  });

  it("returns null for a blocker no card control answers", () => {
    expect(destinoDoBloqueio("CPF_INVALIDO")).toBeNull();
    expect(destinoDoBloqueio("ONUS_FONTE_INVALIDA")).toBeNull();
  });
});
