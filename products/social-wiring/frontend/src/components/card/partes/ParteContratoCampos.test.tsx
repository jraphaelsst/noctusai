/**
 * ParteContratoCampos — a company party's NIRE + sede and a representante's
 * company (contrato-partes-CONTRACT §2, migration 193). Synthetic data only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { ParteEmpresaContratoForm, RepresentanteEmpresaSelect } from "./ParteContratoCampos";
import type { ParteItem } from "@/types/partes";

function pj(id: string, nome: string): ParteItem {
  return {
    parte_id: id, titular: false, rotulo: "Vendedor", lado: "vendedor", papel: "proprietario",
    ordem: 0, tipo_pessoa: "PJ", cliente_id: null, empresa_id: `e-${id}`, nome,
    documento: "11222333000181", observacao: null, cliente: null,
    empresa: { id: `e-${id}`, razao_social: nome, nome_fantasia: null, cnpj: "11222333000181", situacao_cadastral: null },
  };
}

describe("ParteEmpresaContratoForm", () => {
  const comDados = () => ({
    ...pj("p1", "Empresa Um Ltda"),
    pj_nire: "35200000001",
    pj_sede: {
      logradouro: "Rua Exemplo", numero: "7", complemento: null, bairro: "Centro",
      cidade: "Cotia", uf: "SP", cep: "06700000",
    },
  });

  it("🔴 opens PREFILLED from the party's list item and shows what is stored", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    render(<ParteEmpresaContratoForm parte={comDados()} salvando={false} onSalvar={vi.fn()} />);
    expect(screen.getByTestId("parte-empresa-contrato-resumo-p1").textContent).toContain("35200000001");
    expect(screen.queryByTestId("parte-empresa-contrato-faltam-p1")).toBeNull();
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-abrir-p1"));
    expect((screen.getByTestId("parte-empresa-pj_nire-p1") as HTMLInputElement).value).toBe("35200000001");
    expect((screen.getByTestId("parte-empresa-pj_sede_cidade-p1") as HTMLInputElement).value).toBe("Cotia");
    // Nothing changed ⇒ nothing to save.
    expect((screen.getByTestId("parte-empresa-contrato-salvar-p1") as HTMLButtonElement).disabled).toBe(true);
  });

  it("🔴 sends ONLY what changed — an emptied field as null, UF upper-cased", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onSalvar = vi.fn();
    render(<ParteEmpresaContratoForm parte={comDados()} salvando={false} onSalvar={onSalvar} />);
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-abrir-p1"));
    fireEvent.change(screen.getByTestId("parte-empresa-pj_sede_numero-p1"), { target: { value: "70" } });
    fireEvent.change(screen.getByTestId("parte-empresa-pj_sede_bairro-p1"), { target: { value: "" } });
    fireEvent.change(screen.getByTestId("parte-empresa-pj_sede_uf-p1"), { target: { value: "sp" } });
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-salvar-p1"));
    expect(onSalvar).toHaveBeenCalledWith({ pj_sede_numero: "70", pj_sede_bairro: null });
  });

  it("names what is still missing for the contract; mirrors the server's CEP 400", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    render(<ParteEmpresaContratoForm parte={pj("p1", "Empresa Um Ltda")} salvando={false} onSalvar={vi.fn()} />);
    expect(screen.getByTestId("parte-empresa-contrato-faltam-p1").textContent).toContain("NIRE");
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-abrir-p1"));
    fireEvent.change(screen.getByTestId("parte-empresa-pj_sede_cep-p1"), { target: { value: "0670" } });
    expect(screen.getByText("CEP da sede deve ter 8 dígitos.")).toBeTruthy();
    expect((screen.getByTestId("parte-empresa-contrato-salvar-p1") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("RepresentanteEmpresaSelect", () => {
  it("🔴 one representante per company — a taken company is disabled; picking sends its parte_id", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onChange = vi.fn();
    render(
      <RepresentanteEmpresaSelect
        parteId="r1"
        valor={null}
        empresas={[pj("pj1", "Empresa Um Ltda"), pj("pj2", "Empresa Dois Ltda")]}
        ocupadas={["pj1"]}
        salvando={false}
        onChange={onChange}
      />,
    );
    const select = screen.getByTestId("representa-select-r1") as HTMLSelectElement;
    const opcao = [...select.options].find((o) => o.value === "pj1") as HTMLOptionElement;
    expect(opcao.disabled).toBe(true);
    expect(opcao.textContent).toContain("já tem representante");
    fireEvent.change(select, { target: { value: "pj2" } });
    expect(onChange).toHaveBeenCalledWith("pj2");
  });

  it("says so when the side has no company to represent", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(<RepresentanteEmpresaSelect parteId="r1" valor={null} empresas={[]} ocupadas={[]} salvando={false} onChange={vi.fn()} />);
    expect(screen.getByTestId("representante-sem-empresa-r1")).toBeTruthy();
  });
});
