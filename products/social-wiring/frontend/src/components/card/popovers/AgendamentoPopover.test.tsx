/**
 * AgendamentoPopover — the Agendar button.
 *
 * This file exists for ONE assertion: "Visita" is no longer offered here
 * (migration 082). A visit belongs to a ROTEIRO, which can hold several
 * properties, keep them in order, print a cronograma and record whether each
 * one happened — none of which an agendamento can do. Offering "Visita" here
 * would hand the user the weaker of two things under the better name.
 *
 * The paired assertion lives in `ClienteCardDialog.test.tsx`: a live row with
 * `tipo='visita'` must STILL render as "Visita". The value stays legal, the
 * button just stops offering it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { AgendamentoPopover, TIPO_OPTIONS } from "./AgendamentoPopover";

async function render(props: Partial<React.ComponentProps<typeof AgendamentoPopover>> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(
    React.createElement(AgendamentoPopover, {
      open: true,
      onOpenChange: vi.fn(),
      onCreate: vi.fn(),
      ...props,
    }),
  );
}

describe("AgendamentoPopover — Visita moved to Roteiros", () => {
  it("🔴 no longer offers Visita", async () => {
    expect(TIPO_OPTIONS.map((o) => o.value)).not.toContain("visita");
  });

  it("still offers the other three", async () => {
    expect(TIPO_OPTIONS.map((o) => o.value)).toEqual(["ligacao", "reuniao", "outro"]);
  });

  it("defaults to ligação, not to a type that no longer exists here", async () => {
    const { getByTestId } = await render();
    expect((getByTestId("agendamento-tipo") as HTMLSelectElement).value).toBe("ligacao");
  });

  it("never submits tipo=visita", async () => {
    const onCreate = vi.fn();
    const { getByTestId } = await render({ onCreate });
    const rtl = await import("@testing-library/react");

    rtl.fireEvent.change(getByTestId("agendamento-quando"), {
      target: { value: "2026-09-01T13:00" },
    });
    rtl.fireEvent.click(getByTestId("agendamento-salvar"));

    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate.mock.calls[0][0].tipo).not.toBe("visita");
  });
});
