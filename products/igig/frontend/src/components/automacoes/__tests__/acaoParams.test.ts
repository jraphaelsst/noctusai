/**
 * The ação draft → wire params mapping. The backend refuses ANY extra key
 * per tipo (`extra="forbid"`), so `montarAcao` must emit exactly the keys of
 * `PARAMS_POR_TIPO` in `app/schemas/automacoes.py`.
 */
import { describe, expect, it } from "vitest";

import { DRAFT_VAZIO, draftDe, montarAcao, problemaDoDraft, resumoAcao } from "../acaoParams";

const d = (over: Partial<typeof DRAFT_VAZIO>) => ({ ...DRAFT_VAZIO, ...over });

describe("montarAcao — exactly the keys each tipo accepts", () => {
  it.each([
    ["criar_checklist", ["itens", "titulo"]],
    ["definir_responsavel", ["profissional_id"]],
    ["criar_tarefa", ["prazo_dias", "responsavel_id", "titulo"]],
    ["notificar", ["mensagem", "titulo", "usuario_ids"]],
    ["enviar_email", ["assunto", "mensagem", "para"]],
    ["enviar_whatsapp", ["mensagem", "para"]],
  ] as const)("%s", (tipo, chaves) => {
    const cheio = d({ titulo: "t", itens: "a", profissional_id: "p", prazo_dias: "2", responsavel_id: "r", mensagem: "m", assunto: "s", para: "x@y.co", usuario_ids: ["u"] });
    const acao = montarAcao(tipo, cheio);
    expect(acao.tipo).toBe(tipo);
    expect(Object.keys(acao.params).sort()).toEqual([...chaves]);
  });

  it("checklist itens: one per line, blanks dropped", () => {
    expect(montarAcao("criar_checklist", d({ titulo: " Onboarding ", itens: "Contrato\n\n  Briefing \n" })).params).toEqual({
      titulo: "Onboarding",
      itens: ["Contrato", "Briefing"],
    });
  });

  it("optional text is null, not an empty string", () => {
    expect(montarAcao("enviar_whatsapp", d({ mensagem: "Oi {nome}" })).params).toEqual({ mensagem: "Oi {nome}", para: null });
    expect(montarAcao("criar_tarefa", d({ titulo: "x" })).params).toEqual({ titulo: "x", prazo_dias: null, responsavel_id: null });
  });
});

describe("problemaDoDraft", () => {
  it("names what is missing per tipo", () => {
    expect(problemaDoDraft("definir_responsavel", DRAFT_VAZIO)).toBe("Escolha o responsável.");
    expect(problemaDoDraft("enviar_email", d({ assunto: "a", mensagem: "m", para: "nao-e-email" }))).toBe(
      "E-mail do destinatário inválido.",
    );
    expect(problemaDoDraft("criar_tarefa", d({ titulo: "x", prazo_dias: "400" }))).toBe("Prazo máximo: 365 dias.");
    expect(problemaDoDraft("notificar", DRAFT_VAZIO)).toBeNull();
  });
});

describe("draftDe ↔ montarAcao round-trip", () => {
  it("an existing rule re-emits the same params", () => {
    const acao = { tipo: "criar_checklist" as const, params: { titulo: "Kickoff", itens: ["a", "b"] } };
    expect(montarAcao("criar_checklist", draftDe(acao))).toEqual(acao);
  });
});

describe("resumoAcao", () => {
  it("summarises for the list", () => {
    expect(resumoAcao({ tipo: "enviar_email", params: { assunto: "Bem-vindo", mensagem: "m", para: null } })).toBe(
      'E-mail "Bem-vindo" ao contato do card',
    );
    expect(
      resumoAcao({ tipo: "definir_responsavel", params: { profissional_id: "p1" } }, { profissional: () => "Ana" }),
    ).toBe("Responsável: Ana");
  });
});
