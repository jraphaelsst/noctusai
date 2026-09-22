/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Card, EmptyState, ErrorState, Field, FormError, Select, Textarea } from "./FormControls";

afterEach(() => {
  cleanup();
});

describe("Card", () => {
  it("renders children and the card token classes", () => {
    render(<Card data-testid="card">conteúdo</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveTextContent("conteúdo");
    expect(card).toHaveClass("rounded-lg", "border", "bg-card");
  });

  it("merges a custom className", () => {
    render(
      <Card data-testid="card" className="custom-class">
        x
      </Card>,
    );
    expect(screen.getByTestId("card")).toHaveClass("custom-class");
  });
});

describe("Textarea", () => {
  it("defaults to 4 rows", () => {
    render(<Textarea aria-label="notas" />);
    expect(screen.getByRole("textbox", { name: "notas" })).toHaveAttribute("rows", "4");
  });

  it("applies the monospace variant", () => {
    render(<Textarea aria-label="json" monospace />);
    expect(screen.getByRole("textbox", { name: "json" })).toHaveClass("font-mono", "text-xs");
  });

  it("does not apply monospace classes by default", () => {
    render(<Textarea aria-label="texto" />);
    expect(screen.getByRole("textbox", { name: "texto" })).not.toHaveClass("font-mono");
  });
});

describe("Select", () => {
  it("renders its option children", () => {
    render(
      <Select aria-label="categoria">
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>,
    );
    const select = screen.getByRole("combobox", { name: "categoria" });
    expect(select).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "A" })).toBeInTheDocument();
  });
});

describe("Field", () => {
  it("renders the label, required marker, children, and error", () => {
    render(
      <Field label="Nome" required error="obrigatório">
        <input aria-label="Nome" />
      </Field>,
    );
    expect(screen.getByText("Nome")).toBeInTheDocument();
    expect(screen.getByText("*")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toBeInTheDocument();
    expect(screen.getByText("obrigatório")).toBeInTheDocument();
  });

  it("omits the required marker and error when not provided", () => {
    render(
      <Field label="Nome">
        <input aria-label="Nome" />
      </Field>,
    );
    expect(screen.queryByText("*")).not.toBeInTheDocument();
  });
});

describe("FormError", () => {
  it("renders nothing when message is null", () => {
    const { container } = render(<FormError message={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an alert with the message when set", () => {
    render(<FormError message="Falha ao salvar" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Falha ao salvar");
  });
});

describe("EmptyState", () => {
  it("renders the message with no alert role", () => {
    render(<EmptyState message="Nada por aqui" />);
    expect(screen.getByText("Nada por aqui")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("renders the message as an alert", () => {
    render(<ErrorState message="Erro ao carregar" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Erro ao carregar");
  });
});
