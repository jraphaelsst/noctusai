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
    expect(rotulos).toEqual([
      "Nome Completo",
      "Celular",
      "Email",
      "Data de Nascimento",
      "Profissão",
      "Gênero",
    ]);
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
