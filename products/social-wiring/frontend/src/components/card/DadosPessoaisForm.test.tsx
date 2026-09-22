/**
 * DadosPessoaisForm — the fields the checklist derives from.
 *
 * The assertions worth having here are about the GÊNERO DEFAULT, because that
 * is the one place this form can quietly lie. The dropdown shows "Masculino"
 * pre-selected as a convenience; if that counted as data before anyone saved,
 * the Gênero item would read green for every existing cliente the day it
 * shipped and could never again answer "who still needs checking" — the
 * permanently-GREEN twin of the permanently-red `nome_completo` bug migration
 * 068 had to fix.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

// This suite renders the same testids repeatedly; without an explicit cleanup
// the second render finds two of everything.
afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { DadosPessoaisForm } from "./DadosPessoaisForm";

async function abrir(props: Partial<Parameters<typeof DadosPessoaisForm>[0]> = {}) {
  const { fireEvent, render, screen } = await import("@testing-library/react");
  const onSave = vi.fn();
  render(
    <DadosPessoaisForm valores={{}} onSave={onSave} {...props} />,
  );
  fireEvent.click(screen.getByTestId("dados-pessoais-editar-btn"));
  return { onSave, fireEvent, screen };
}

describe("DadosPessoaisForm", () => {
  it("offers the fields in the checklist's own order", async () => {
    const { screen } = await abrir();
    const form = screen.getByTestId("dados-pessoais");
    const rotulos = Array.from(form.querySelectorAll("label")).map((l) =>
      l.textContent?.trim(),
    );
    // The sequence an operator actually collects details in — not alphabetical.
    //
    // 🔴 THE FIRST SIX ARE STILL THE CHECKLIST'S ORDER, and that is what this
    // test is for. Migration 097 appended the qualification block a contract
    // needs — CPF/RG (which ARE checklist items) and the civil-status and
    // address fields (which are not) — AFTER them, deliberately: the operator
    // still collects contact details first, and inserting a CPF box between
    // "Celular" and "Email" would reorder a form somebody uses daily.
    expect(rotulos).toEqual([
      "Nome Completo",
      "Celular",
      "Email",
      "Data de Nascimento",
      "Profissão",
      "Gênero",
      // Qualificação (097) — nome_oficial (071, human-editable since the
      // owner's 2026-09-19 directive) leads the block, same reasoning
      // migration 097's own header gives for CPF/RG leading it: these are
      // document-provenance identity fields, not contact details.
      "Nome completo (como no documento)",
      "CPF",
      "RG",
      "Órgão expedidor",
      "Nacionalidade",
      "Estado civil",
      "Regime de bens",
      // Migration 148 — always shown (required for a vendedor regardless
      // of estado civil). "Data de casamento" is absent here: it only
      // renders while estado_civil reads "Casado(a)", which this cliente
      // does not.
      "Certidão de estado civil — data de emissão (obrigatório para vendedores)",
      // Endereço (097)
      "CEP",
      "Logradouro",
      "Número",
      "Complemento",
      "Bairro",
      "Cidade",
      "UF",
    ]);
  });

  it("hides Data de casamento when estado civil is not Casado(a)", async () => {
    const { screen } = await abrir();
    expect(screen.queryByTestId("dados-pessoais-data-casamento")).toBeNull();
  });

  it("shows Data de casamento while estado civil reads Casado(a)", async () => {
    const { screen } = await abrir({ valores: { estado_civil: "Casado(a)" } });
    expect(screen.getByTestId("dados-pessoais-data-casamento")).toBeTruthy();
  });

  it("sends nome_oficial and certidao_estado_civil_emitida_em", async () => {
    const { onSave, fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-nome-oficial"), {
      target: { value: "Ana Maria da Silva" },
    });
    fireEvent.change(
      screen.getByTestId("dados-pessoais-certidao-estado-civil-emitida-em"),
      { target: { value: "2025-06-01" } },
    );
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        nome_oficial: "Ana Maria da Silva",
        certidao_estado_civil_emitida_em: "2025-06-01",
      }),
    );
  });

  it("🔴 sends the qualification fields Save was given", async () => {
    const { onSave, fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-cpf"), {
      target: { value: "412.954.238-98" },
    });
    fireEvent.change(screen.getByTestId("dados-pessoais-rg-orgao"), {
      target: { value: "SSP/SP" },
    });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        cpf: "412.954.238-98",
        rg_orgao_expedidor: "SSP/SP",
      }),
    );
  });

  it("uppercases the UF as it is typed", async () => {
    /* A two-letter state code is printed upper-case on every document this
       feeds, and normalising at the keystroke means the value stored matches
       the value compared. */
    const { onSave, fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-uf"), {
      target: { value: "sp" },
    });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ endereco_uf: "SP" }),
    );
  });

  it("🔴 writes nothing until Save is pressed", async () => {
    const { onSave, fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-profissao"), {
      target: { value: "Engenheiro" },
    });
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("🔴 sends Masculino only once the operator saves, never before", async () => {
    const { onSave, fireEvent, screen } = await abrir();
    // Pre-selected in the UI…
    expect(screen.getByTestId("dados-pessoais-genero").textContent).toContain(
      "Masculino",
    );
    // …but it is a convenience, not a value, until this click.
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave.mock.calls[0][0].genero).toBe("Masculino");
  });

  it("keeps an already-saved gênero rather than resetting it to the default", async () => {
    const { onSave, fireEvent, screen } = await abrir({
      valores: { genero: "Feminino" },
    });
    expect(screen.getByTestId("dados-pessoais-genero").textContent).toContain(
      "Feminino",
    );
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave.mock.calls[0][0].genero).toBe("Feminino");
  });

  it("sends an emptied field as null, not as an empty string", async () => {
    // A `""` would satisfy NOT NULL and tick the item for a value no human
    // would accept — the whitespace case the backend's `_preenchido` rejects.
    const { onSave, fireEvent, screen } = await abrir({
      valores: { profissao: "Engenheiro" },
    });
    fireEvent.change(screen.getByTestId("dados-pessoais-profissao"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave.mock.calls[0][0].profissao).toBeNull();
  });

  it("seeds the form from the current record", async () => {
    const { screen } = await abrir({
      valores: { nome_completo: "Luciano Mauricio", celular: "+5511999998888" },
    });
    expect(
      (screen.getByTestId("dados-pessoais-nome") as HTMLInputElement).value,
    ).toBe("Luciano Mauricio");
    expect(
      (screen.getByTestId("dados-pessoais-celular") as HTMLInputElement).value,
    ).toBe("+5511999998888");
  });
});

