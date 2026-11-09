/**
 * RoteiroEditorDialog — one test per DRAFT row of the roteiro state matrix
 * (mockup NOTES §2): Rascunho salvo / salvando / erro / falta data, Confirmar
 * gerar, Fechar com erro — plus the autosave contract (created on the first
 * meaningful edit, debounced text fields, immediate list writes), the ↑/↓
 * reorder with its aria-live announcement, and the live imóvel search.
 *
 * The seam is the NETWORK EDGE: a real QueryClient + the real hooks, with
 * `api` answering in the contract's shapes (`roteiroFixtures.ts`). Every
 * assertion on a request asserts the contract's exact path and body keys.
 *
 * WHAT THIS DOES NOT SIMULATE: the drag gesture — drag is optional sugar now;
 * ↑/↓ buttons are the reorder control (WCAG 2.5.7).
 */
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const { api, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({
  api,
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

import { roteirosKeys } from "@/hooks/useCardHub";
import type { Roteiro } from "@/types/cardHub";

import { RoteiroEditorDialog, type RoteiroEditorDialogProps } from "./RoteiroEditorDialog";
import { imovelFx, permissoesRascunho, roteiroFx, visitaFx } from "./roteiroFixtures";

const BASE = "/api/clientes/c1";

/** What the server would say about a draft's `permissoes` (CONTRACT §2) — fixture logic, not FE logic. */
function comPermissoes(r: Roteiro): Roteiro {
  const motivo =
    r.visitas.length === 0
      ? "Adicione ao menos um imóvel."
      : !r.data_visita
        ? "Informe a data da visita."
        : null;
  return {
    ...r,
    permissoes: permissoesRascunho({ gerar: motivo === null, motivo_gerar: motivo }),
  };
}

let db: Roteiro[] = [];

function wire() {
  api.get.mockImplementation(async (url: string) => {
    if (url.includes("/api/imoveis/busca")) {
      return {
        items: [imovelFx("ONE9001"), imovelFx("ONE9002")],
      };
    }
    if (url === `${BASE}/roteiros`) return { items: db, total: db.length };
    throw new Error(`unexpected GET ${url}`);
  });
}

function montar(props: Partial<RoteiroEditorDialogProps> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const onOpenChange = vi.fn();
  const onGerado = vi.fn();
  const utils = render(
    <RoteiroEditorDialog
      open
      onOpenChange={onOpenChange}
      onGerado={onGerado}
      clienteId="c1"
      atendimentoId="a1"
      {...props}
    />,
    { wrapper },
  );
  return { qc, onOpenChange, onGerado, ...utils };
}

const tres = () => [
  visitaFx("v1", "ONE9001", { ordem: 0 }),
  visitaFx("v2", "ONE9002", { ordem: 1 }),
  visitaFx("v3", "ONE9003", { ordem: 2 }),
];

beforeEach(() => {
  db = [];
  wire();
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const apiError = (status: number, message: string, code = "erro") =>
  Object.assign(new Error(`[${status}] ${message}`), {
    name: "ApiError",
    status,
    body: { detail: { code, message } },
  });

describe("RoteiroEditorDialog — Rascunho · salvo", () => {
  it("shows the Rascunho chip, the ↑/↓ list, Gerar enabled — and NO PDF control", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    montar({ roteiroId: "r1" });

    await screen.findByTestId("roteiro-lista");
    expect(screen.getByTestId("roteiro-status-chip").textContent).toBe("Rascunho");
    expect(screen.getByTestId("roteiro-salvamento").textContent).toContain("Salvo");
    expect((screen.getByTestId("roteiro-gerar-roteiro") as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByTestId("roteiro-gerar-motivo").textContent).toBe("Pronto para gerar: 3 imóveis.");
    // 🔴 the PDF gate: a draft never carries a PDF control
    expect(screen.queryByText("Baixar PDF")).toBeNull();
    expect(screen.queryByText(/Reabrir/)).toBeNull();
  });

  it("F6 — the first ↑ and the last ↓ are disabled, with the reason in the accessible name", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    const sobe1 = screen.getByTestId("roteiro-subir-ONE9001") as HTMLButtonElement;
    const desce3 = screen.getByTestId("roteiro-descer-ONE9003") as HTMLButtonElement;
    expect(sobe1.disabled).toBe(true);
    expect(sobe1.getAttribute("aria-label")).toBe("Mover ONE9001 para cima (já é o 1º)");
    expect(desce3.disabled).toBe(true);
    expect(desce3.getAttribute("aria-label")).toBe("Mover ONE9003 para baixo (já é o último)");
    expect((screen.getByTestId("roteiro-subir-ONE9002") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId("roteiro-descer-ONE9001") as HTMLButtonElement).disabled).toBe(false);
  });

  it("F6 — ↓ sends the exact new order (R5) and announces the new position in a polite live region", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.put.mockImplementation(async (_url: string, body: { visita_ids: string[] }) => {
      const r = db[0];
      const visitas = body.visita_ids.map((id) => r.visitas.find((v) => v.id === id)!);
      db = [comPermissoes({ ...r, visitas })];
      return db[0];
    });
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.click(screen.getByTestId("roteiro-descer-ONE9001"));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(`${BASE}/roteiros/r1/ordem`, {
        visita_ids: ["v2", "v1", "v3"],
      }),
    );
    const live = screen.getByTestId("roteiro-ordem-live");
    expect(live.getAttribute("aria-live")).toBe("polite");
    expect(live.textContent).toBe("ONE9001 agora é o 2º.");
    // the list itself shows the new order (cache write, no refetch needed)
    await waitFor(() => {
      const ordem = within(screen.getByTestId("roteiro-lista"))
        .getAllByRole("listitem")
        .map((li) => li.getAttribute("data-testid"));
      expect(ordem).toEqual(["roteiro-linha-ONE9002", "roteiro-linha-ONE9001", "roteiro-linha-ONE9003"]);
    });
  });

  it("removing an imóvel sends R7 with the visita id", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.delete.mockImplementation(async () => {
      db = [comPermissoes({ ...db[0], visitas: db[0].visitas.filter((v) => v.id !== "v2") })];
      return db[0];
    });
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.click(screen.getByTestId("roteiro-remover-ONE9002"));
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith(`${BASE}/roteiros/r1/visitas/v2`),
    );
  });

  it("renders the list from `permissoes.editar_imoveis`: false ⇒ no ↑/↓, no remove, no search", async () => {
    db = [
      roteiroFx({
        visitas: tres(),
        permissoes: permissoesRascunho({ editar_imoveis: false }),
      }),
    ];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");
    expect(screen.queryByTestId("roteiro-subir-ONE9002")).toBeNull();
    expect(screen.queryByTestId("roteiro-remover-ONE9002")).toBeNull();
    expect(screen.queryByTestId("roteiro-busca")).toBeNull();
  });
});

