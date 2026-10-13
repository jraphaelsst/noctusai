/**
 * RevisaoJuridicaSection — the ONE final legal review of a generated version
 * (owner decision 2026-09-30, migration 177).
 *
 * Pins every state: `nao_exigida` renders nothing, `aguardando` lists each
 * fact with its VALUE (masked until revealed), source, reason and measured
 * precision — derived/corroborated ones collapsed apart, uncounted — with
 * the single "Aprovar revisão jurídica" (admin only,
 * behind a confirmation), `aprovada` says who/when; and the in-flight
 * approval disables the button.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { RevisaoJuridicaSection } from "./RevisaoJuridicaSection";
import type { RevisaoJuridica, VersaoOut } from "@/hooks/useContratos";

function versao(revisao: RevisaoJuridica | null | undefined): VersaoOut {
  return {
    id: "v3",
    nome_original: "contrato-gerado-v3.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 2048,
    tipo_documento: "contrato",
    enviado_por: null,
    created_at: "2026-09-30T12:00:00+00:00",
    numero: 3,
    rotulo: null,
    origem: "gerado",
    docx_disponivel: true,
    modalidade_assinatura: "digital",
    revisao_juridica: revisao,
  };
}

const CAMPO = {
  chave: "cliente:p1:cpf",
  entidade: "cliente",
  entidade_id: "p1",
  campo: "cpf",
  rotulo: "CPF",
  grupo: "Fulano de Tal (proprietario)",
  origem: "rg",
  fonte_documento_id: "d1",
  fonte_nome: "rg-fulano.pdf",
  confianca: "alta",
};

function aguardando(campos = [CAMPO]): RevisaoJuridica {
  return { status: "aguardando", campos, revisado_por: null, revisado_em: null };
}

async function render(props: Partial<Parameters<typeof RevisaoJuridicaSection>[0]> = {}) {
  const rtl = await import("@testing-library/react");
  rtl.render(
    <RevisaoJuridicaSection
      contratoId="c1"
      versao={versao(aguardando())}
      podeAprovarRevisao
      onAprovar={vi.fn()}
      {...props}
    />,
  );
  return rtl;
}

describe("RevisaoJuridicaSection", () => {
  it("renders nothing when no review is needed (and for a pre-177 row without the field)", async () => {
    const { screen } = await render({
      versao: versao({ status: "nao_exigida", campos: [], revisado_por: null, revisado_em: null }),
    });
    expect(screen.queryByTestId("contrato-revisao-aguardando-c1")).toBeNull();
    expect(screen.queryByTestId("contrato-revisao-aprovada-c1")).toBeNull();
    (await import("@testing-library/react")).cleanup();

    const segundo = await render({ versao: versao(undefined) });
    expect(segundo.screen.queryByTestId("contrato-revisao-aguardando-c1")).toBeNull();
  });

  it("🔴 a row recorded before values existed still lists the field, its person and source", async () => {
    const { screen } = await render();
    const bloco = screen.getByTestId("contrato-revisao-aguardando-c1");
    expect(bloco.textContent).toContain("Aguardando revisão jurídica");
    expect(bloco.textContent).toContain("Fulano de Tal (proprietario)");
    const linha = screen.getByTestId("contrato-revisao-campo-cliente:p1:cpf");
    expect(linha.textContent).toContain("CPF");
    expect(linha.textContent).toContain("extraído automaticamente");
    expect(linha.textContent).toContain("fonte: RG · rg-fulano.pdf");
    expect(linha.textContent).toContain("confira no PDF");
    expect(linha.textContent).toContain("sem medição");
    // The document's own confidence is never shown (owner 2026-10-13).
    expect(linha.textContent).not.toContain("Confiança");
  });

  it("🔴 shows the VALUE, masked until revealed, with the measured precision and the reason", async () => {
    const campo = {
      ...CAMPO, valor: "123.456.789-09", valor_mascarado: "***.456.789-**", valor_confere: true,
      secao: "extraido" as const, fonte_tipo: "CNH", precisao: "precisão medida 39% (18 contratos)",
      motivo: "Lido automaticamente do documento e ainda não confirmado por ninguém.",
    };
    const { screen, fireEvent } = await render({ versao: versao(aguardando([campo])) });
    const valor = screen.getByTestId("contrato-revisao-valor-cliente:p1:cpf");
    expect(valor.textContent).toBe("***.456.789-**");
    fireEvent.click(screen.getByTestId("contrato-revisao-revelar-cliente:p1:cpf"));
    expect(valor.textContent).toBe("123.456.789-09");
    const linha = screen.getByTestId("contrato-revisao-campo-cliente:p1:cpf").textContent ?? "";
    expect(linha).toContain("fonte: CNH · rg-fulano.pdf");
    expect(linha).toContain("precisão medida 39% (18 contratos)");
    expect(linha).toContain("ainda não confirmado");
    expect(screen.queryByTestId("contrato-revisao-mudou-cliente:p1:cpf")).toBeNull();
  });

  it("🔴 derived and corroborated values are collapsed apart and never counted as extracted", async () => {
    const derivado = { ...CAMPO, chave: "cliente:p2:endereco", campo: "endereco", secao: "derivado" as const,
      valor: "Rua das Amostras, 10", motivo: "Copiado do endereço do cônjuge (mesmo domicílio)" };
    const corroborado = { ...CAMPO, chave: "cliente:p1:nome_oficial", campo: "nome_oficial",
      secao: "corroborado" as const, valor: "Fulano de Tal", n_documentos: 2 };
    const { screen } = await render({ versao: versao(aguardando([CAMPO, derivado, corroborado])) });
    const texto = screen.getByTestId("contrato-revisao-texto-c1").textContent ?? "";
    expect(texto).toContain("um dado extraído automaticamente");
    const derivados = screen.getByTestId("contrato-revisao-derivados-c1");
    expect(derivados.tagName).toBe("DETAILS");
    expect(derivados.textContent).toContain("Derivados (conferir) (1)");
    expect(derivados.textContent).toContain("Copiado do endereço do cônjuge");
    expect(screen.getByTestId("contrato-revisao-corroborados-c1").textContent).toContain(
      "Confirmado por documentos (1)",
    );
    expect(screen.getByTestId("contrato-revisao-campos-c1").textContent).not.toContain("Rua das Amostras");
  });

  it("warns when the value changed after the version was generated", async () => {
    const campo = { ...CAMPO, valor: "529.982.247-25", valor_confere: false };
    const { screen } = await render({ versao: versao(aguardando([campo])) });
    expect(screen.getByTestId("contrato-revisao-mudou-cliente:p1:cpf").textContent).toContain(
      "gere uma nova versão",
    );
  });

  it("🔴 counts the extracted values only when there are some", async () => {
    const { screen } = await render();
    const texto = screen.getByTestId("contrato-revisao-texto-c1").textContent ?? "";
    expect(texto).toContain("gerada pelo sistema");
    expect(texto).toContain("um dado extraído automaticamente");
  });

  it("🔴 a version with ZERO extracted values still waits — and never reads '0 dados'", async () => {
    const { screen, fireEvent } = await render({ versao: versao(aguardando([])) });
    expect(screen.getByTestId("contrato-revisao-aguardando-c1")).toBeTruthy();
    const texto = screen.getByTestId("contrato-revisao-texto-c1").textContent ?? "";
    expect(texto).not.toMatch(/\b0 dados?\b/);
    expect(texto).toContain("Nenhum dado foi extraído automaticamente");
    expect(texto).toContain("revise o contrato por inteiro");
    expect(screen.queryByTestId("contrato-revisao-campos-c1")).toBeNull();
    fireEvent.click(screen.getByTestId("contrato-revisao-aprovar-c1"));
    const dialogo = document.body.textContent ?? "";
    expect(dialogo).toContain("foi revisado por inteiro");
    expect(dialogo).not.toContain("passa a constar");
  });

  it("an aditivo's generated wording and free clauses are not called 'extraído'", async () => {
    const base = { ...CAMPO, entidade: "aditivo", entidade_id: "a1", grupo: "Aditivo",
      fonte_documento_id: null, fonte_nome: null, confianca: null };
    const { screen } = await render({
      contratoId: "a1",
      documento: "aditivo",
      testIdPrefix: "aditivo-revisao",
      versao: versao(
        aguardando([
          { ...base, chave: "aditivo:a1:redacao", campo: "redacao", origem: "gerado",
            rotulo: "Redação do aditivo (revisão jurídica obrigatória)" },
          { ...base, chave: "aditivo:a1:outro:1", campo: "outro", origem: "manual",
            rotulo: "Cláusula livre: DA TRAVA" },
        ]),
      ),
    });
    const texto = screen.getByTestId("aditivo-revisao-texto-a1").textContent ?? "";
    expect(texto).toContain("revise o aditivo por inteiro");
    const redacao = screen.getByTestId("aditivo-revisao-campo-aditivo:a1:redacao").textContent ?? "";
    expect(redacao).toContain("texto gerado pelo sistema");
    expect(redacao).not.toContain("extraído");
    const livre = screen.getByTestId("aditivo-revisao-campo-aditivo:a1:outro:1").textContent ?? "";
    expect(livre).toContain("redigido pela equipe");
  });

  it("🔴 lists the wording items (migration 193) as reading the reviewer must do", async () => {
    const { screen, fireEvent } = await render({
      versao: versao({
        ...aguardando(),
        itens: [{ codigo: "PJ_REDACAO", titulo: "Qualificação da empresa vendedora", texto: "EMPRESA EXEMPLO LTDA, inscrita no CNPJ…" }],
      }),
    });
    const bloco = screen.getByTestId("contrato-revisao-itens-c1");
    expect(bloco.textContent).toContain("leitura obrigatória");
    expect(bloco.textContent).toContain("Qualificação da empresa vendedora");
    fireEvent.click(screen.getByTestId("contrato-revisao-aprovar-c1"));
    expect(document.body.textContent).toContain("incluindo o texto listado");
  });

  it("🔴 'Aprovar revisão jurídica' asks for confirmation, then calls back with the version id", async () => {
    const onAprovar = vi.fn();
    const { screen, fireEvent } = await render({ onAprovar });
    fireEvent.click(screen.getByTestId("contrato-revisao-aprovar-c1"));
    expect(onAprovar).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("contrato-revisao-aprovar-confirmar-c1"));
    expect(onAprovar).toHaveBeenCalledWith("v3");
  });

  it("a non-admin sees who approves instead of a button", async () => {
    const { screen } = await render({ podeAprovarRevisao: false });
    expect(screen.queryByTestId("contrato-revisao-aprovar-c1")).toBeNull();
    expect(screen.getByTestId("contrato-revisao-so-admin-c1")).toBeTruthy();
  });

  it("the button waits while the approval is in flight", async () => {
    const { screen } = await render({ aprovando: true });
    expect(
      (screen.getByTestId("contrato-revisao-aprovar-c1") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("aprovada says who approved and when — and offers no button", async () => {
    const { screen } = await render({
      versao: versao({
        status: "aprovada",
        campos: [CAMPO],
        revisado_por: { id: "u9", nome: "Dra. Jurídica" },
        revisado_em: "2026-09-30T15:00:00+00:00",
      }),
    });
    const linha = screen.getByTestId("contrato-revisao-aprovada-c1");
    expect(linha.textContent).toContain("Revisão jurídica aprovada");
    expect(linha.textContent).toContain("Dra. Jurídica");
    expect(screen.queryByTestId("contrato-revisao-aprovar-c1")).toBeNull();
  });
});