describe("DadosPessoaisForm — RG não pode ser igual ao CPF (migration 110)", () => {
  it("🔴 mostra o aviso ao vivo quando RG e CPF colapsam no mesmo documento", async () => {
    const { fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-cpf"), {
      target: { value: "412.954.238-98" },
    });
    expect(screen.queryByTestId("dados-pessoais-rg-igual-cpf")).toBeNull();
    fireEvent.change(screen.getByTestId("dados-pessoais-rg"), {
      // Same digits, different punctuation — the comparison is
      // punctuation-blind on both sides.
      target: { value: "412.954.238-98" },
    });
    expect(screen.getByTestId("dados-pessoais-rg-igual-cpf")).toBeTruthy();
  });

  it("não bloqueia o envio — é consultivo, quem recusa é o servidor", async () => {
    const { onSave, fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-cpf"), {
      target: { value: "41295423898" },
    });
    fireEvent.change(screen.getByTestId("dados-pessoais-rg"), {
      target: { value: "41295423898" },
    });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("some quando um dos dois deixa de bater", async () => {
    const { fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-cpf"), {
      target: { value: "41295423898" },
    });
    fireEvent.change(screen.getByTestId("dados-pessoais-rg"), {
      target: { value: "41295423898" },
    });
    expect(screen.getByTestId("dados-pessoais-rg-igual-cpf")).toBeTruthy();
    fireEvent.change(screen.getByTestId("dados-pessoais-rg"), {
      target: { value: "52.179.965-X" },
    });
    expect(screen.queryByTestId("dados-pessoais-rg-igual-cpf")).toBeNull();
  });
});

describe("DadosPessoaisForm — surfacing a rejected save (migration 110)", () => {
  it("🔴 mostra a mensagem do servidor mesmo depois do editor fechar", async () => {
    // `submit()` fecha o editor de imediato; a rejeição chega DEPOIS,
    // assíncrona — um caller que só mostrasse `saveError` enquanto aberto não
    // mostraria a ninguém.
    const { render, screen } = await import("@testing-library/react");
    const onSave = vi.fn();
    render(
      <DadosPessoaisForm
        valores={{}}
        onSave={onSave}
        saveError="[400] RG não pode ser igual ao CPF."
      />,
    );
    expect(screen.getByTestId("dados-pessoais-erro").textContent).toContain(
      "RG não pode ser igual ao CPF.",
    );
  });

  it("mostra o erro também enquanto o editor está aberto", async () => {
    const { screen } = await abrir({ saveError: "Não foi possível salvar os dados." });
    expect(screen.getByTestId("dados-pessoais-erro").textContent).toBe(
      "Não foi possível salvar os dados.",
    );
  });

  it("não mostra nada quando não há erro", async () => {
    const { screen } = await abrir();
    expect(screen.queryByTestId("dados-pessoais-erro")).toBeNull();
  });
});

describe("DadosPessoaisForm — pendente de confirmação do administrador (owner directive, 2026-09-19)", () => {
  it("mostra um aviso sob o campo cujo valor foi retido", async () => {
    const { screen } = await abrir({ pendenteConfirmacao: ["estado_civil"] });
    expect(screen.getByTestId("dados-pessoais-estado-civil-pendente")).toBeTruthy();
    // Nenhum outro campo mostra o aviso.
    expect(screen.queryByTestId("dados-pessoais-cpf-pendente")).toBeNull();
  });

  it("mostra o resumo mesmo com o editor fechado", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <DadosPessoaisForm
        valores={{}}
        onSave={vi.fn()}
        pendenteConfirmacao={["nome_oficial", "cpf"]}
      />,
    );
    const resumo = screen.getByTestId("dados-pessoais-pendente-resumo");
    expect(resumo.textContent).toContain("nome_oficial");
    expect(resumo.textContent).toContain("cpf");
  });

  it("não mostra nada quando não há pendência", async () => {
    const { screen } = await abrir();
    expect(screen.queryByTestId("dados-pessoais-pendente-resumo")).toBeNull();
    expect(screen.queryByTestId("dados-pessoais-cpf-pendente")).toBeNull();
  });
});