describe("RoteiroEditorDialog — reopening a draft (Continuar editando)", () => {
  it("🔴 shows a skeleton — never empty inputs that could PATCH over real data — until the draft is known, then hydrates", async () => {
    db = [comPermissoes(roteiroFx({ titulo: "Terça", hora_visita: "09:30", visitas: tres() }))];
    let liberar!: () => void;
    api.get.mockImplementation(
      (url: string) =>
        new Promise((resolve) => {
          liberar = () => resolve({ items: db, total: db.length });
          void url;
        }),
    );
    montar({ roteiroId: "r1" });

    expect(screen.getByTestId("roteiro-editor-carregando")).toBeTruthy();
    expect(screen.queryByTestId("roteiro-data-visita")).toBeNull();
    expect(screen.queryByTestId("roteiro-lista-vazia")).toBeNull();

    liberar();
    await screen.findByTestId("roteiro-lista");
    expect((screen.getByTestId("roteiro-titulo") as HTMLInputElement).value).toBe("Terça");
    expect((screen.getByTestId("roteiro-data-visita") as HTMLInputElement).value).toBe("2026-11-14");
    expect((screen.getByTestId("roteiro-hora-visita") as HTMLInputElement).value).toBe("09:30");
  });

  it("a draft that no longer exists says so instead of rendering an empty editor", async () => {
    db = [];
    montar({ roteiroId: "r1" });
    const msg = await screen.findByTestId("roteiro-editor-indisponivel");
    expect(msg.textContent).toContain("Este rascunho não existe mais");
    expect(screen.queryByTestId("roteiro-data-visita")).toBeNull();
  });
});

