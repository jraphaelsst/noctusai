/** ConsentDocLayout `brand` seam: default shell unchanged; brand mode swaps it. */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ConsentDocLayout } from "../src/pages/consent/ConsentDocLayout";
import { PRIVACY_POLICY } from "../src/content/consent";

const orgDoc = {
  title: "Aviso de privacidade",
  intro: "Como a Empresa Exemplo trata seus dados.",
  sections: [{ n: "1", title: "Controlador", blocks: [{ p: "Empresa Exemplo." }] }],
};

describe("ConsentDocLayout brand seam", () => {
  it("default (no brand) keeps the NoctusAI mark, doc switcher and DPO block", () => {
    render(
      <MemoryRouter>
        <ConsentDocLayout doc={PRIVACY_POLICY} />
      </MemoryRouter>,
    );
    expect(screen.getByText("AI")).toBeTruthy();
    expect(screen.getByLabelText("Documentos")).toBeTruthy();
    expect(screen.getAllByText("Encarregado (DPO) e contato").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("consent-brand")).toBeNull();
  });

  it("brand mode shows the org name and drops the NoctusAI shell", () => {
    render(
      <MemoryRouter>
        <ConsentDocLayout
          doc={orgDoc}
          brand={{
            name: "Empresa Exemplo",
            meta: [{ label: "Versão", value: "2" }],
            contact: { title: "Contato", lines: [{ label: "E-mail", value: "a@b.com", href: "mailto:a@b.com" }] },
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("consent-brand").textContent).toBe("Empresa Exemplo");
    expect(screen.queryByLabelText("Documentos")).toBeNull();
    expect(screen.queryAllByText("Encarregado (DPO) e contato")).toHaveLength(0);
    expect(screen.queryByText(/NoctusAI/)).toBeNull();
    expect(screen.getByText("Versão:")).toBeTruthy();
    expect(screen.getByText("Contato")).toBeTruthy();
  });
});
