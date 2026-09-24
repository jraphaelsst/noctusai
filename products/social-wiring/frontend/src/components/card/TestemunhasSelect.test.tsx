/**
 * TestemunhasSelect — the count selector + N registered-witness dropdowns
 * (migration 168). Coverage: count changes resize the slot list, a
 * "CPF pendente" registry row is disabled (never selectable), and a witness
 * picked in one slot is unavailable in every other slot (no duplicates).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// Same convention `ContratosPanel.test.tsx` takes for the Radix `Select`
// popover jsdom cannot model faithfully — inline every item, respect
// `disabled` so the no-duplicates/cpf-pendente assertions mean something.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-disabled": disabled, "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children, disabled }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        {
          type: "button",
          disabled,
          onClick: () => !disabled && ctx.onValueChange?.(value),
        },
        children,
      );
    },
  };
});

import { TestemunhasSelect } from "./TestemunhasSelect";
import type { Testemunha } from "@/hooks/useTestemunhas";

function testemunha(over: Partial<Testemunha> = {}): Testemunha {
  return {
    id: "t1",
    nome: "Maria Souza",
    cpf: "111.222.333-44",
    rg: null,
    celular: null,
    email: null,
    cpf_pendente: false,
    contratos_em_uso: 0,
    created_at: null,
    updated_at: null,
    ...over,
  };
}

async function render(props: Partial<Parameters<typeof TestemunhasSelect>[0]> = {}) {
  const { render: rtlRender } = await import("@testing-library/react");
  const onChangeQuantidade = vi.fn();
  const onChangeSlot = vi.fn();
  const utils = rtlRender(
    <TestemunhasSelect
      registro={[testemunha(), testemunha({ id: "t2", nome: "João Lima" })]}
      selecionados={[]}
      onChangeQuantidade={onChangeQuantidade}
      onChangeSlot={onChangeSlot}
      {...props}
    />,
  );
  return { ...utils, onChangeQuantidade, onChangeSlot };
}

describe("quantidade", () => {
  it("nenhum slot quando a quantidade é 0", async () => {
    const { getByText } = await render({ selecionados: [] });
    expect(getByText("Nenhuma testemunha selecionada.")).toBeTruthy();
  });

  it("um slot por unidade escolhida", async () => {
    const { getByTestId, queryByTestId } = await render({ selecionados: [null, null] });
    expect(getByTestId("testemunhas-slot-0")).toBeTruthy();
    expect(getByTestId("testemunhas-slot-1")).toBeTruthy();
    expect(queryByTestId("testemunhas-slot-2")).toBeNull();
  });

  it("🔴 só oferece de 2 a 5 testemunhas (decisão do dono, 2026-09-24)", async () => {
    const { getByTestId } = await render({ selecionados: [] });
    const seletor = getByTestId("testemunhas-quantidade").parentElement as HTMLElement;
    const opcoes = Array.from(seletor.querySelectorAll("button")).map((b) => b.textContent);
    expect(opcoes).toEqual(["2", "3", "4", "5"]);
  });

  it("mudar a quantidade chama onChangeQuantidade com o novo número", async () => {
    const { getByText, onChangeQuantidade } = await render({ selecionados: [] });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByText("2"));
    expect(onChangeQuantidade).toHaveBeenCalledWith(2);
  });
});

describe("CPF pendente nunca é selecionável", () => {
  it("uma testemunha com cpf_pendente aparece desabilitada em todo slot", async () => {
    const { getAllByText } = await render({
      registro: [testemunha({ cpf_pendente: true })],
      selecionados: [null],
    });
    const opcao = getAllByText(/CPF pendente/)[0].closest("button") as HTMLButtonElement;
    expect(opcao.disabled).toBe(true);
  });
});

describe("sem duplicatas", () => {
  it("uma testemunha já escolhida em outro slot fica desabilitada aqui", async () => {
    const { getAllByText } = await render({ selecionados: ["t1", null] });
    // Slot 1's "Maria Souza" option (already chosen in slot 0) is disabled.
    const opcoes = getAllByText("Maria Souza");
    const botaoSlot1 = opcoes[opcoes.length - 1].closest("button") as HTMLButtonElement;
    expect(botaoSlot1.disabled).toBe(true);
  });

  it("escolher uma testemunha em um slot chama onChangeSlot com o índice certo", async () => {
    const { getAllByText, onChangeSlot } = await render({ selecionados: [null, null] });
    const { fireEvent } = await import("@testing-library/react");
    const opcoes = getAllByText("João Lima");
    fireEvent.click(opcoes[0]);
    expect(onChangeSlot).toHaveBeenCalledWith(0, "t2");
  });
});

describe("testemunha removida do cadastro", () => {
  it("continua no slot que já a tinha, mas não pode ser escolhida em outro", async () => {
    const { getAllByText } = await render({
      registro: [testemunha({ excluida: true }), testemunha({ id: "t2", nome: "João Lima" })],
      selecionados: ["t1", null],
    });
    const opcoes = getAllByText(/Maria Souza — removida do cadastro/);
    const noProprioSlot = opcoes[0].closest("button") as HTMLButtonElement;
    const noOutroSlot = opcoes[1].closest("button") as HTMLButtonElement;
    expect(noProprioSlot.disabled).toBe(false);
    expect(noOutroSlot.disabled).toBe(true);
  });
});