describe("RoteiroEditorDialog — horário por visita", () => {
  it("each imóvel has its own Horário; leaving the field sends R11 {horario} and writes the answer", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.patch.mockImplementation(async (_u: string, body: { horario: string | null }) => {
      db = [comPermissoes({ ...db[0], visitas: db[0].visitas.map((v) => (v.id === "v2" ? { ...v, horario: body.horario } : v)) })];
      return db[0];
    });
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    const campo = screen.getByTestId("visita-horario-ONE9002") as HTMLInputElement;
    fireEvent.change(campo, { target: { value: "11:15" } });
    expect(api.patch).not.toHaveBeenCalled();
    fireEvent.blur(campo);
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(`${BASE}/roteiros/r1/visitas/v2`, { horario: "11:15" }),
    );
    // cleared ⇒ null
    fireEvent.change(campo, { target: { value: "" } });
    fireEvent.blur(campo);
    await waitFor(() =>
      expect(api.patch).toHaveBeenLastCalledWith(`${BASE}/roteiros/r1/visitas/v2`, { horario: null }),
    );
  });
});

describe("RoteiroEditorDialog — Rascunho · salvando", () => {
  it("says Salvando… while the write is in flight and keeps Gerar disabled, then Salvo", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    let resolver!: (r: Roteiro) => void;
    api.patch.mockImplementation(
      () =>
        new Promise<Roteiro>((r) => {
          resolver = r;
        }),
    );
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.change(screen.getByTestId("roteiro-titulo"), { target: { value: "Sábado" } });
    // the debounce is pending: already "Salvando…" (a draft always says whether it is saved)
    expect(screen.getByTestId("roteiro-salvamento").textContent).toContain("Salvando…");
    expect((screen.getByTestId("roteiro-gerar-roteiro") as HTMLButtonElement).disabled).toBe(true);

    await waitFor(() => expect(api.patch).toHaveBeenCalled(), { timeout: 2500 });
    expect(screen.getByTestId("roteiro-salvamento").textContent).toContain("Salvando…");
    resolver({ ...db[0], titulo: "Sábado" });
    await waitFor(() =>
      expect(screen.getByTestId("roteiro-salvamento").textContent).toMatch(/Salvo há \d+ s/),
    );
    expect((screen.getByTestId("roteiro-gerar-roteiro") as HTMLButtonElement).disabled).toBe(false);
  });

  it("the live region is polite (WCAG 4.1.3)", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");
    expect(screen.getByTestId("roteiro-salvamento").getAttribute("aria-live")).toBe("polite");
  });
});

