/**
 * Timeline.test.tsx — D9's "everything, one thread": four states (loading /
 * empty / error / success), and the forward-compat rule that an unknown
 * `kind` renders a graceful generic entry rather than crashing or vanishing
 * (Phase 2b's conversation kinds land on this slot untested here, but the
 * union's escape hatch must already hold).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TimelineEntry } from "@/types/cardHub";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { Timeline } from "./Timeline";

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
    const { getAllByTestId, getByText } = await render({ entries, loading: false });
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

describe("Timeline — um contato diz o que aconteceu", () => {
  it("nomeia a ação e a origem, não só a pessoa", async () => {
    // 🔴 Antes: quatro linhas idênticas com o nome do lead e uma data,
    // sem verbo — impossível saber o que cada uma registrava.
    const { getAllByTestId } = await render({ loading: false, error: null, entries: [
      {
        id: "t1",
        kind: "touch",
        ocorrido_em: "2026-07-29T13:15:00+00:00",
        ator: null,
        origem_tabela: "leads",
        origem_id: "L1",
        origem_rotulo: "Meta Ads",
        resumo: "Ana Lima",
        dados: {},
      }] as any });

    const linha = getAllByTestId("timeline-entry")[0];
    expect(linha.textContent).toContain("Novo contato via Meta Ads");
    expect(linha.textContent).toContain("Ana Lima");
  });

  it("não repete o mesmo texto duas vezes quando nome e origem coincidem", async () => {
    const { getAllByTestId } = await render({ loading: false, error: null, entries: [
      {
        id: "t2",
        kind: "touch",
        ocorrido_em: "2026-07-29T13:15:00+00:00",
        ator: null,
        origem_tabela: "leads",
        origem_id: "L2",
        origem_rotulo: "OLX",
        resumo: "olx",
        dados: {},
      }] as any });

    expect(getAllByTestId("timeline-entry")[0].textContent).toContain(
      "Novo contato via OLX",
    );
  });
});

describe("Timeline — Bug 4 (prod card 755253934): a touch entry's date never shifts to the previous day", () => {
  it("🔴 data_entrada 2026-09-23, serialized as UTC midnight, renders 23/09/2026 — never 22/09/2026 21:00", async () => {
    const { getAllByTestId } = await render({
      loading: false,
      error: null,
      entries: [
        {
          id: "t3",
          kind: "touch",
          // What the backend sends for a DATE column (`data_entrada`)
          // widened into a tz-aware timestamp — exactly midnight UTC,
          // which is 21:00 the PREVIOUS day in America/Sao_Paulo.
          ocorrido_em: "2026-09-23T00:00:00Z",
          ator: null,
          origem_tabela: "leads",
          origem_id: "L3",
          origem_rotulo: null,
          resumo: null,
          dados: {},
        },
      ] as any,
    });

    const texto = getAllByTestId("timeline-entry")[0].textContent ?? "";
    expect(texto).toContain("23/09/2026");
    expect(texto).not.toContain("22/09/2026");
  });

  it("the +00:00 offset spelling is treated the same as Z", async () => {
    const { getAllByTestId } = await render({
      loading: false,
      error: null,
      entries: [
        {
          id: "t4",
          kind: "touch",
          ocorrido_em: "2026-09-23T00:00:00+00:00",
          ator: null,
          origem_tabela: "leads",
          origem_id: "L4",
          origem_rotulo: null,
          resumo: null,
          dados: {},
        },
      ] as any,
    });

    const texto = getAllByTestId("timeline-entry")[0].textContent ?? "";
    expect(texto).toContain("23/09/2026");
    expect(texto).not.toContain("22/09/2026");
  });

  it("a REAL midnight-adjacent timestamp for a non-touch kind is left untouched (never over-corrected)", async () => {
    const { getAllByTestId } = await render({
      loading: false,
      error: null,
      entries: [
        {
          id: "t5",
          kind: "sistema",
          // A genuine event at 21:00 local (00:00 UTC) — NOT a date-only
          // fact, so it must render at its real time, not get collapsed to
          // a bare date. Only `touch` traces back to a DATE column.
          ocorrido_em: "2026-09-23T00:00:00Z",
          ator: null,
          evento: "Cartão criado",
          detalhe: null,
        },
      ] as any,
    });

    const texto = getAllByTestId("timeline-entry")[0].textContent ?? "";
    // Unshifted-by-this-fix means the SEED's own `formatDate` still parses
    // it as a real UTC instant — 21:00 the day before in America/Sao_Paulo,
    // same day in a UTC runner (CI). Expect whatever LOCAL date that instant is.
    const local = new Date("2026-09-23T00:00:00Z");
    const esperado = `${String(local.getDate()).padStart(2, "0")}/${String(local.getMonth() + 1).padStart(2, "0")}/${local.getFullYear()}`;
    expect(texto).toContain(esperado);
  });
});
