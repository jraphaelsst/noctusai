/**
 * DadosPessoaisForm — the fields the checklist derives from.
 *
 * The assertions worth having here are about GÊNERO HAVING NO DEFAULT,
 * because that is the one place this form used to quietly lie: a pre-picked
 * "Masculino" read as answered on screen while the checklist (driven by the
 * same null column) correctly read it as missing, and confirming Save with
 * no interaction at all silently wrote "Masculino" onto a record nobody
 * ever stated the gênero of (live-tested, contract-gate audit, 2026-09-22).
 * The box now shows an empty "Selecione" placeholder for null and sends
 * exactly what the operator picked, never a default — the permanently-GREEN
 * twin of the permanently-red `nome_completo` bug migration 068 had to fix.
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
    //
    // 🔴 "Regime de bens" is ABSENT here (this slice) — `valores={}` means no
    // `estado_civil` is on file, and a regime is meaningless for a single
    // person. See the "casamento gates" describe block below for both sides
    // of that gate.
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

  describe("🔴 Regime de bens is conditioned on marriage (this slice)", () => {
    it("hides it when estado civil is not on file", async () => {
      const { screen } = await abrir();
      expect(screen.queryByTestId("dados-pessoais-regime-bens")).toBeNull();
    });

    it("hides it for a single person", async () => {
      const { screen } = await abrir({ valores: { estado_civil: "Solteiro(a)" } });
      expect(screen.queryByTestId("dados-pessoais-regime-bens")).toBeNull();
    });

    it("shows it while estado civil reads Casado(a)", async () => {
      const { screen } = await abrir({ valores: { estado_civil: "Casado(a)" } });
      expect(screen.getByTestId("dados-pessoais-regime-bens")).toBeTruthy();
    });

    it("shows it for União estável too — CC art. 1.647 covers both", async () => {
      const { screen } = await abrir({ valores: { estado_civil: "União estável" } });
      expect(screen.getByTestId("dados-pessoais-regime-bens")).toBeTruthy();
      // But NOT "Data de casamento" — a união estável has no casamento to date.
      expect(screen.queryByTestId("dados-pessoais-data-casamento")).toBeNull();
    });
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

  it("🔴 shows an empty placeholder for a null gênero, never a default", async () => {
    const { screen } = await abrir();
    expect(screen.getByTestId("dados-pessoais-genero").textContent).toContain(
      "Selecione",
    );
  });

  it("🔴 saving without touching gênero sends null, never Masculino", async () => {
    // `genero: null` — the realistic shape a record with no gênero ever
    // recorded arrives in (a DB column, not an absent JS key).
    const { onSave, fireEvent, screen } = await abrir({ valores: { genero: null } });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0].genero).toBeNull();
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

describe("DadosPessoaisForm — RG igual ao CPF é uma notícia, não um erro (CIN)", () => {
  it("🔴 mostra o aviso âmbar ao vivo quando RG e CPF colapsam no mesmo documento", async () => {
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
    const aviso = screen.getByTestId("dados-pessoais-rg-igual-cpf");
    expect(aviso.textContent).toContain("Carteira de Identidade Nacional");
    // Never `text-destructive` — this is informational, not a rejection.
    expect(aviso.className).not.toContain("text-destructive");
  });

  it("🔴 nunca bloqueia o envio — RG==CPF é normal para a CIN", async () => {
    const { onSave, fireEvent, screen } = await abrir();
    fireEvent.change(screen.getByTestId("dados-pessoais-cpf"), {
      target: { value: "41295423898" },
    });
    fireEvent.change(screen.getByTestId("dados-pessoais-rg"), {
      target: { value: "41295423898" },
    });
    fireEvent.click(screen.getByTestId("dados-pessoais-salvar"));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0].rg).toBe("41295423898");
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

describe("DadosPessoaisForm — RG == CPF nunca é sinalizado para a CIN (2026-09-23)", () => {
  it("🔴 some quando há uma CIN no cadastro", async () => {
    const { fireEvent, screen } = await abrir({ temCin: true });
    fireEvent.change(screen.getByTestId("dados-pessoais-cpf"), {
      target: { value: "448.864.938-66" },
    });
    fireEvent.change(screen.getByTestId("dados-pessoais-rg"), {
      target: { value: "448.864.938-66" },
    });
    expect(screen.queryByTestId("dados-pessoais-rg-igual-cpf")).toBeNull();
  });

  it("🔴 some quando o órgão expedidor é o IIGDR da CIN", async () => {
    const { fireEvent, screen } = await abrir({
      valores: { cpf: "448.864.938-66", rg: "448.864.938-66", rg_orgao_expedidor: "IIGDR-SP" },
    });
    expect(screen.queryByTestId("dados-pessoais-rg-igual-cpf")).toBeNull();
    fireEvent.change(screen.getByTestId("dados-pessoais-rg-orgao"), {
      target: { value: "SSP/SP" },
    });
    expect(screen.getByTestId("dados-pessoais-rg-igual-cpf")).toBeTruthy();
  });
});

describe("DadosPessoaisForm — surfacing a rejected save (migration 110)", () => {
  it("🔴 mostra a mensagem do servidor mesmo depois do editor fechar", async () => {
    // `submit()` fecha o editor de imediato; a rejeição chega DEPOIS,
    // assíncrona — um caller que só mostrasse `saveError` enquanto aberto não
    // mostraria a ninguém. RG==CPF is no longer a rejection example — the
    // server accepts it now — so a generic validation message stands in.
    const { render, screen } = await import("@testing-library/react");
    const onSave = vi.fn();
    render(
      <DadosPessoaisForm
        valores={{}}
        onSave={onSave}
        saveError="[400] CPF inválido."
      />,
    );
    expect(screen.getByTestId("dados-pessoais-erro").textContent).toContain(
      "CPF inválido.",
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
