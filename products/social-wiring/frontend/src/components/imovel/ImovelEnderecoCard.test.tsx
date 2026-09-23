/**
 * ImovelEnderecoCard — the manual address override (migration 149, widened
 * by 159), extracted from `ImovelCartorioCard.tsx` on 2026-09-23 (see this
 * component's own header for why).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelEnderecoCard from "./ImovelEnderecoCard";
import type { ImovelDados } from "@/hooks/useImovelDados";

function dados(over: Partial<ImovelDados> = {}): ImovelDados {
  return {
    codigo: "ONE9001",
    numero_matricula: null,
    numero_matricula_origem: null,
    numero_matricula_documento_id: null,
    numero_matricula_em: null,
    numero_matricula_confirmado_por: null,
    numero_matricula_confirmado_em: null,
    numero_registro_imoveis: null,
    prefeitura_cadastro_imobiliario: null,
    captador: null,
    situacao_onus: null,
    onus_observacoes: null,
    onus_certidao_em: null,
    onus_documento_id: null,
    onus_registrado_por: null,
    onus_registrado_em: null,
    situacoes_onus: [],
    titulo_aquisitivo_fonte: null,
    onus_fonte: null,
    endereco_manual_logradouro: null,
    endereco_manual_numero: null,
    endereco_manual_complemento: null,
    endereco_manual_bairro: null,
    endereco_manual_cidade: null,
    endereco_manual_uf: null,
    endereco_manual_cep: null,
    endereco_manual_confirmado_por: null,
    endereco_manual_confirmado_em: null,
    empreendimento_manual: null,
    empreendimento_manual_confirmado_por: null,
    empreendimento_manual_confirmado_em: null,
    updated_at: null,
    ...over,
  };
}

async function render(
  dadosOverride?: Partial<ImovelDados>,
  opts?: {
    onSave?: (patch: unknown) => void;
    mirror?: {
      logradouro?: string | null;
      numero?: string | null;
      complemento?: string | null;
      bairro?: string | null;
      cidade?: string | null;
      uf?: string | null;
      cep?: string | null;
    };
  },
) {
  const rtl = await import("@testing-library/react");
  const view = rtl.render(
    <ImovelEnderecoCard
      dados={dados(dadosOverride)}
      loading={false}
      saving={false}
      onSave={opts?.onSave ?? vi.fn()}
      mirror={opts?.mirror}
    />,
  );
  return { ...view, ...rtl };
}

describe("ImovelEnderecoCard", () => {
  it("pre-fills every stored override field, including the 159 additions", async () => {
    const { screen } = await render({
      endereco_manual_logradouro: "Alameda Alemanha",
      endereco_manual_numero: "535",
      endereco_manual_complemento: "Unidade 12",
      endereco_manual_bairro: "Euroville - Km 23",
      endereco_manual_cidade: "Barueri",
      endereco_manual_uf: "SP",
      endereco_manual_cep: "06355-465",
    });

    expect(
      (screen.getByTestId("imovel-endereco-manual-logradouro") as HTMLInputElement).value,
    ).toBe("Alameda Alemanha");
    expect(
      (screen.getByTestId("imovel-endereco-manual-complemento") as HTMLInputElement).value,
    ).toBe("Unidade 12");
    expect(
      (screen.getByTestId("imovel-endereco-manual-bairro") as HTMLInputElement).value,
    ).toBe("Euroville - Km 23");
    expect((screen.getByTestId("imovel-endereco-manual-cep") as HTMLInputElement).value).toBe(
      "06355-465",
    );
  });

  it("saves every field through the override PUT, blank fields as null", async () => {
    const onSave = vi.fn();
    const { screen, fireEvent } = await render(undefined, { onSave });

    fireEvent.change(screen.getByTestId("imovel-endereco-manual-logradouro"), {
      target: { value: "Alameda Alemanha" },
    });
    fireEvent.change(screen.getByTestId("imovel-endereco-manual-numero"), {
      target: { value: "535" },
    });
    fireEvent.click(screen.getByTestId("imovel-endereco-manual-salvar"));

    expect(onSave).toHaveBeenCalledWith({
      logradouro: "Alameda Alemanha",
      numero: "535",
      complemento: null,
      bairro: null,
      cidade: null,
      uf: null,
      cep: null,
    });
  });

  it("shows the CRM mirror value as the placeholder for the 159 fields too", async () => {
    const { screen } = await render(undefined, {
      mirror: { complemento: "535", bairro: "Centro", cep: "01000-000" },
    });

    expect(
      (screen.getByTestId("imovel-endereco-manual-complemento") as HTMLInputElement).placeholder,
    ).toBe("535");
    expect(
      (screen.getByTestId("imovel-endereco-manual-bairro") as HTMLInputElement).placeholder,
    ).toBe("Centro");
    expect(
      (screen.getByTestId("imovel-endereco-manual-cep") as HTMLInputElement).placeholder,
    ).toBe("01000-000");
  });

  it("renders with no mirror prop at all — the manual-layout case", async () => {
    const { screen } = await render();
    expect(screen.getByTestId("imovel-endereco-manual")).toBeTruthy();
  });
});
