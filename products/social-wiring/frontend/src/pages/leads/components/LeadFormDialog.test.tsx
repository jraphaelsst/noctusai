/**
 * LeadFormDialog — the código the form has always shown now actually LANDS.
 *
 * 🔴 THE BUG THIS SUITE EXISTS FOR. The dialog has had a "Código do imóvel"
 * input since it shipped, bound to `codigo_raw` alone. `codigo_raw` is the
 * verbatim spelling and nothing joins on it; `leads.codigo_imovel` is the
 * column migration 062's trigger canonicalises into `codigo_imovel_norm`, and
 * that is what every imóvel-side join, every registry FK and the card's origin
 * affordance match on.
 *
 * So a manually-entered lead's código was recorded and then joined to nothing.
 * The backend had accepted `codigo_imovel` on create AND update the whole time
 * (`leads/schemas.py:91,114`) — only the request body dropped it, which is why
 * nothing anywhere errored.
 *
 * The same dialog backs the funil's "Novo lead" button, so both entry points
 * are covered by these assertions.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useLeadsSources", () => ({
  useLeadSources: () => ({ data: [], isPending: false }),
}));
vi.mock("@/hooks/useLeadsCorretores", () => ({
  useLeadCorretores: () => ({ data: [], isPending: false }),
}));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { LeadFormDialog } from "./LeadFormDialog";
import type { Lead } from "@/pages/leads/types";

async function abrir(lead?: Lead) {
  const rtl = await import("@testing-library/react");
  const onSubmit = vi.fn();
  const view = rtl.render(
    <LeadFormDialog
      open
      onOpenChange={vi.fn()}
      lead={lead ?? null}
      onSubmit={onSubmit}
    />,
  );
  return { ...rtl, ...view, onSubmit };
}

async function preencherCodigo(value: string) {
  const rtl = await import("@testing-library/react");
  const input = rtl.screen.getByTestId("lead-form-codigo");
  rtl.fireEvent.change(input, { target: { value } });
  return input;
}

async function salvar() {
  const rtl = await import("@testing-library/react");
  rtl.fireEvent.click(rtl.screen.getByTestId("lead-form-submit"));
}

describe("LeadFormDialog — o código do imóvel", () => {
  it("sends codigo_imovel, not only codigo_raw", async () => {
    const { onSubmit } = await abrir();

    await preencherCodigo("ONE10337");
    await salvar();

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const values = onSubmit.mock.calls[0][0];
    // 🔴 THE ASSERTION. Without it the field is decorative.
    expect(values.codigo_imovel).toBe("ONE10337");
  });

  it("keeps the raw spelling alongside it", async () => {
    const { onSubmit } = await abrir();

    // Lowercase on purpose: `codigo_raw` records what a person typed, and the
    // canonicalisation is the DB trigger's job — server-side, for every write
    // path including the portal webhooks. Upper-casing in the browser would be
    // a second definition of the same rule to keep in step.
    await preencherCodigo("one10337");
    await salvar();

    const values = onSubmit.mock.calls[0][0];
    expect(values.codigo_raw).toBe("one10337");
    expect(values.codigo_imovel).toBe("one10337");
  });

  it("sends null rather than an empty string when left blank", async () => {
    const { onSubmit } = await abrir();

    await salvar();

    const values = onSubmit.mock.calls[0][0];
    expect(values.codigo_imovel).toBeNull();
    expect(values.codigo_raw).toBeNull();
  });

  it("clearing the field clears both columns", async () => {
    const { onSubmit } = await abrir();

    await preencherCodigo("ONE10337");
    await preencherCodigo("");
    await salvar();

    const values = onSubmit.mock.calls[0][0];
    expect(values.codigo_imovel).toBeNull();
  });
});