describe("RoteiroEditorDialog — Rascunho · erro", () => {
  it("🔴 Não salvo (alert) + banner with the SERVER's message + the input kept + Tentar de novo", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.patch.mockRejectedValueOnce(apiError(500, "Sem conexão com o servidor."));
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.change(screen.getByTestId("roteiro-titulo"), { target: { value: "Sábado" } });
    const banner = await screen.findByTestId("roteiro-erro-banner", undefined, { timeout: 2500 });
    expect(banner.getAttribute("role")).toBe("alert");
    expect(banner.textContent).toContain("Sua última alteração não foi salva.");
    expect(banner.textContent).toContain("Sem conexão com o servidor.");
    const chip = screen.getByTestId("roteiro-salvamento");
    expect(chip.getAttribute("role")).toBe("alert");
    expect(chip.textContent).toContain("Não salvo");
    // the input is kept
    expect((screen.getByTestId("roteiro-titulo") as HTMLInputElement).value).toBe("Sábado");
    // Gerar disabled: "Salve antes de gerar."
    expect((screen.getByTestId("roteiro-gerar-roteiro") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("roteiro-gerar-motivo").textContent).toBe("Salve antes de gerar.");

    api.patch.mockResolvedValueOnce({ ...db[0], titulo: "Sábado" });
    fireEvent.click(screen.getByTestId("roteiro-tentar-de-novo"));
    await waitFor(() => expect(screen.queryByTestId("roteiro-erro-banner")).toBeNull());
    expect(api.patch).toHaveBeenCalledTimes(2);
    expect(api.patch).toHaveBeenLastCalledWith(`${BASE}/roteiros/r1`, {
      titulo: "Sábado",
      data_visita: "2026-11-14",
      hora_visita: null,
    });
    expect(screen.getByTestId("roteiro-salvamento").textContent).toMatch(/Salvo há/);
  });
});

