/**
 * aditivoDraft — draft ↔ wire conversion and the client-side mirror of the
 * aditivo 422 rules (contrato-aditivos-CONTRACT §1). Synthetic data only.
 */
import { describe, expect, it } from "vitest";

import type { AditivoOut } from "@/hooks/useContratoAditivos";

import {
  alteracaoVazia,
  draftDoAditivo,
  draftSujo,
  patchDoDraft,
  validarDraft,
} from "./aditivoDraft";

function aditivo(over: Partial<AditivoOut> = {}): AditivoOut {
  return {
    id: "ad1",
    contrato_id: "c1",
    ordinal: 1,
    estilo: "house",
    status: "rascunho",
    status_em: null,
    status_por: null,
    alteracoes: [],
    parcelas: [],
    assinatura_data: null,
    modalidade_assinatura: "digital",
    created_at: "2026-09-24T12:00:00+00:00",
    updated_at: null,
    versao_atual: null,
    versoes: [],
    ...over,
  };
}

describe("aditivoDraft", () => {
  it("round-trips a stored aditivo without reading as dirty", () => {
    const a = aditivo({
      alteracoes: [
        { tipo: "pagamento", clausula_alvo: 2, novo_valor: "490000.00" },
        { tipo: "posse", clausula_alvo: 5, data: "2026-10-15", precaria: true, finalidade: "a medição" },
        { tipo: "comissao", clausula_alvo: 13, parcela_corretagem: 1, marco: "parcela", parcela_numero: 2 },
        { tipo: "outro", clausula_alvo: null, titulo: "Da trava", texto: "Fica vedada qualquer alteração." },
      ],
      parcelas: [
        { id: "p2", ordem: 2, tipo: "saldo", valor: "440000.00", vencimento: "2026-12-10", evento: null,
          forma_pagamento: "TED", favorecido_id: "f1", confissao_divida: false },
        { id: "p1", ordem: 1, tipo: "sinal", valor: "50000.00", vencimento: null,
          evento: "na assinatura do presente aditivo", forma_pagamento: "PIX", favorecido_id: "f1",
          confissao_divida: false },
      ],
    });
    const draft = draftDoAditivo(a);
    expect(draft.parcelas.map((p) => p.uid)).toEqual(["p1", "p2"]);
    expect(draftSujo(draft, a)).toBe(false);
    expect(validarDraft(draft)).toEqual({});

    const patch = patchDoDraft(draft, a);
    expect(patch.alteracoes?.[0]).toEqual({ tipo: "pagamento", clausula_alvo: 2, novo_valor: "490000.00" });
    expect(patch.alteracoes?.[1]).toMatchObject({ tipo: "posse", precaria: true, finalidade: "a medição" });
    expect(patch.alteracoes?.[2]).toEqual({
      tipo: "comissao", clausula_alvo: 13, parcela_corretagem: 1, marco: "parcela",
      parcela_numero: 2, data: null,
    });
    // Order = list order; no client uid on the wire.
    expect(patch.parcelas?.map((p) => p.tipo)).toEqual(["sinal", "saldo"]);
    expect(patch.parcelas?.[0]).not.toHaveProperty("uid");
    // Unchanged date / modalidade are not re-sent.
    expect(patch).not.toHaveProperty("assinatura_data");
    expect(patch).not.toHaveProperty("modalidade_assinatura");
  });

  it("reads a typed pt-BR price as a decimal string and sends a changed date", () => {
    const a = aditivo();
    const draft = draftDoAditivo(a);
    const pag = alteracaoVazia("pagamento");
    pag.clausula = "2";
    pag.novoValor = "490.000,00";
    draft.alteracoes.push(pag);
    draft.assinaturaData = "2026-09-30";
    expect(draftSujo(draft, a)).toBe(true);
    const patch = patchDoDraft(draft, a);
    expect(patch.alteracoes?.[0]).toEqual({ tipo: "pagamento", clausula_alvo: 2, novo_valor: "490000.00" });
    expect(patch.assinatura_data).toBe("2026-09-30");
  });

  it("mirrors the 422 rules in pt-BR", () => {
    const draft = draftDoAditivo(aditivo());
    const posse = alteracaoVazia("posse");
    posse.clausula = "5";
    posse.precaria = true;
    const comissao = alteracaoVazia("comissao");
    comissao.clausula = "70";
    comissao.marco = "data";
    const outro = alteracaoVazia("outro");
    outro.titulo = "ab";
    outro.texto = "curto";
    const pagamento = alteracaoVazia("pagamento");
    draft.alteracoes.push(posse, comissao, outro, pagamento);

    const erros = validarDraft(draft);
    expect(erros[posse.uid]).toEqual([
      "Informe a data da posse.",
      "A posse precária exige a finalidade.",
    ]);
    expect(erros[comissao.uid]).toEqual([
      "A cláusula é um número inteiro entre 1 e 59.",
      "Informe a data do pagamento da comissão.",
    ]);
    expect(erros[outro.uid]).toEqual([
      "O título tem de 3 a 120 caracteres.",
      "O texto tem de 10 a 8000 caracteres.",
    ]);
    // The clause is optional only for `outro`.
    expect(erros[pagamento.uid]).toEqual(["Informe o número da cláusula do contrato original."]);
  });
});
