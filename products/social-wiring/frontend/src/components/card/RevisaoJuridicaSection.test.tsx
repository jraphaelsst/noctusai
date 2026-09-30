/**
 * RevisaoJuridicaSection — the ONE final legal review of a generated version
 * (owner decision 2026-09-30, migration 177).
 *
 * Pins every state: `nao_exigida` renders nothing, `aguardando` lists each
 * machine-derived field as "extraído automaticamente — revisar no documento"
 * (never its value) with the single "Aprovar revisão jurídica" (admin only,
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
      isAdmin
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

  it("🔴 aguardando lists each machine-derived field with its source — to be checked in the document", async () => {
    const { screen } = await render();
    const bloco = screen.getByTestId("contrato-revisao-aguardando-c1");
    expect(bloco.textContent).toContain("Aguardando revisão jurídica");
    const linha = screen.getByTestId("contrato-revisao-campo-cliente:p1:cpf");
    expect(linha.textContent).toContain("CPF");
    expect(linha.textContent).toContain("Fulano de Tal (proprietario)");
    expect(linha.textContent).toContain("extraído automaticamente");
    expect(linha.textContent).toContain("RG");
    expect(linha.textContent).toContain("rg-fulano.pdf");
    expect(linha.textContent).toContain("revisar no documento");
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
    const { screen } = await render({ isAdmin: false });
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
