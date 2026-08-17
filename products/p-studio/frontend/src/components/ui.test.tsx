/**
 * Primitivas de UI.
 *
 * O foco é a `StatusBadge`: ela é a ponte entre o dicionário de tons e a
 * pintura real, e é onde uma etapa nova do backend apareceria como badge sem
 * cor nenhuma. O resto cobre o que a tela precisa que não quebre.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Badge, Button, Modal, StatCard, StatusBadge } from "@/components/ui";
import { CLASSES_STATUS, TOM_FINANCEIRO, TOM_PRODUCAO } from "@/lib/status";

describe("StatusBadge", () => {
  it("aplica as classes do tom pedido", () => {
    render(<StatusBadge tom="late">Atrasado</StatusBadge>);
    const badge = screen.getByText("Atrasado");
    for (const classe of CLASSES_STATUS.late.split(" ")) {
      expect(badge).toHaveClass(classe);
    }
  });

  it("o tom do status financeiro atrasado é o de alerta", () => {
    render(<StatusBadge tom={TOM_FINANCEIRO.atrasado}>Atrasado</StatusBadge>);
    expect(screen.getByText("Atrasado")).toHaveClass("text-status-late");
  });

  it("aceita classe extra sem perder a do tom", () => {
    render(
      <StatusBadge tom="received" className="ml-2">
        Recebido
      </StatusBadge>
    );
    const badge = screen.getByText("Recebido");
    expect(badge).toHaveClass("ml-2");
    expect(badge).toHaveClass("text-status-received");
  });

  it("todo tom de produção produz uma badge pintada", () => {
    for (const [etapa, tom] of Object.entries(TOM_PRODUCAO)) {
      const { unmount } = render(<StatusBadge tom={tom}>{etapa}</StatusBadge>);
      expect(screen.getByText(etapa).className).toContain("status-");
      unmount();
    }
  });
});

describe("Badge", () => {
  it("renderiza o conteúdo", () => {
    render(<Badge>Fotografia</Badge>);
    expect(screen.getByText("Fotografia")).toBeInTheDocument();
  });
});

describe("StatCard", () => {
  it("mostra rótulo e valor", () => {
    render(<StatCard label="Recebido" value="R$ 1.200,00" />);
    expect(screen.getByText("Recebido")).toBeInTheDocument();
    expect(screen.getByText("R$ 1.200,00")).toBeInTheDocument();
  });

  it("mostra a dica quando informada", () => {
    render(<StatCard label="Em aberto" value="R$ 800,00" hint="3 lançamentos" />);
    expect(screen.getByText("3 lançamentos")).toBeInTheDocument();
  });

  it("sem dica não renderiza sobra vazia", () => {
    const { container } = render(<StatCard label="Total" value="R$ 0,00" />);
    expect(container.querySelectorAll(".text-xs.text-muted-foreground")).toHaveLength(0);
  });
});

describe("Button", () => {
  it("dispara onClick", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Salvar</Button>);

    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("desabilitado não dispara", async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Salvar
      </Button>
    );

    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("Modal", () => {
  it("fechado não renderiza nada", () => {
    render(
      <Modal open={false} onClose={() => {}} title="Novo cliente">
        <p>corpo</p>
      </Modal>
    );
    expect(screen.queryByText("Novo cliente")).not.toBeInTheDocument();
  });

  it("aberto mostra título e corpo", () => {
    render(
      <Modal open onClose={() => {}} title="Novo cliente">
        <p>corpo</p>
      </Modal>
    );
    expect(screen.getByText("Novo cliente")).toBeInTheDocument();
    expect(screen.getByText("corpo")).toBeInTheDocument();
  });
});
