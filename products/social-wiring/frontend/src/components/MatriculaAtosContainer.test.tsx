/**
 * MatriculaAtosContainer — which matrícula reading the human is choosing acts
 * on. Real hooks against a fake API (`api.get` routed by URL).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  useAuthStore: () => ({ user: { id: "u1" } }),
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

import { MatriculaAtosContainer } from "./MatriculaAtosContainer";

afterEach(() => {
  cleanup();
  mockGet.mockReset();
});

const EXTRACAO_VELHA = { id: "ext-velha", nome_arquivo: "velha.pdf", status: "concluida", created_at: "2026-01-01T00:00:00Z" };
const EXTRACAO_NOVA = { id: "ext-nova", nome_arquivo: "nova.pdf", status: "concluida", created_at: "2026-03-01T00:00:00Z" };
const EXTRACAO_PROCESSANDO = { id: "ext-proc", nome_arquivo: "proc.pdf", status: "processando", created_at: "2026-04-01T00:00:00Z" };

function fakeApi(opts: { persistida: string | null }) {
  mockGet.mockImplementation(async (url: string, params?: Record<string, unknown>) => {
    if (url === "/api/matriculas/extracoes") {
      return { data: params?.sem_imovel ? [] : [EXTRACAO_VELHA, EXTRACAO_NOVA, EXTRACAO_PROCESSANDO] };
    }
    if (url === "/api/matriculas/contratos/k1/atos") {
      return {
        data: {
          contrato_id: "k1",
          extracao_id: opts.persistida,
          atos: opts.persistida ? [{ ato_id: "a1", ordem: 0 }] : [],
          permutas: [],
          selecionado_por: null,
          selecionado_em: null,
        },
      };
    }
    if (url.startsWith("/api/matriculas/extracoes/") && url.endsWith("/atos")) {
      const id = url.split("/")[4];
      return { data: { extracao_id: id, status: "concluida", codigo: "AP1", total: 0, atos: [] } };
    }
    throw new Error(`unexpected GET ${url}`);
  });
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MatriculaAtosContainer contratoId="k1" codigo="AP1" />
    </QueryClientProvider>,
  );
}

describe("MatriculaAtosContainer — current reading", () => {
  it("🔴 a contract with nothing saved opens on the imóvel's NEWEST concluded reading", async () => {
    fakeApi({ persistida: null });
    mount();
    await waitFor(() =>
      expect(screen.getByTestId("matricula-atos-extracao-ext-nova").textContent).toContain("selecionada"),
    );
    // the newest concluded one is marked; the still-processing one is never "current"
    expect(screen.getByTestId("matricula-atos-atual-ext-nova")).toBeTruthy();
    expect(screen.queryByTestId("matricula-atos-atual-ext-proc")).toBeNull();
    expect(screen.queryByTestId("matricula-atos-leitura-desatualizada")).toBeNull();
  });

  it("🔴 saved acts from an OLDER reading open on that reading, with the switch offered", async () => {
    fakeApi({ persistida: "ext-velha" });
    mount();
    await waitFor(() =>
      expect(screen.getByTestId("matricula-atos-extracao-ext-velha").textContent).toContain("selecionada"),
    );
    expect(screen.getByTestId("matricula-atos-leitura-desatualizada")).toBeTruthy();
    screen.getByTestId("matricula-atos-usar-leitura-atual").click();
    await waitFor(() =>
      expect(screen.getByTestId("matricula-atos-extracao-ext-nova").textContent).toContain("selecionada"),
    );
  });
});
