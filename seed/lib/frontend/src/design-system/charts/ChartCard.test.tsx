/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ChartCard } from "./ChartCard";

afterEach(cleanup);

describe("ChartCard", () => {
  it("renders the title/subtitle and the success-state children", () => {
    render(
      <ChartCard title="Evolução mensal" subtitle="Últimos 12 meses">
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByText("Evolução mensal")).toBeInTheDocument();
    expect(screen.getByText("Últimos 12 meses")).toBeInTheDocument();
    expect(screen.getByText("chart body")).toBeInTheDocument();
  });

  it("shows a loading skeleton and hides children while loading", () => {
    render(
      <ChartCard title="X" loading>
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByRole("status", { name: "Carregando" })).toBeInTheDocument();
    expect(screen.queryByText("chart body")).not.toBeInTheDocument();
  });

  it("shows the error message and hides children on error", () => {
    render(
      <ChartCard title="X" error="Falha ao carregar">
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Falha ao carregar");
    expect(screen.queryByText("chart body")).not.toBeInTheDocument();
  });

  it("shows the default empty message when isEmpty and no override is given", () => {
    render(
      <ChartCard title="X" isEmpty>
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByText("Sem dados para o período selecionado.")).toBeInTheDocument();
    expect(screen.queryByText("chart body")).not.toBeInTheDocument();
  });

  it("respects a custom emptyMessage", () => {
    render(
      <ChartCard title="X" isEmpty emptyMessage="Nada por aqui ainda.">
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByText("Nada por aqui ainda.")).toBeInTheDocument();
  });

  it("renders the actions slot in the header", () => {
    render(
      <ChartCard title="X" actions={<button>Ver detalhes</button>}>
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByRole("button", { name: "Ver detalhes" })).toBeInTheDocument();
  });

  it("prioritizes loading over error/empty when multiple flags are set", () => {
    render(
      <ChartCard title="X" loading error="boom" isEmpty>
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByRole("status", { name: "Carregando" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // REGRESSION for the refetch-unmount bug (`KB § PATTERNS/frontend/
  // lying-loading-state.md`). A consumer's `isPending || isFetching` flips
  // `loading` back to `true` on every background refetch even though
  // `children` already reflects valid (possibly stale) data. Before this
  // fix `loading ? skeleton : ...` blanked the chart back to a skeleton on
  // every refetch; now the organ remembers it has shown real content once
  // and keeps rendering it.
  it("REGRESSION: keeps showing chart children through a background refetch (loading flips true again after data has rendered)", () => {
    const { rerender } = render(
      <ChartCard title="X">
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByText("chart body")).toBeInTheDocument();

    rerender(
      <ChartCard title="X" loading>
        <div>chart body</div>
      </ChartCard>,
    );
    expect(screen.getByText("chart body")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Carregando" })).not.toBeInTheDocument();
  });
});
