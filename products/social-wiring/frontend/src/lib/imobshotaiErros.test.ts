import { describe, expect, it } from "vitest";
import { ApiError } from "@noctusai/lib/api";
import { mensagemImobShotAI } from "./imobshotaiErros";

const erro = (status: number, code: string, msg: string) => new ApiError(status, msg, { detail: { detail: msg, code } });

describe("mensagemImobShotAI (contract §1, §5 codes)", () => {
  it.each([
    ["sem_acesso_edicao_fotos", "Seu papel não dá acesso ao ImobShotAI."],
    ["imovel_inexistente", "Nenhum imóvel com esse código."],
    ["restrito_admin_organizacao", "Aguardando aprovação de um administrador."],
    ["card_nao_encontrado", "Esse imóvel não foi encontrado no ImobShotAI."],
  ])("%s -> contract copy", (code, copy) => expect(mensagemImobShotAI(erro(422, code, "msg do servidor"), "fallback")).toBe(copy));

  it("keeps the server's message for the lotes-route codes", () => {
    expect(mensagemImobShotAI(erro(422, "modelo_nao_configurado", "Configure um modelo."), "fallback")).toBe("Configure um modelo.");
    expect(mensagemImobShotAI(erro(422, "sem_tipos_edicao", "Ative um tipo de edição."), "fallback")).toBe("Ative um tipo de edição.");
  });

  it("falls back when the error carries nothing", () => {
    expect(mensagemImobShotAI(new Error(""), "Não foi possível.")).toBe("Não foi possível.");
    expect(mensagemImobShotAI(undefined, "Não foi possível.")).toBe("Não foi possível.");
  });
});
