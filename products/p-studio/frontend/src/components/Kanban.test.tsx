/**
 * Kanban com arrastar-para-avançar.
 *
 * No protótipo o kanban era só leitura — o layout existia, mas soltar o
 * cartão não fazia nada. Aqui `onMover` bate na rota `/etapa`, então a regra
 * que importa é *quando* ele é chamado: soltar na própria coluna não pode
 * disparar um PATCH inútil, e sem `onMover` o quadro volta a ser leitura.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { Kanban, type ColunaKanban } from "@/components/Kanban";
import { TOM_PRODUCAO } from "@/lib/status";

interface Card {
  id: string;
  titulo: string;
  etapa: string;
  valor: number;
}

const COLUNAS: ColunaKanban[] = [
  { id: "agendado", label: "Agendado" },
  { id: "edicao", label: "Edição" },
  { id: "entregue", label: "Entregue" },
];

const ITENS: Card[] = [
  { id: "a", titulo: "Cobertura Atlântica", etapa: "agendado", valor: 1000 },
  { id: "b", titulo: "Apto Jardins", etapa: "edicao", valor: 500 },
  { id: "c", titulo: "Casa Alphaville", etapa: "edicao", valor: 250 },
];

function montar(props: Partial<React.ComponentProps<typeof Kanban<Card>>> = {}) {
  const onMover = vi.fn();
  render(
    <Kanban<Card>
      colunas={COLUNAS}
      itens={ITENS}
      etapaDoItem={(i) => i.etapa}
      tomDaEtapa={(e) => TOM_PRODUCAO[e]}
      renderCard={(i) => <div data-testid={`card-${i.id}`}>{i.titulo}</div>}
      onMover={onMover}
      {...props}
    />
  );
  return { onMover };
}

/** Coluna inteira (cabeçalho + dropzone) a partir do rótulo. */
function coluna(label: string): HTMLElement {
  return screen.getByText(label).closest("div.shrink-0") as HTMLElement;
}

/** Dropzone da coluna — o irmão do cabeçalho. */
function dropzone(label: string): HTMLElement {
  return coluna(label).querySelector("div.min-h-24") as HTMLElement;
}

describe("Kanban", () => {
  it("renderiza uma coluna por etapa", () => {
    montar();
    for (const c of COLUNAS) expect(screen.getByText(c.label)).toBeInTheDocument();
  });

  it("distribui os cartões na coluna da própria etapa", () => {
    montar();
    expect(within(coluna("Agendado")).getByTestId("card-a")).toBeInTheDocument();
    expect(within(coluna("Edição")).getByTestId("card-b")).toBeInTheDocument();
    expect(within(coluna("Edição")).getByTestId("card-c")).toBeInTheDocument();
  });

  it("mostra a contagem por coluna", () => {
    montar();
    expect(within(coluna("Edição")).getByText("2")).toBeInTheDocument();
    expect(within(coluna("Agendado")).getByText("1")).toBeInTheDocument();
  });

  it("coluna vazia mostra o marcador em vez de ficar em branco", () => {
    montar();
    expect(within(coluna("Entregue")).getByText("Vazio")).toBeInTheDocument();
  });

  it("renderiza o total da coluna quando informado", () => {
    montar({
      totalDaColuna: (itens) => `R$ ${itens.reduce((s, i) => s + i.valor, 0)}`,
    });
    expect(within(coluna("Edição")).getByText("R$ 750")).toBeInTheDocument();
  });

  it("arrastar para outra coluna chama onMover com o item e a etapa nova", () => {
    const { onMover } = montar();

    const card = screen.getByTestId("card-a").parentElement!;
    fireEvent.dragStart(card);
    fireEvent.dragOver(dropzone("Edição"));
    fireEvent.drop(dropzone("Edição"));

    expect(onMover).toHaveBeenCalledTimes(1);
    expect(onMover).toHaveBeenCalledWith(ITENS[0], "edicao");
  });

  it("soltar na própria coluna não dispara PATCH", () => {
    const { onMover } = montar();

    const card = screen.getByTestId("card-b").parentElement!;
    fireEvent.dragStart(card);
    fireEvent.dragOver(dropzone("Edição"));
    fireEvent.drop(dropzone("Edição"));

    expect(onMover).not.toHaveBeenCalled();
  });

  it("soltar sem ter arrastado nada é inofensivo", () => {
    const { onMover } = montar();
    fireEvent.drop(dropzone("Entregue"));
    expect(onMover).not.toHaveBeenCalled();
  });

  it("dragEnd cancela o arrasto — soltar depois não move", () => {
    const { onMover } = montar();

    const card = screen.getByTestId("card-a").parentElement!;
    fireEvent.dragStart(card);
    fireEvent.dragEnd(card);
    fireEvent.drop(dropzone("Entregue"));

    expect(onMover).not.toHaveBeenCalled();
  });

  it("sem onMover os cartões não são arrastáveis", () => {
    render(
      <Kanban<Card>
        colunas={COLUNAS}
        itens={ITENS}
        etapaDoItem={(i) => i.etapa}
        tomDaEtapa={(e) => TOM_PRODUCAO[e]}
        renderCard={(i) => <div data-testid={`card-${i.id}`}>{i.titulo}</div>}
      />
    );
    const card = screen.getByTestId("card-a").parentElement!;
    expect(card).not.toHaveAttribute("draggable", "true");
  });

  it("sem onMover soltar não quebra", () => {
    render(
      <Kanban<Card>
        colunas={COLUNAS}
        itens={ITENS}
        etapaDoItem={(i) => i.etapa}
        tomDaEtapa={(e) => TOM_PRODUCAO[e]}
        renderCard={(i) => <div data-testid={`card-${i.id}`}>{i.titulo}</div>}
      />
    );
    expect(() => fireEvent.drop(dropzone("Edição"))).not.toThrow();
  });

  it("pinta a bolinha da coluna com a cor do tom da etapa", () => {
    montar();
    const bolinha = coluna("Entregue").querySelector("span.rounded-full") as HTMLElement;
    // TOM_PRODUCAO.entregue === "delivered"
    expect(bolinha.style.backgroundColor).toContain("--status-delivered");
  });

  it("lista vazia ainda desenha todas as colunas", () => {
    render(
      <Kanban<Card>
        colunas={COLUNAS}
        itens={[]}
        etapaDoItem={(i) => i.etapa}
        tomDaEtapa={(e) => TOM_PRODUCAO[e]}
        renderCard={(i) => <div>{i.titulo}</div>}
      />
    );
    expect(screen.getAllByText("Vazio")).toHaveLength(3);
  });
});
