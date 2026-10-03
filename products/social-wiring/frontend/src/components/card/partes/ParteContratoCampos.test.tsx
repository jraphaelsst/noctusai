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
  it("🔴 sends ONLY the fields typed (a blank never clears a stored value), UF upper-cased", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onSalvar = vi.fn();
    render(<ParteEmpresaContratoForm parteId="p1" salvando={false} onSalvar={onSalvar} />);
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-abrir-p1"));
    fireEvent.change(screen.getByTestId("parte-empresa-pj_nire-p1"), { target: { value: "35200000001" } });
    fireEvent.change(screen.getByTestId("parte-empresa-pj_sede_uf-p1"), { target: { value: "sp" } });
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-salvar-p1"));
    expect(onSalvar).toHaveBeenCalledWith({ pj_nire: "35200000001", pj_sede_uf: "SP" });
  });

  it("mirrors the server's UF / CEP 400s", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    render(<ParteEmpresaContratoForm parteId="p1" salvando={false} onSalvar={vi.fn()} />);
    fireEvent.click(screen.getByTestId("parte-empresa-contrato-abrir-p1"));
    fireEvent.change(screen.getByTestId("parte-empresa-pj_sede_cep-p1"), { target: { value: "0670" } });
    expect(screen.getByText("CEP da sede deve ter 8 dígitos.")).toBeTruthy();
    expect((screen.getByTestId("parte-empresa-contrato-salvar-p1") as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows what the last save returned", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ParteEmpresaContratoForm
        parteId="p1"
        salvando={false}
        onSalvar={vi.fn()}
        salvo={{ id: "p1", pj_nire: "35200000001", pj_sede_logradouro: "Rua X", pj_sede_numero: "7", pj_sede_cidade: "Cotia", pj_sede_uf: "SP" }}
      />,
    );
    expect(screen.getByTestId("parte-empresa-contrato-salvo-p1").textContent).toContain("35200000001");
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
