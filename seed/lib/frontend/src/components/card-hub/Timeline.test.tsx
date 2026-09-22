// Ported from `products/social-wiring/frontend/src/components/card/Timeline.test.tsx`
// (seed card hub, wave-a Slice C); SW's `touch`-kind cases stay with SW's renderer.
/**
 * Timeline.test.tsx — D9's "everything, one thread": four states (loading /
 * empty / error / success), and the forward-compat rule that an unknown
 * `kind` renders a graceful generic entry rather than crashing or vanishing
 * (Phase 2b's conversation kinds land on this slot untested here, but the
 * union's escape hatch must already hold).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TimelineEntry } from "./types";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { DEFAULT_TIMELINE_RENDERERS, GENERIC_TIMELINE_RENDERERS, Timeline } from "./Timeline";

async function render(props: React.ComponentProps<typeof Timeline>) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(Timeline, props));
}

describe("Timeline — four states", () => {
  it("shows a loading skeleton, never the empty state, while loading", async () => {
    const { getByTestId, queryByTestId } = await render({ entries: [], loading: true });
    expect(getByTestId("timeline-loading")).toBeTruthy();
    expect(queryByTestId("timeline-empty")).toBeNull();
  });

  it("shows the error state, taking precedence over empty", async () => {
    const { getByTestId } = await render({ entries: [], loading: false, error: "boom" });
    expect(getByTestId("timeline-error")).toBeTruthy();
  });

  it("shows empty only when truly empty and not loading/erroring", async () => {
    const { getByTestId } = await render({ entries: [], loading: false, error: null });
    expect(getByTestId("timeline-empty")).toBeTruthy();
  });

  it("renders one row per entry, newest-first order as given", async () => {
    const entries: TimelineEntry[] = [
      {
        id: "e1",
        kind: "nota",
        ocorrido_em: "2026-08-18T10:00:00Z",
        ator: { id: "u1", nome: "Rapha Souza" },
        corpo: "Ligar amanhã",
        autor: { id: "u1", nome: "Rapha Souza" },
        editado_em: null,
        deleted_at: null,
      },
      {
        id: "e2",
        kind: "sistema",
        ocorrido_em: "2026-08-17T10:00:00Z",
        ator: null,
        evento: "Cartão criado",
        detalhe: null,
      },
    ];
    const { getAllByTestId, getByText } = await render({
      entries,
      loading: false,
      renderers: { ...DEFAULT_TIMELINE_RENDERERS, ...GENERIC_TIMELINE_RENDERERS },
    });
    expect(getAllByTestId("timeline-entry")).toHaveLength(2);
    expect(getByText(/Ligar amanhã/)).toBeTruthy();
    expect(getByText(/Cartão criado/)).toBeTruthy();
  });
});

describe("Timeline — unknown kind forward-compat (Phase 2b slot)", () => {
  it("renders a generic entry for an unrecognised kind instead of crashing or dropping it", async () => {
    const entries: TimelineEntry[] = [
      {
        id: "e3",
        kind: "whatsapp_mensagem" as any,
        ocorrido_em: "2026-08-18T11:00:00Z",
        ator: { id: "u2", nome: "Cliente" },
        texto: "Oi, tudo bem?",
      } as TimelineEntry,
    ];
    const { getAllByTestId, getByTestId } = await render({ entries, loading: false });
    expect(getAllByTestId("timeline-entry")).toHaveLength(1);
    expect(getByTestId("timeline-entry-unknown-kind").textContent).toContain("whatsapp_mensagem");
  });
});

describe("Timeline — pagination", () => {
  it("shows a Carregar mais button only when hasMore is true, and fires onLoadMore", async () => {
    const onLoadMore = vi.fn();
    const entries: TimelineEntry[] = [
      {
        id: "e1",
        kind: "sistema",
        ocorrido_em: "2026-08-17T10:00:00Z",
        ator: null,
        evento: "Cartão criado",
        detalhe: null,
      },
    ];
    const { getByText } = await render({ entries, loading: false, hasMore: true, onLoadMore });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByText("Carregar mais"));
    expect(onLoadMore).toHaveBeenCalledOnce();
  });
});

describe("Timeline — lying-loading-state rule", () => {
  it("🔴 keeps existing entries mounted while a refetch is in flight", async () => {
    const entries: TimelineEntry[] = [
      {
        id: "e1",
        kind: "documento",
        ocorrido_em: "2026-08-17T10:00:00Z",
        ator: null,
        nome_original: "rg.pdf",
        mime_type: "application/pdf",
        tamanho_bytes: 10,
      },
    ];
    const { getAllByTestId, queryByTestId } = await render({ entries, loading: true });
    expect(getAllByTestId("timeline-entry")).toHaveLength(1);
    expect(queryByTestId("timeline-loading")).toBeNull();
  });
});

describe("Timeline — kind-renderer registry", () => {
  const sistema: TimelineEntry = {
    id: "s1",
    kind: "sistema",
    ocorrido_em: "2026-08-17T10:00:00Z",
    ator: null,
    evento: "Cartão criado",
    detalhe: "via import",
  };

  it("the seed default registry covers the seed gatherers (nota, documento, checklist)", () => {
    expect(Object.keys(DEFAULT_TIMELINE_RENDERERS).sort()).toEqual(["checklist", "documento", "nota"]);
  });

  it("🔴 a kind outside the registry falls back — it is never dropped", async () => {
    const { getAllByTestId, getByTestId } = await render({ entries: [sistema], loading: false });
    expect(getAllByTestId("timeline-entry")).toHaveLength(1);
    expect(getByTestId("timeline-entry").textContent).toContain("Evento (sistema)");
    expect(getByTestId("timeline-entry-unknown-kind").textContent).toBe("(sistema)");
  });

  it("an opted-in generic renderer summarises its kind", async () => {
    const { getByTestId, queryByTestId } = await render({
      entries: [sistema],
      loading: false,
      renderers: { ...DEFAULT_TIMELINE_RENDERERS, ...GENERIC_TIMELINE_RENDERERS },
    });
    expect(getByTestId("timeline-entry").textContent).toContain("Cartão criado — via import");
    expect(queryByTestId("timeline-entry-unknown-kind")).toBeNull();
  });

  it("a product registers its own kind without touching the seed", async () => {
    const { Zap } = await import("lucide-react");
    const { getByTestId } = await render({
      entries: [
        { id: "t1", kind: "touch", ocorrido_em: "2026-07-29T13:15:00Z", ator: null, origem_rotulo: "OLX" } as TimelineEntry,
      ],
      loading: false,
      renderers: {
        ...DEFAULT_TIMELINE_RENDERERS,
        touch: { icon: Zap, summary: (e: { origem_rotulo: string }) => `Novo contato via ${e.origem_rotulo}` },
      },
    });
    expect(getByTestId("timeline-entry").textContent).toContain("Novo contato via OLX");
    expect(getByTestId("timeline-entry").getAttribute("data-kind")).toBe("touch");
  });

  it("a movimento renders its stage transition", async () => {
    const { getByTestId } = await render({
      entries: [
        { id: "m1", kind: "movimento", ocorrido_em: "2026-07-29T13:15:00Z", ator: null, de_etapa: "Novo", para_etapa: "Visita" },
      ],
      loading: false,
      renderers: GENERIC_TIMELINE_RENDERERS,
    });
    expect(getByTestId("timeline-entry").textContent).toContain('Moveu de "Novo" para "Visita"');
  });
});
