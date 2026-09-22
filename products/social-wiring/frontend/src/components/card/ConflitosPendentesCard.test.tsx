/**
 * ConflitosPendentesCard.test.tsx — the admin decide surface (owner
 * directive, 2026-09-19). Presentational: everything is driven by props,
 * no hooks, no query client.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { ConflitosPendentesCard } from "./ConflitosPendentesCard";

const PENDENTE = {
  id: "c1",
  cliente_id: "cli-1",
  campo: "estado_civil",
  valor_anterior: "Casado(a)",
  origem_anterior: "certidao_casamento",
  valor_proposto: "Solteiro(a)",
  origem_proposto: "manual",
  confianca_proposta: null,
  status: "pendente" as const,
  created_at: "2026-09-20T00:00:00Z",
};

describe("ConflitosPendentesCard", () => {
  it("renders nothing when there are no pending conflicts", async () => {
    const { render } = await import("@testing-library/react");
    const { container } = render(
      <ConflitosPendentesCard conflitos={[]} onDecidir={vi.fn()} isAdmin />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when every conflict is already decided", async () => {
    const { render } = await import("@testing-library/react");
    const { container } = render(
      <ConflitosPendentesCard
        conflitos={[{ ...PENDENTE, status: "aceito" }]}
        onDecidir={vi.fn()}
        isAdmin
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the field label, prior and proposed values", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ConflitosPendentesCard conflitos={[PENDENTE]} onDecidir={vi.fn()} isAdmin />,
    );
    expect(screen.getByText("Estado civil")).toBeTruthy();
    expect(screen.getByText(/Casado\(a\)/)).toBeTruthy();
    expect(screen.getByText(/Solteiro\(a\)/)).toBeTruthy();
  });

  it("falls back to the raw campo key for an unlabeled field", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ConflitosPendentesCard
        conflitos={[{ ...PENDENTE, campo: "algo_novo" }]}
        onDecidir={vi.fn()}
        isAdmin
      />,
    );
    expect(screen.getByText("algo_novo")).toBeTruthy();
  });

  it("a non-admin sees the list but never the decide buttons", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ConflitosPendentesCard
        conflitos={[PENDENTE]}
        onDecidir={vi.fn()}
        isAdmin={false}
        testId="cx"
      />,
    );
    expect(screen.getByText("Estado civil")).toBeTruthy();
    expect(screen.queryByTestId("cx-item-c1-aprovar")).toBeNull();
    expect(screen.queryByTestId("cx-item-c1-rejeitar")).toBeNull();
  });

  it("an admin sees Aprovar/Rejeitar and they call onDecidir with the right args", async () => {
    const { render, screen, fireEvent } = await import("@testing-library/react");
    const onDecidir = vi.fn();
    render(
      <ConflitosPendentesCard
        conflitos={[PENDENTE]}
        onDecidir={onDecidir}
        isAdmin
        testId="cx"
      />,
    );
    fireEvent.click(screen.getByTestId("cx-item-c1-aprovar"));
    expect(onDecidir).toHaveBeenCalledWith("c1", true);
    fireEvent.click(screen.getByTestId("cx-item-c1-rejeitar"));
    expect(onDecidir).toHaveBeenCalledWith("c1", false);
  });

  it("disables both buttons for the row currently being decided", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ConflitosPendentesCard
        conflitos={[PENDENTE]}
        onDecidir={vi.fn()}
        isAdmin
        decidingId="c1"
        testId="cx"
      />,
    );
    expect((screen.getByTestId("cx-item-c1-aprovar") as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByTestId("cx-item-c1-rejeitar") as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("mostrarCliente shows which person a row is about", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { rerender } = render(
      <ConflitosPendentesCard conflitos={[PENDENTE]} onDecidir={vi.fn()} isAdmin />,
    );
    expect(screen.queryByText("cli-1")).toBeNull();

    rerender(
      <ConflitosPendentesCard
        conflitos={[PENDENTE]}
        onDecidir={vi.fn()}
        isAdmin
        mostrarCliente
      />,
    );
    expect(screen.getByText("cli-1")).toBeTruthy();
  });

  it("mostrarCliente prefers a resolved name over the raw id", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ConflitosPendentesCard
        conflitos={[PENDENTE]}
        onDecidir={vi.fn()}
        isAdmin
        mostrarCliente
        nomeDoCliente={(id) => (id === "cli-1" ? "Ana Silva" : undefined)}
      />,
    );
    expect(screen.getByText("Ana Silva")).toBeTruthy();
  });

  it("filters out already-decided conflicts from a mixed list", async () => {
    const { render, screen } = await import("@testing-library/react");
    render(
      <ConflitosPendentesCard
        conflitos={[PENDENTE, { ...PENDENTE, id: "c2", campo: "cpf", status: "aceito" }]}
        onDecidir={vi.fn()}
        isAdmin
      />,
    );
    expect(screen.getByText("Estado civil")).toBeTruthy();
    expect(screen.queryByText("CPF")).toBeNull();
  });
});
