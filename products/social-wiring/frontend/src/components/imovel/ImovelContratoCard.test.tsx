/**
 * ImovelContratoCard — what the contract needs from the matrícula.
 *
 * The assertions worth having are the ones about ABSENCE, because that is
 * where this screen either helps or wastes someone's afternoon: a missing
 * título phrase has five different causes, each fixed somewhere else, and a
 * blank field says none of them. Plus the office's 5-year certidões rule,
 * which must fire on an unreadable date too — an unknown date leads to
 * asking, never to silently waiving.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelContratoCard from "./ImovelContratoCard";
import type {
  AntigosProprietariosResponse,
  OnusCredorResponse,
  TituloAquisitivoResponse,
} from "@/hooks/useImovelContrato";

function titulo(over: Partial<TituloAquisitivoResponse> = {}): TituloAquisitivoResponse {
  return {
    codigo: "AP1234",
    ato: {
      extracao_id: "extracao-9",
      ato_id: "ato-1",
      kind: "R",
      numero: 1,
      ato_ref: "R-1",
      detalhes_origem: "sugestao",
    },
    sugestao: "conforme R-1 da matrícula, Escritura Pública lavrada no 1o Tabelião",
    motivo_sem_sugestao: null,
    confirmado: null,
    ...over,
  };
}

function onus(over: Partial<OnusCredorResponse> = {}): OnusCredorResponse {
  return {
    codigo: "AP1234",
    extracao_id: "extracao-9",
    atos: [
      {
        ato_id: "ato-2",
        kind: "R",
        numero: 2,
        ato_ref: "R-2",
        natureza: "hipoteca",
        credor: "Banco do Brasil S.A.",
        credor_confianca: "alta",
        detalhes_origem: "confirmado",
      },
    ],
    sugestao: "Banco do Brasil S.A.",
    motivo_sem_sugestao: null,
    confirmado: null,
    ...over,
  };
}

function antigos(
  over: Partial<AntigosProprietariosResponse> = {},
): AntigosProprietariosResponse {
  return {
    codigo: "AP1234",
    extracao_id: "extracao-9",
    ultima_transferencia: {
      ato_id: "ato-1",
      ato_ref: "R-1",
      natureza: "compra_e_venda",
      data_registro: "2024-05-10",
      detalhes_origem: "sugestao",
    },
    transmitentes: [{ nome: "Joao da Silva", cpf_cnpj: "000.000.000-00" }],
    exige_certidoes: true,
    data_desconhecida: false,
    sem_registro: false,
    origem: "extracao",
    manual: null,
    ...over,
  };
}

async function render(props: Record<string, unknown> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  const onConfirmarTitulo = vi.fn();
  const onConfirmarEnderecoRegistro = vi.fn();
  const onConfirmarOnusCredor = vi.fn();
  const onConfirmarUltimaTransferenciaManual = vi.fn();
  const onConfirmarDescricao = vi.fn();
  const view = rtl.render(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(ImovelContratoCard, {
        codigo: "AP1234",
        titulo: titulo(),
        tituloShowSkeleton: false,
        tituloIsRefreshing: false,
        tituloIsError: false,
        savingTitulo: false,
        onConfirmarTitulo,
        enderecoRegistro: { codigo: "AP1234", confirmado: null },
        enderecoRegistroShowSkeleton: false,
        enderecoRegistroIsRefreshing: false,
        enderecoRegistroIsError: false,
        savingEnderecoRegistro: false,
        onConfirmarEnderecoRegistro,
        descricao: {
          codigo: "AP1234",
          derivado: "Apartamento ficticio nº 12, com 80,00 m² de área privativa.",
          confirmado: null,
          efetivo: "Apartamento ficticio nº 12, com 80,00 m² de área privativa.",
          origem: "matricula",
        },
        descricaoShowSkeleton: false,
        descricaoIsRefreshing: false,
        descricaoIsError: false,
        savingDescricao: false,
        onConfirmarDescricao,
        onus: onus(),
        onusShowSkeleton: false,
        onusIsRefreshing: false,
        onusIsError: false,
        savingOnus: false,
        onConfirmarOnusCredor,
        antigos: antigos(),
        antigosShowSkeleton: false,
        antigosIsError: false,
        savingUltimaTransferenciaManual: false,
        onConfirmarUltimaTransferenciaManual,
        ...props,
      } as never),
    ),
  );
  return {
    ...rtl,
    ...view,
    onConfirmarTitulo,
    onConfirmarEnderecoRegistro,
    onConfirmarOnusCredor,
    onConfirmarUltimaTransferenciaManual,
    onConfirmarDescricao,
  };
}

describe("ImovelContratoCard — título aquisitivo", () => {
  it("shows the suggested phrase and which act it came from", async () => {
    const { getByTestId } = await render();
    const sugestao = getByTestId("imovel-titulo-sugestao");
    expect(sugestao.textContent).toContain("Escritura Pública");
    expect(sugestao.textContent).toContain("R-1");
  });

  it("copies the suggestion into the editable field on request", async () => {
    const { getByTestId, fireEvent } = await render();
    fireEvent.click(getByTestId("imovel-titulo-usar-sugestao"));
    expect((getByTestId("imovel-titulo-texto") as HTMLTextAreaElement).value).toContain(
      "Escritura Pública",
    );
  });

  it("confirms the wording the operator actually has on screen", async () => {
    const { getByTestId, fireEvent, onConfirmarTitulo } = await render();
    fireEvent.change(getByTestId("imovel-titulo-texto"), {
      target: { value: "  frase revisada  " },
    });
    fireEvent.click(getByTestId("imovel-titulo-confirmar"));
    expect(onConfirmarTitulo).toHaveBeenCalledWith("frase revisada");
  });

  it("🔴 confirming an empty field CLEARS, sending null rather than \"\"", async () => {
    const { getByTestId, fireEvent, onConfirmarTitulo } = await render({
      titulo: titulo({
        confirmado: { texto: "antiga", confirmado_por: null, confirmado_em: null },
      }),
    });
    fireEvent.change(getByTestId("imovel-titulo-texto"), { target: { value: "" } });
    fireEvent.click(getByTestId("imovel-titulo-confirmar"));
    expect(onConfirmarTitulo).toHaveBeenCalledWith(null);
  });

  it("🔴 explains WHY there is no suggestion, in pt-BR, and links to the fix", async () => {
    // Five different causes, five different fixes, all of them elsewhere. A
    // blank field would send the operator hunting for a bug instead.
    const { getByTestId } = await render({
      titulo: titulo({ sugestao: null, motivo_sem_sugestao: "sem_instrumento" }),
    });
    const aviso = getByTestId("imovel-titulo-sem-sugestao");
    expect(aviso.getAttribute("data-motivo")).toBe("sem_instrumento");
    expect(aviso.textContent).toContain("instrumento");
    const link = aviso.querySelector("a") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas?extracao=extracao-9");
  });

  it("points at the imóvel's matrículas when no título act is confirmed yet", async () => {
    const { getByTestId } = await render({
      titulo: titulo({ ato: null, sugestao: null, motivo_sem_sugestao: "sem_titulo_confirmado" }),
    });
    const aviso = getByTestId("imovel-titulo-sem-sugestao");
    expect(aviso.textContent).toContain("título aquisitivo");
    expect((aviso.querySelector("a") as HTMLAnchorElement).getAttribute("href")).toBe(
      "/matriculas?codigo=AP1234",
    );
  });

  it("F73: a removed matrícula shows the server's pendência message and a pick-another action", async () => {
    const mensagem = "A matrícula do título aquisitivo confirmado foi removida — escolha outra.";
    const { getByTestId } = await render({
      titulo: titulo({
        ato: null,
        sugestao: null,
        motivo_sem_sugestao: "matricula_removida",
        mensagem_pendencia: mensagem,
      }),
    });
    const aviso = getByTestId("imovel-titulo-sem-sugestao");
    expect(aviso.getAttribute("data-motivo")).toBe("matricula_removida");
    expect(aviso.textContent).toContain(mensagem);
    const link = aviso.querySelector("a") as HTMLAnchorElement;
    expect(link.textContent).toContain("Escolher outra matrícula");
    expect(link.getAttribute("href")).toBe("/matriculas?codigo=AP1234");
  });

  it("F73: título block has loading and error states (no pendência while loading/erroring)", async () => {
    const carregando = await render({ titulo: undefined, tituloShowSkeleton: true });
    expect(carregando.getByTestId("imovel-titulo-skeleton")).toBeTruthy();
    expect(carregando.queryByTestId("imovel-titulo-sem-sugestao")).toBeNull();
    (await import("@testing-library/react")).cleanup();
    const erro = await render({ titulo: undefined, tituloIsError: true });
    expect(erro.getByTestId("imovel-titulo-erro")).toBeTruthy();
    expect(erro.queryByTestId("imovel-titulo-sem-sugestao")).toBeNull();
  });

  it("F73: the pendência message wins over the generic motivo text", async () => {
    const { getByTestId } = await render({
      titulo: titulo({
        ato: null,
        sugestao: null,
        motivo_sem_sugestao: "matricula_removida",
        mensagem_pendencia: "Mensagem do servidor.",
      }),
    });
    expect(getByTestId("imovel-titulo-sem-sugestao").textContent).toContain("Mensagem do servidor.");
  });

  it("names who confirmed the wording in force", async () => {
    const { getByTestId } = await render({
      titulo: titulo({
        confirmado: {
          texto: "frase final",
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-03-01T10:00:00Z",
        },
      }),
    });
    expect(getByTestId("imovel-titulo-confirmado").textContent).toContain("Ana");
  });

  const confirmado = {
    texto: "frase final",
    confirmado_por: { id: "u1", nome: "Ana" },
    confirmado_em: "2026-03-01T10:00:00Z",
  };

  it("lists only the divergent fact (folhas) with pt-BR label", async () => {
    const { getByTestId, queryByTestId } = await render({
      titulo: titulo({
        confirmado,
        divergencias: [{ fato: "folhas", atual: "09/15", sugerido: "071/076" }],
      }),
    });
    const li = getByTestId("imovel-titulo-divergencia-folhas");
    expect(li.textContent).toContain("Folhas");
    expect(li.textContent).toContain("09/15");
    expect(li.textContent).toContain("071/076");
    expect(queryByTestId("imovel-titulo-divergencia-data")).toBeNull();
    expect(queryByTestId("imovel-titulo-divergencia-livro")).toBeNull();
  });

  it("shows no divergence block when none (or older backend)", async () => {
    const { queryByTestId } = await render({ titulo: titulo({ confirmado }) });
    expect(queryByTestId("imovel-titulo-divergencias")).toBeNull();
  });
});

describe("ImovelContratoCard — endereço do registro", () => {
  it("has no suggestion affordance — never a recomputed guess", async () => {
    const { queryByTestId } = await render();
    expect(queryByTestId("imovel-endereco-registro-sugestao")).toBeNull();
    expect(queryByTestId("imovel-endereco-registro-usar-sugestao")).toBeNull();
  });

  it("confirms the address the operator actually has on screen", async () => {
    const { getByTestId, fireEvent, onConfirmarEnderecoRegistro } = await render();
    fireEvent.change(getByTestId("imovel-endereco-registro-texto"), {
      target: { value: "  Rua Fictícia, nº 100  " },
    });
    fireEvent.click(getByTestId("imovel-endereco-registro-confirmar"));
    expect(onConfirmarEnderecoRegistro).toHaveBeenCalledWith("Rua Fictícia, nº 100");
  });

  it("🔴 confirming an empty field CLEARS, sending null rather than \"\"", async () => {
    const { getByTestId, fireEvent, onConfirmarEnderecoRegistro } = await render({
      enderecoRegistro: {
        codigo: "AP1234",
        confirmado: { texto: "antigo", confirmado_por: null, confirmado_em: null },
      },
    });
    fireEvent.change(getByTestId("imovel-endereco-registro-texto"), { target: { value: "" } });
    fireEvent.click(getByTestId("imovel-endereco-registro-confirmar"));
    expect(onConfirmarEnderecoRegistro).toHaveBeenCalledWith(null);
  });

  it("names who confirmed the address in force", async () => {
    const { getByTestId } = await render({
      enderecoRegistro: {
        codigo: "AP1234",
        confirmado: {
          texto: "Rua Fictícia, nº 100",
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-03-01T10:00:00Z",
        },
      },
    });
    expect(getByTestId("imovel-endereco-registro-confirmado").textContent).toContain("Ana");
  });
});

describe("ImovelContratoCard — ônus creditor", () => {
  it("confirms the creditor the operator typed", async () => {
    const { getByTestId, fireEvent, onConfirmarOnusCredor } = await render();
    fireEvent.change(getByTestId("imovel-onus-credor-input"), {
      target: { value: "Banco X S.A." },
    });
    fireEvent.click(getByTestId("imovel-onus-credor-confirmar"));
    expect(onConfirmarOnusCredor).toHaveBeenCalledWith("Banco X S.A.");
  });

  it("offers the creditor read from the confirmed ônus acts", async () => {
    const { getByTestId, fireEvent } = await render();
    fireEvent.click(getByTestId("imovel-onus-credor-usar-sugestao"));
    expect((getByTestId("imovel-onus-credor-input") as HTMLInputElement).value).toBe(
      "Banco do Brasil S.A.",
    );
  });

  it("🔴 flags a low-confidence creditor next to the act it came from", async () => {
    const { getByTestId } = await render({
      onus: onus({
        atos: [
          {
            ato_id: "ato-2",
            kind: "R",
            numero: 2,
            ato_ref: "R-2",
            natureza: "hipoteca",
            credor: "Banco talvez",
            credor_confianca: "baixa",
            detalhes_origem: "sugestao",
          },
        ],
      }),
    });
    expect(getByTestId("imovel-onus-credor-confianca-ato-2").textContent).toContain("confira");
  });

  it("explains an absent creditor rather than showing an empty box", async () => {
    const { getByTestId } = await render({
      onus: onus({ sugestao: null, motivo_sem_sugestao: "sem_credor", atos: [] }),
    });
    expect(getByTestId("imovel-onus-credor-sem-sugestao").textContent).toContain("credor");
  });
});

describe("ImovelContratoCard — antigos proprietários", () => {
  it("shows the last transfer and who sold", async () => {
    const { getByTestId } = await render();
    expect(getByTestId("imovel-antigos-proprietarios").textContent).toContain("R-1");
    expect(getByTestId("imovel-antigos-proprietarios").textContent).toContain("10/05/2024");
    expect(getByTestId("imovel-antigos-transmitentes").textContent).toContain("Joao da Silva");
  });

  it("🔴 states plainly that the sellers' certidões are required", async () => {
    // The office rule: a sale registered less than five years ago.
    const { getByTestId } = await render();
    const aviso = getByTestId("imovel-antigos-exige-certidoes");
    expect(aviso.textContent).toContain("obrigatórias por padrão");
    expect(aviso.textContent).toContain("5 anos");
  });

  it("does not claim certidões are required when the sale is old enough", async () => {
    const { queryByTestId } = await render({
      antigos: antigos({ exige_certidoes: false, data_desconhecida: false }),
    });
    expect(queryByTestId("imovel-antigos-exige-certidoes")).toBeNull();
  });

  it("🔴 asks for the act's date when it could not be read — and still requires the certidões", async () => {
    // An unreadable date must lead to asking, never to silently waiving.
    const { getByTestId } = await render({
      antigos: antigos({
        data_desconhecida: true,
        exige_certidoes: true,
        ultima_transferencia: {
          ato_id: "ato-1",
          ato_ref: "R-1",
          natureza: "compra_e_venda",
          data_registro: null,
          detalhes_origem: "sugestao",
        },
      }),
    });
    expect(getByTestId("imovel-antigos-data-desconhecida").textContent).toContain(
      "Confirme a data",
    );
    expect(getByTestId("imovel-antigos-exige-certidoes")).toBeTruthy();
  });

  it("says when the matrícula has no registered sale at all", async () => {
    const { getByTestId } = await render({
      antigos: antigos({ ultima_transferencia: null, transmitentes: [], exige_certidoes: false }),
    });
    expect(getByTestId("imovel-antigos-vazio")).toBeTruthy();
  });
});

describe("ImovelContratoCard — última transferência (manual override, migration 152)", () => {
  it("🔴 a confirmed 'não consta' is an ANSWER, not the empty state", async () => {
    const { getByTestId, queryByTestId } = await render({
      antigos: antigos({
        ultima_transferencia: null,
        transmitentes: [],
        exige_certidoes: false,
        sem_registro: true,
        origem: "manual",
        manual: {
          data_registro: null,
          natureza: null,
          sem_registro: true,
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-09-22T10:00:00Z",
        },
      }),
    });
    expect(getByTestId("imovel-antigos-sem-registro").textContent).toContain(
      "não consta transferência",
    );
    expect(queryByTestId("imovel-antigos-vazio")).toBeNull();
  });

  it("the confirm button stays disabled with an empty draft", async () => {
    const { getByTestId } = await render({
      antigos: antigos({ manual: null }),
    });
    expect(
      (getByTestId("imovel-ultima-transferencia-confirmar") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("confirms a typed date (no nature chosen) as null, not a stray value", async () => {
    const { getByTestId, fireEvent, onConfirmarUltimaTransferenciaManual } = await render({
      antigos: antigos({ manual: null }),
    });
    fireEvent.change(getByTestId("imovel-ultima-transferencia-data"), {
      target: { value: "2023-07-11" },
    });
    fireEvent.click(getByTestId("imovel-ultima-transferencia-confirmar"));
    expect(onConfirmarUltimaTransferenciaManual).toHaveBeenCalledWith({
      data: "2023-07-11",
      natureza: null,
      semRegistro: false,
      transmitentes: [],
    });
  });

  it("🔴 checking 'não consta' clears the date draft and sends sem_registro, not a date", async () => {
    const { getByTestId, fireEvent, onConfirmarUltimaTransferenciaManual } = await render({
      antigos: antigos({ manual: null }),
    });
    fireEvent.change(getByTestId("imovel-ultima-transferencia-data"), {
      target: { value: "2023-07-11" },
    });
    fireEvent.click(getByTestId("imovel-ultima-transferencia-sem-registro"));
    expect((getByTestId("imovel-ultima-transferencia-data") as HTMLInputElement).value).toBe("");
    fireEvent.click(getByTestId("imovel-ultima-transferencia-confirmar"));
    expect(onConfirmarUltimaTransferenciaManual).toHaveBeenCalledWith({
      data: null,
      natureza: null,
      semRegistro: true,
      transmitentes: [],
    });
  });

  it("offers no Limpar button when there is no override yet", async () => {
    const { queryByTestId } = await render({ antigos: antigos({ manual: null }) });
    expect(queryByTestId("imovel-ultima-transferencia-limpar")).toBeNull();
  });

  it("Limpar clears the override entirely once one exists", async () => {
    const { getByTestId, fireEvent, onConfirmarUltimaTransferenciaManual } = await render({
      antigos: antigos({
        manual: {
          data_registro: "2023-07-11",
          natureza: "permuta",
          sem_registro: false,
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-09-22T10:00:00Z",
        },
      }),
    });
    fireEvent.click(getByTestId("imovel-ultima-transferencia-limpar"));
    expect(onConfirmarUltimaTransferenciaManual).toHaveBeenCalledWith({
      data: null,
      natureza: null,
      semRegistro: false,
      transmitentes: [],
    });
  });

  it("names who confirmed the manual override", async () => {
    const { getByTestId } = await render({
      antigos: antigos({
        manual: {
          data_registro: "2023-07-11",
          natureza: "permuta",
          sem_registro: false,
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-09-22T10:00:00Z",
        },
      }),
    });
    expect(getByTestId("imovel-ultima-transferencia-confirmado").textContent).toContain("Ana");
  });
});

describe("ImovelContratoCard — vinculo_legal markers", () => {
  it("marks título / endereço / ônus / última transferência from the manual record and conflicts", async () => {
    const { getByTestId } = await render({
      vinculoLegal: {
        manual_codigo: "SW-0001",
        fontes: {
          titulo_aquisitivo_texto: "SW-0001",
          endereco_registro_texto: "SW-0001",
          ultima_transferencia_manual: "SW-0001",
        },
        conflitos: ["onus_credor"],
      },
    });
    expect(getByTestId("vinculo-legal-titulo_aquisitivo_texto").textContent).toBe("do cadastro manual");
    expect(getByTestId("vinculo-legal-endereco_registro_texto").textContent).toBe("do cadastro manual");
    expect(getByTestId("vinculo-legal-ultima_transferencia_manual").textContent).toBe("do cadastro manual");
    expect(getByTestId("vinculo-legal-onus_credor").textContent).toBe("em conflito — revise");
  });

  it("no markers without a vínculo", async () => {
    const { queryByTestId } = await render();
    expect(queryByTestId("vinculo-legal-titulo_aquisitivo_texto")).toBeNull();
  });
});

describe("ImovelContratoCard — descrição do imóvel (migration 306)", () => {
  it("shows the matrícula's reading and confirms the typed text, which the operator can always enter", async () => {
    const { getByTestId, fireEvent, onConfirmarDescricao } = await render();
    expect(getByTestId("imovel-descricao-derivado").textContent).toContain("Apartamento ficticio");
    // Not pre-filled with the reading: a reading is not a decision.
    expect((getByTestId("imovel-descricao-texto") as HTMLTextAreaElement).value).toBe("");

    fireEvent.change(getByTestId("imovel-descricao-texto"), {
      target: { value: "  Casa ficticia nº 7, com 300,00 m² de terreno.  " },
    });
    fireEvent.click(getByTestId("imovel-descricao-confirmar"));
    expect(onConfirmarDescricao).toHaveBeenCalledWith(
      "Casa ficticia nº 7, com 300,00 m² de terreno.",
    );
  });

  it("copies the reading into the editable field on request", async () => {
    const { getByTestId, fireEvent } = await render();
    fireEvent.click(getByTestId("imovel-descricao-usar-derivado"));
    expect((getByTestId("imovel-descricao-texto") as HTMLTextAreaElement).value).toContain(
      "Apartamento ficticio",
    );
  });

  it("with no transcription, says so and still lets the operator type it", async () => {
    const { getByTestId, queryByTestId } = await render({
      descricao: { codigo: "AP1234", derivado: null, confirmado: null, efetivo: null, origem: null },
    });
    expect(getByTestId("imovel-descricao-sem-derivado")).toBeTruthy();
    expect(queryByTestId("imovel-descricao-derivado")).toBeNull();
    expect((getByTestId("imovel-descricao-confirmar") as HTMLButtonElement).disabled).toBe(false);
  });

  it("seeds the field from the typed override, names who confirmed it, and Limpar sends null", async () => {
    const { getByTestId, fireEvent, onConfirmarDescricao } = await render({
      descricao: {
        codigo: "AP1234",
        derivado: null,
        confirmado: {
          texto: "Casa ficticia nº 7.",
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-10-24T10:00:00Z",
        },
        efetivo: "Casa ficticia nº 7.",
        origem: "manual",
      },
    });
    expect((getByTestId("imovel-descricao-texto") as HTMLTextAreaElement).value).toBe(
      "Casa ficticia nº 7.",
    );
    expect(getByTestId("imovel-descricao-confirmado").textContent).toContain("Ana");
    fireEvent.click(getByTestId("imovel-descricao-limpar"));
    expect(onConfirmarDescricao).toHaveBeenCalledWith(null);
  });

  it("has loading and error states", async () => {
    const loading = await render({ descricaoShowSkeleton: true });
    expect(loading.getByTestId("imovel-descricao-skeleton")).toBeTruthy();
    expect(loading.queryByTestId("imovel-descricao-texto")).toBeNull();
    loading.unmount();
    const erro = await render({ descricaoIsError: true });
    expect(erro.getByTestId("imovel-descricao-erro")).toBeTruthy();
  });
});

describe("ImovelContratoCard — vendedores typed (migration 306)", () => {
  it("🔴 typed names alone are a valid override, sent one per line, blanks dropped", async () => {
    const { getByTestId, fireEvent, onConfirmarUltimaTransferenciaManual } = await render({
      antigos: antigos({ manual: null }),
    });
    fireEvent.change(getByTestId("imovel-ultima-transferencia-transmitentes"), {
      target: { value: " Fulano Ficticio \n\nBeltrana Ficticia" },
    });
    const confirmar = getByTestId("imovel-ultima-transferencia-confirmar") as HTMLButtonElement;
    expect(confirmar.disabled).toBe(false);
    fireEvent.click(confirmar);
    expect(onConfirmarUltimaTransferenciaManual).toHaveBeenCalledWith({
      data: null,
      natureza: null,
      semRegistro: false,
      transmitentes: ["Fulano Ficticio", "Beltrana Ficticia"],
    });
  });

  it("seeds the names from the override and marks typed sellers in the list", async () => {
    const { getByTestId } = await render({
      antigos: antigos({
        transmitentes: [{ nome: "Fulano Ficticio", cpf_cnpj: null }],
        transmitentes_origem: "manual",
        manual: {
          data_registro: null,
          natureza: null,
          sem_registro: false,
          transmitentes: ["Fulano Ficticio"],
          confirmado_por: { id: "u1", nome: "Ana" },
          confirmado_em: "2026-10-24T10:00:00Z",
        },
      }),
    });
    expect(
      (getByTestId("imovel-ultima-transferencia-transmitentes") as HTMLTextAreaElement).value,
    ).toBe("Fulano Ficticio");
    expect(getByTestId("imovel-antigos-transmitentes-manual")).toBeTruthy();
  });

  it("checking 'não consta' clears and disables the names", async () => {
    const { getByTestId, fireEvent } = await render({ antigos: antigos({ manual: null }) });
    const campo = getByTestId("imovel-ultima-transferencia-transmitentes") as HTMLTextAreaElement;
    fireEvent.change(campo, { target: { value: "Fulano Ficticio" } });
    fireEvent.click(getByTestId("imovel-ultima-transferencia-sem-registro"));
    expect(campo.value).toBe("");
    expect(campo.disabled).toBe(true);
  });
});
