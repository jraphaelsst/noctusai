/**
 * `useRoteiroMutations` — the roteiro lifecycle writes (roteiro-ciclo CONTRACT §3–§5).
 *
 * Two things are pinned, both against the CONTRACT's exact shapes (fixtures in
 * `components/card/roteiroFixtures.ts`, no privately guessed mock):
 *
 *  1. the wire — path, method and body KEYS of every route R2–R14 the FE calls;
 *  2. the cache — every write puts what the server answered into `roteirosKeys.list`
 *     the instant it answers (the settle refetch never runs here), never
 *     invalidate-only; `reagendar` writes BOTH roteiros.
 *
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api,
  supabase: {
    auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "tok" } } }) },
  },
}));

import { baixarRoteiroPdf, roteirosKeys, useRoteiroMutations } from "./useCardHub";
import {
  permissoesGerado,
  permissoesRascunho,
  roteiroFx,
  visitaFx,
} from "@/components/card/roteiroFixtures";
import type { Roteiro } from "@/types/cardHub";

const C = "c1";
const BASE = `/api/clientes/${C}/roteiros`;

function mount(seed: Roteiro[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  qc.setQueryData(roteirosKeys.list(C), seed);
  // the settle refetch never finishes: the cache is exactly what the hook wrote
  vi.spyOn(qc, "invalidateQueries").mockReturnValue(new Promise(() => {}));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useRoteiroMutations(C), { wrapper });
  const lista = () => qc.getQueryData<Roteiro[]>(roteirosKeys.list(C)) ?? [];
  return { qc, result, lista };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("useRoteiroMutations — R2 create / R3 update", () => {
  it("R2 POSTs the optional keys only and prepends the DRAFT the server answered", async () => {
    const existente = roteiroFx({ id: "r0" });
    const novo = roteiroFx({ id: "r9", status: "rascunho", titulo: null, data_visita: null });
    api.post.mockResolvedValueOnce(novo);
    const { result, lista } = mount([existente]);

    await act(() =>
      result.current.create.mutateAsync({
        titulo: null,
        data_visita: "2026-11-14",
        hora_visita: "10:00",
        atendimento_id: "a1",
        imoveis: ["ONE9001"],
      }),
    );

    expect(api.post).toHaveBeenCalledWith(BASE, {
      titulo: null,
      data_visita: "2026-11-14",
      hora_visita: "10:00",
      atendimento_id: "a1",
      imoveis: ["ONE9001"],
    });
    expect(lista().map((r) => r.id)).toEqual(["r9", "r0"]);
    expect(lista()[0].status).toBe("rascunho");
  });

  it("R3 PATCHes titulo/data_visita/hora_visita and replaces the cached row with the server's", async () => {
    const { result, lista } = mount([roteiroFx()]);
    api.patch.mockResolvedValueOnce(
      roteiroFx({ titulo: "Sábado", hora_visita: "10:30", updated_at: "2026-11-09T13:00:00+00:00" }),
    );

    await act(() =>
      result.current.update.mutateAsync({
        id: "r1",
        body: { titulo: "Sábado", data_visita: "2026-11-14", hora_visita: "10:30" },
      }),
    );

    expect(api.patch).toHaveBeenCalledWith(`${BASE}/r1`, {
      titulo: "Sábado",
      data_visita: "2026-11-14",
      hora_visita: "10:30",
    });
    expect(lista()[0].titulo).toBe("Sábado");
    expect(lista()[0].updated_at).toBe("2026-11-09T13:00:00+00:00");
  });
});

describe("useRoteiroMutations — R5 ordem / R6 / R7", () => {
  const tres = () => [visitaFx("v1", "A1"), visitaFx("v2", "A2"), visitaFx("v3", "A3")];

  it("R5 draws the new order BEFORE the server answers, then commits the server's roteiro", async () => {
    const { result, lista } = mount([roteiroFx({ visitas: tres() })]);
    let resolver!: (r: Roteiro) => void;
    api.put.mockImplementationOnce(() => new Promise<Roteiro>((r) => (resolver = r)));

    let p!: Promise<unknown>;
    act(() => {
      p = result.current.reorder.mutateAsync({ id: "r1", visitaIds: ["v3", "v1", "v2"] });
    });
    await waitFor(() => expect(lista()[0].visitas.map((v) => v.id)).toEqual(["v3", "v1", "v2"]));
    expect(api.put).toHaveBeenCalledWith(`${BASE}/r1/ordem`, { visita_ids: ["v3", "v1", "v2"] });

    resolver(roteiroFx({ visitas: [tres()[2], tres()[0], tres()[1]], updated_at: "2026-11-09T14:00:00+00:00" }));
    await act(() => p);
    expect(lista()[0].updated_at).toBe("2026-11-09T14:00:00+00:00");
  });

  it("R5 rolls the order back when the server refuses (409 roteiro_gerado)", async () => {
    const { result, lista } = mount([roteiroFx({ visitas: tres() })]);
    api.put.mockRejectedValueOnce(new Error("roteiro_gerado"));
    await act(async () => {
      await result.current.reorder.mutateAsync({ id: "r1", visitaIds: ["v3", "v1", "v2"] }).catch(() => {});
    });
    expect(lista()[0].visitas.map((v) => v.id)).toEqual(["v1", "v2", "v3"]);
  });

  it("R6 POSTs {codigo} and writes the Visita into the roteiro; the roteiro's server-derived parts are refreshed", async () => {
    const { result, lista, qc } = mount([roteiroFx({ visitas: [visitaFx("v1", "A1")] })]);
    api.post.mockResolvedValueOnce(visitaFx("v9", "A9", { ordem: 1 }));

    await act(() => result.current.addVisita.mutateAsync({ roteiroId: "r1", codigo: "A9" }));

    expect(api.post).toHaveBeenCalledWith(`${BASE}/r1/visitas`, { codigo: "A9" });
    expect(lista()[0].visitas.map((v) => v.codigo)).toEqual(["A1", "A9"]);
    // R6 answers a Visita only: `permissoes.gerar` comes from a background refetch of the list
    const chaves = vi.mocked(qc.invalidateQueries).mock.calls.map(([a]) => JSON.stringify(a?.queryKey));
    expect(chaves).toContain(JSON.stringify(roteirosKeys.list(C)));
  });

  it("R7 removes the visita optimistically (DELETE …/visitas/{vid})", async () => {
    const { result, lista } = mount([roteiroFx({ visitas: tres() })]);
    api.delete.mockResolvedValueOnce(undefined);
    await act(() => result.current.removeVisita.mutateAsync({ roteiroId: "r1", visitaId: "v2" }));
    expect(api.delete).toHaveBeenCalledWith(`${BASE}/r1/visitas/v2`);
    expect(lista()[0].visitas.map((v) => v.id)).toEqual(["v1", "v3"]);
  });
});

describe("useRoteiroMutations — R8 gerar / R9 reabrir", () => {
  it("R8 POSTs …/gerar (no body) and writes status 'gerado' + the server's permissoes into the cache", async () => {
    const { result, lista } = mount([roteiroFx({ visitas: [visitaFx("v1", "A1")] })]);
    api.post.mockResolvedValueOnce(
      roteiroFx({
        status: "gerado",
        visitas: [visitaFx("v1", "A1")],
        permissoes: permissoesGerado(),
        funil: { moveu: true, de: "novo", para: "visitas", motivo: null },
      }),
    );

    const out = await act(() => result.current.gerar.mutateAsync({ id: "r1" }));

    expect(api.post).toHaveBeenCalledWith(`${BASE}/r1/gerar`);
    expect(out.funil?.moveu).toBe(true);
    const r = lista()[0];
    expect(r.status).toBe("gerado");
    expect(r.permissoes.baixar_pdf).toBe(true);
    expect(r.permissoes.editar_imoveis).toBe(false);
    expect(r.gerado_em).toBeTruthy();
  });

  it("R8 / R9 also refresh the pendentes-feedback queue and the card (their derived views)", async () => {
    const { result, qc } = mount([roteiroFx()]);
    api.post.mockResolvedValueOnce(roteiroFx({ status: "gerado" }));
    await act(() => result.current.gerar.mutateAsync({ id: "r1" }));
    api.post.mockResolvedValueOnce(roteiroFx({ status: "rascunho" }));
    await act(() => result.current.reabrir.mutateAsync({ id: "r1" }));
    const chaves = vi.mocked(qc.invalidateQueries).mock.calls.map(([a]) => JSON.stringify(a?.queryKey));
    expect(chaves).toContain(JSON.stringify(["sw", "roteiros", "pendentes-feedback"]));
  });

  it("R9 POSTs …/reabrir and writes the DRAFT back (the PDF permission disappears with it)", async () => {
    const { result, lista } = mount([roteiroFx({ status: "gerado" })]);
    api.post.mockResolvedValueOnce(
      roteiroFx({
        status: "rascunho",
        reaberto_em: "2026-11-13T09:00:00+00:00",
        reaberto_por: "u-cindy",
        permissoes: permissoesRascunho(),
      }),
    );
    await act(() => result.current.reabrir.mutateAsync({ id: "r1" }));
    expect(api.post).toHaveBeenCalledWith(`${BASE}/r1/reabrir`);
    expect(lista()[0].status).toBe("rascunho");
    expect(lista()[0].permissoes.baixar_pdf).toBe(false);
    expect(lista()[0].reaberto_por).toBe("u-cindy");
  });
});

describe("useRoteiroMutations — R11 outcome / R13 proposta / R12 reagendar", () => {
  it("R11 PATCHes status + cancelada_por + cancelada_motivo (+ observacao) and merges the Visita the server answered", async () => {
    const { result, lista } = mount([
      roteiroFx({ status: "gerado", visitas: [visitaFx("v1", "A1"), visitaFx("v2", "A2")] }),
    ]);
    api.patch.mockResolvedValueOnce(
      visitaFx("v1", "A1", {
        status: "cancelada",
        cancelada_por: "proprietario",
        cancelada_motivo: "imovel_indisponivel",
        resultado_em: "2026-11-14T10:00:00+00:00",
        resultado_por: "u1",
      }),
    );

    await act(() =>
      result.current.patchVisita.mutateAsync({
        roteiroId: "r1",
        visitaId: "v1",
        body: {
          status: "cancelada",
          cancelada_por: "proprietario",
          cancelada_motivo: "imovel_indisponivel",
        },
      }),
    );

    expect(api.patch).toHaveBeenCalledWith(`${BASE}/r1/visitas/v1`, {
      status: "cancelada",
      cancelada_por: "proprietario",
      cancelada_motivo: "imovel_indisponivel",
    });
    const v1 = lista()[0].visitas[0];
    expect([v1.status, v1.cancelada_por, v1.cancelada_motivo, v1.resultado_em]).toEqual([
      "cancelada",
      "proprietario",
      "imovel_indisponivel",
      "2026-11-14T10:00:00+00:00",
    ]);
    expect(lista()[0].visitas[1].status).toBe("pendente"); // the sibling is untouched
  });

  it("R13 keeps its own route (…/proposta) with {proposta, aceita}", async () => {
    const { result } = mount([roteiroFx({ status: "gerado", visitas: [visitaFx("v1", "A1")] })]);
    api.patch.mockResolvedValueOnce(visitaFx("v1", "A1", { proposta_em: "2026-11-15T00:00:00+00:00" }));
    await act(() =>
      result.current.patchProposta.mutateAsync({ roteiroId: "r1", visitaId: "v1", body: { proposta: true } }),
    );
    expect(api.patch).toHaveBeenCalledWith(`${BASE}/r1/visitas/v1/proposta`, { proposta: true });
  });

  it("🔴 R12 POSTs …/reagendar and writes BOTH roteiros: the old visita turns 'reagendada', the new draft appears", async () => {
    const antigo = roteiroFx({
      status: "gerado",
      visitas: [visitaFx("v1", "ONE10702"), visitaFx("v2", "ONE10811")],
    });
    const { result, lista } = mount([antigo]);
    const visita = visitaFx("v1", "ONE10702", {
      status: "reagendada",
      reagendada_para_visita_id: "nv1",
      resultado_em: "2026-11-14T10:00:00+00:00",
    });
    const novo = roteiroFx({
      id: "r2",
      status: "rascunho",
      data_visita: "2026-11-21",
      visitas: [visitaFx("nv1", "ONE10702", { roteiro_id: "r2" })],
    });
    api.post.mockResolvedValueOnce({ visita, novo_roteiro: novo });

    const out = await act(() =>
      result.current.reagendar.mutateAsync({
        roteiroId: "r1",
        visitaId: "v1",
        body: { data_visita: "2026-11-21", hora_visita: null },
      }),
    );

    expect(api.post).toHaveBeenCalledWith(`${BASE}/r1/visitas/v1/reagendar`, {
      data_visita: "2026-11-21",
      hora_visita: null,
    });
    expect(out.novo_roteiro.id).toBe("r2");
    const l = lista();
    expect(l.map((r) => r.id)).toEqual(["r2", "r1"]); // the new draft is in the list
    const velho = l.find((r) => r.id === "r1")!;
    expect(velho.visitas[0].status).toBe("reagendada");
    expect(velho.visitas[0].reagendada_para_visita_id).toBe("nv1");
    expect(velho.visitas[1].status).toBe("pendente"); // untouched
    expect(l.find((r) => r.id === "r2")!.status).toBe("rascunho");
  });

  it("R12 without a body still sends {} (every field optional)", async () => {
    const { result } = mount([roteiroFx({ status: "gerado" })]);
    api.post.mockResolvedValueOnce({
      visita: visitaFx("v1", "ONE9001", { status: "reagendada" }),
      novo_roteiro: roteiroFx({ id: "r2" }),
    });
    await act(() => result.current.reagendar.mutateAsync({ roteiroId: "r1", visitaId: "v1" }));
    expect(api.post).toHaveBeenCalledWith(`${BASE}/r1/visitas/v1/reagendar`, {});
  });

  it("R4 removes the roteiro optimistically and restores it when the server refuses", async () => {
    const { result, lista, qc } = mount([roteiroFx({ status: "gerado" })]);
    // R4 is a plain mutation whose `onSettled` awaits the invalidations: let them settle (no refetch happens)
    vi.mocked(qc.invalidateQueries).mockResolvedValue(undefined);
    api.delete.mockRejectedValueOnce(new Error("roteiro_gerado_com_resultados"));
    await act(async () => {
      await result.current.remove.mutateAsync("r1").catch(() => {});
    });
    expect(api.delete).toHaveBeenCalledWith(`${BASE}/r1`);
    expect(lista().map((r) => r.id)).toEqual(["r1"]);
  });
});

describe("baixarRoteiroPdf — R10", () => {
  const resposta = (init: Partial<Response> & { jsonBody?: unknown }) =>
    ({
      ok: false,
      status: 409,
      headers: new Headers(),
      json: async () => init.jsonBody,
      blob: async () => new Blob(["%PDF-"]),
      ...init,
    }) as unknown as Response;

  it("409 roteiro_rascunho: the thrown error carries the server's message, not a bare status", async () => {
    const message = "Este roteiro ainda é um rascunho. Gere o roteiro para baixar o PDF.";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        resposta({ jsonBody: { detail: { code: "roteiro_rascunho", message } } }),
      ),
    );
    await expect(baixarRoteiroPdf(C, "r1")).rejects.toThrow(message);
  });

  it("falls back to the status when the body is not the typed envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        resposta({
          status: 500,
          json: async () => {
            throw new Error("not json");
          },
        }),
      ),
    );
    await expect(baixarRoteiroPdf(C, "r1")).rejects.toThrow("HTTP 500");
  });

  it("requests the contract path with the session token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(resposta({ ok: false, status: 409, jsonBody: {} }));
    vi.stubGlobal("fetch", fetchMock);
    await baixarRoteiroPdf(C, "r1").catch(() => {});
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(`${BASE}/r1/pdf`);
    expect((init as RequestInit).headers).toEqual({ Authorization: "Bearer tok" });
  });
});