describe("RoteiroEditorDialog — Rascunho · falta data", () => {
  it("Gerar is disabled with the server's motivo, and the date field is marked invalid", async () => {
    db = [
      roteiroFx({
        data_visita: null,
        visitas: tres(),
        permissoes: permissoesRascunho({ gerar: false, motivo_gerar: "Informe a data da visita." }),
      }),
    ];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    expect((screen.getByTestId("roteiro-gerar-roteiro") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("roteiro-gerar-motivo").textContent).toBe("Informe a data da visita.");
    const data = screen.getByTestId("roteiro-data-visita");
    expect(data.getAttribute("aria-invalid")).toBe("true");
    expect(data.getAttribute("aria-describedby")).toBe("roteiro-motivo-gerar");
  });

  it("with no imóvel the server's own reason is what shows (never re-derived here)", async () => {
    db = [comPermissoes(roteiroFx({ visitas: [] }))];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista-vazia");
    expect(screen.getByTestId("roteiro-gerar-motivo").textContent).toBe("Adicione ao menos um imóvel.");
    expect((screen.getByTestId("roteiro-gerar-roteiro") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("RoteiroEditorDialog — Confirmar gerar", () => {
  it("asks first (alertdialog), and 'Continuar editando' sends nothing", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.click(screen.getByTestId("roteiro-gerar-roteiro"));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Gerar o roteiro de 14/11/2026?")).toBeTruthy();
    expect(dialog.textContent).toContain("não será possível adicionar nem remover imóveis");
    expect(dialog.textContent).toContain("3 imóveis, nesta ordem");
    expect(dialog.textContent).toContain("Só um gestor pode reabrir, e só antes do primeiro resultado.");

    fireEvent.click(within(dialog).getByText("Continuar editando"));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(api.post).not.toHaveBeenCalled();
  });

  it("confirming POSTs R8, writes the gerado roteiro, warns on a refused funnel move and closes", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    const gerado = roteiroFx({
      status: "gerado",
      visitas: tres(),
      funil: { moveu: false, de: "novo", para: "visitas", motivo: "Falta o telefone do cliente." },
    });
    api.post.mockImplementationOnce(async () => {
      db = [gerado]; // the server's state moves too: the settle refetch must agree with the write
      return gerado;
    });
    const { onGerado, onOpenChange, qc } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.click(screen.getByTestId("roteiro-gerar-roteiro"));
    fireEvent.click(await screen.findByTestId("roteiro-confirmar-gerar-ok"));

    await waitFor(() => expect(onGerado).toHaveBeenCalledWith(gerado));
    expect(api.post).toHaveBeenCalledWith(`${BASE}/roteiros/r1/gerar`);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toast.success).toHaveBeenCalledWith("Roteiro gerado.");
    expect(toast.warning).toHaveBeenCalled(); // avisarFunilRecusado — the funnel refusal is not silent
    // the answer was WRITTEN into the cache (status now gerado, permissoes now the server's)
    const cache = qc.getQueryData<Roteiro[]>(roteirosKeys.list("c1")) ?? [];
    expect(cache.find((r) => r.id === "r1")?.status).toBe("gerado");
  });

  it("a refused gerar shows the server's message and keeps the editor open", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.post.mockRejectedValueOnce(apiError(422, "Informe a data da visita.", "roteiro_sem_data"));
    const { onOpenChange } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.click(screen.getByTestId("roteiro-gerar-roteiro"));
    fireEvent.click(await screen.findByTestId("roteiro-confirmar-gerar-ok"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Informe a data da visita."));
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByTestId("roteiro-editor")).toBeTruthy();
  });
});

describe("RoteiroEditorDialog — autosave: the draft is created on the first meaningful edit (R2)", () => {
  const criado = (body: Record<string, unknown>) =>
    comPermissoes(
      roteiroFx({
        id: "novo",
        titulo: (body.titulo as string | null) ?? null,
        data_visita: (body.data_visita as string | null) ?? null,
        hora_visita: (body.hora_visita as string | null) ?? null,
        visitas: ((body.imoveis as string[] | undefined) ?? []).map((c, i) =>
          visitaFx(`nv${i}`, c, { roteiro_id: "novo", ordem: i }),
        ),
      }),
    );

  it("a title alone never creates a draft; the date does (debounced ~800 ms), exact body keys", async () => {
    api.post.mockImplementation(async (_u: string, body: Record<string, unknown>) => {
      db = [criado(body)];
      return db[0];
    });
    montar();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.getByTestId("roteiro-salvamento").textContent).toBe("Ainda não salvo");

    fireEvent.change(screen.getByTestId("roteiro-titulo"), { target: { value: "Sábado" } });
    await new Promise((r) => setTimeout(r, 1000));
    expect(api.post).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId("roteiro-data-visita"), { target: { value: "2026-11-14" } });
    expect(api.post).not.toHaveBeenCalled(); // debounced, not per keystroke
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1), { timeout: 2500 });
    expect(api.post).toHaveBeenCalledWith(`${BASE}/roteiros`, {
      titulo: "Sábado",
      data_visita: "2026-11-14",
      hora_visita: null,
      atendimento_id: "a1",
    });
    await waitFor(() =>
      expect(screen.getByTestId("roteiro-salvamento").textContent).toMatch(/Salvo há/),
    );

    // afterwards every text edit is a PATCH of the SAME draft — never a second create
    api.patch.mockImplementation(async (_u: string, body: Record<string, unknown>) => ({
      ...db[0],
      hora_visita: body.hora_visita as string,
    }));
    fireEvent.change(screen.getByTestId("roteiro-hora-visita"), { target: { value: "10:30" } });
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1), { timeout: 2500 });
    expect(api.patch).toHaveBeenCalledWith(`${BASE}/roteiros/novo`, {
      titulo: "Sábado",
      data_visita: "2026-11-14",
      hora_visita: "10:30",
    });
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it("the FIRST imóvel creates the draft at once (no debounce) with the imoveis key, then the next one is R6", async () => {
    api.post.mockImplementation(async (url: string, body: Record<string, unknown>) => {
      if (url === `${BASE}/roteiros`) {
        db = [criado(body)];
        return db[0];
      }
      const r = db[0];
      db = [comPermissoes({ ...r, visitas: [...r.visitas, visitaFx("nv9", (body as { codigo: string }).codigo, { roteiro_id: "novo", ordem: 1 })] })];
      return db[0];
    });
    montar();
    await waitFor(() => expect(api.get).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "ONE9" } });
    fireEvent.click(await screen.findByTestId("roteiro-busca-item-ONE9001"));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenLastCalledWith(`${BASE}/roteiros`, {
      titulo: null,
      data_visita: null,
      hora_visita: null,
      atendimento_id: "a1",
      imoveis: ["ONE9001"],
    });

    // while the first is in the cache, the second goes through R6 — against the SAME draft
    await screen.findByTestId("roteiro-linha-ONE9001");
    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "ONE9" } });
    fireEvent.click(await screen.findByTestId("roteiro-busca-item-ONE9002"));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post).toHaveBeenLastCalledWith(`${BASE}/roteiros/novo/visitas`, { codigo: "ONE9002" });
  });

  it("two imóveis added before the create answers produce ONE draft (serial queue), not two", async () => {
    let finishCreate!: (r: Roteiro) => void;
    api.post.mockImplementation((url: string, body: Record<string, unknown>) => {
      if (url === `${BASE}/roteiros`) {
        return new Promise<Roteiro>((r) => {
          finishCreate = (v) => {
            db = [v];
            r(v);
          };
        });
      }
      const r = db[0];
      db = [comPermissoes({ ...r, visitas: [...r.visitas, visitaFx("nv2", (body as { codigo: string }).codigo, { roteiro_id: "novo", ordem: 1 })] })];
      return Promise.resolve(db[0]);
    });
    montar();
    await waitFor(() => expect(api.get).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "ONE9" } });
    fireEvent.click(await screen.findByTestId("roteiro-busca-item-ONE9001"));
    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "ONE9" } });
    fireEvent.click(await screen.findByTestId("roteiro-busca-item-ONE9002"));

    expect(api.post).toHaveBeenCalledTimes(1); // the second waits for the first
    finishCreate(criado({ imoveis: ["ONE9001"], titulo: null, data_visita: null, hora_visita: null }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post).toHaveBeenNthCalledWith(1, `${BASE}/roteiros`, expect.objectContaining({ imoveis: ["ONE9001"] }));
    expect(api.post).toHaveBeenNthCalledWith(2, `${BASE}/roteiros/novo/visitas`, { codigo: "ONE9002" });
  });

  it("opened with imóveis from the interest list, the draft is created at once, in that order", async () => {
    api.post.mockImplementation(async (_u: string, body: Record<string, unknown>) => {
      db = [criado(body)];
      return db[0];
    });
    montar({ inicial: [imovelFx("ONE9003"), imovelFx("ONE9001")] });

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenCalledWith(`${BASE}/roteiros`, {
      titulo: null,
      data_visita: null,
      hora_visita: null,
      atendimento_id: "a1",
      imoveis: ["ONE9003", "ONE9001"],
    });
    await screen.findByTestId("roteiro-linha-ONE9003");
    // no date yet ⇒ the server's reason shows, Gerar stays disabled
    expect(screen.getByTestId("roteiro-gerar-motivo").textContent).toBe("Informe a data da visita.");
  });

  it("with an ambiguous atendimento nothing is created until one is chosen", async () => {
    api.post.mockImplementation(async (_u: string, body: Record<string, unknown>) => {
      db = [criado(body)];
      return db[0];
    });
    montar({
      atendimentoId: null,
      atendimentoOpcoes: [
        { id: "a1", titulo: "Compra" },
        { id: "a2", titulo: "Locação" },
      ],
      inicial: [imovelFx("ONE9001")],
    });
    await new Promise((r) => setTimeout(r, 200));
    expect(api.post).not.toHaveBeenCalled();
    expect((screen.getByTestId("roteiro-busca") as HTMLInputElement).disabled).toBe(true);

    fireEvent.change(screen.getByTestId("roteiro-atendimento"), { target: { value: "a2" } });
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenCalledWith(
      `${BASE}/roteiros`,
      expect.objectContaining({ atendimento_id: "a2", imoveis: ["ONE9001"] }),
    );
  });
});

describe("RoteiroEditorDialog — Fechar", () => {
  it("closes at once when everything is saved", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    const { onOpenChange } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");
    fireEvent.keyDown(screen.getByTestId("roteiro-editor"), { key: "Escape" });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("🔴 closing never loses a draft: a pending debounced edit is flushed (sent) before closing", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.patch.mockResolvedValue({ ...db[0], titulo: "Sábado" });
    const { onOpenChange } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.change(screen.getByTestId("roteiro-titulo"), { target: { value: "Sábado" } });
    fireEvent.keyDown(screen.getByTestId("roteiro-editor"), { key: "Escape" });

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(api.patch).toHaveBeenCalledWith(`${BASE}/roteiros/r1`, {
      titulo: "Sábado",
      data_visita: "2026-11-14",
      hora_visita: null,
    });
  });

  it("Fechar com erro — the close-guard asks; 'Fechar mesmo assim' closes, 'Tentar salvar de novo' retries", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.patch.mockRejectedValueOnce(apiError(500, "Sem conexão com o servidor."));
    const { onOpenChange } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.change(screen.getByTestId("roteiro-titulo"), { target: { value: "Sábado" } });
    await screen.findByTestId("roteiro-erro-banner", undefined, { timeout: 2500 });

    fireEvent.keyDown(screen.getByTestId("roteiro-editor"), { key: "Escape" });
    const guarda = await screen.findByTestId("roteiro-guarda-fechar");
    expect(guarda.textContent).toContain("Há uma alteração que não foi salva");
    expect(onOpenChange).not.toHaveBeenCalled();

    // retry path
    api.patch.mockResolvedValueOnce({ ...db[0], titulo: "Sábado" });
    fireEvent.click(screen.getByTestId("roteiro-guarda-tentar"));
    await waitFor(() => expect(screen.queryByTestId("roteiro-erro-banner")).toBeNull());
    expect(api.patch).toHaveBeenCalledTimes(2);
  });

  it("'Fechar mesmo assim' discards the unsaved change and closes", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.patch.mockRejectedValue(apiError(500, "Sem conexão com o servidor."));
    const { onOpenChange } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");
    fireEvent.change(screen.getByTestId("roteiro-titulo"), { target: { value: "Sábado" } });
    await screen.findByTestId("roteiro-erro-banner", undefined, { timeout: 2500 });
    fireEvent.keyDown(screen.getByTestId("roteiro-editor"), { key: "Escape" });
    fireEvent.click(await screen.findByTestId("roteiro-fechar-mesmo-assim"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("RoteiroEditorDialog — live imóvel search", () => {
  it("asks for two characters, lists matches, marks ones already on the roteiro", async () => {
    db = [comPermissoes(roteiroFx({ visitas: [visitaFx("v1", "ONE9001")] }))];
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "O" } });
    expect(screen.getByTestId("roteiro-busca-popover").textContent).toContain("2 caracteres");

    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "ONE9" } });
    const ja = await screen.findByTestId("roteiro-busca-item-ONE9001");
    expect((ja as HTMLButtonElement).disabled).toBe(true);
    expect(ja.textContent).toContain("já no roteiro");
    expect((screen.getByTestId("roteiro-busca-item-ONE9002") as HTMLButtonElement).disabled).toBe(false);
  });

  it("a failed search is surfaced, never an empty list", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.get.mockImplementation(async (url: string) => {
      if (url.includes("/api/imoveis/busca")) throw new Error("boom");
      return { items: db, total: db.length };
    });
    montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");
    fireEvent.change(screen.getByTestId("roteiro-busca"), { target: { value: "ONE9" } });
    await screen.findByTestId("roteiro-busca-erro");
    expect(screen.queryByTestId("roteiro-busca-vazio")).toBeNull();
  });
});

describe("RoteiroEditorDialog — excluir rascunho (R4)", () => {
  it("asks for confirmation, then DELETEs the draft and closes", async () => {
    db = [comPermissoes(roteiroFx({ visitas: tres() }))];
    api.delete.mockResolvedValue(undefined);
    const { onOpenChange } = montar({ roteiroId: "r1" });
    await screen.findByTestId("roteiro-lista");

    fireEvent.click(screen.getByTestId("roteiro-excluir-rascunho"));
    const dialog = await screen.findByTestId("roteiro-confirmar-excluir");
    expect(api.delete).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByText("Excluir"));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith(`${BASE}/roteiros/r1`));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
