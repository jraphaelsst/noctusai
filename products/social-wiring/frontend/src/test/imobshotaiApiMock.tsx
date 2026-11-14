/**
 * Shared test kit for the ImobShotAI screens: a fake of the product `api` client (the HTTP boundary) answering
 * CONTRACT-SHAPED fixtures (`products/social-wiring/IMOBSHOTAI-CONTRACT.md` v1, plus the Edição de Fotos shapes the
 * funnel reuses). Tests wire it with
 *   vi.mock("@noctusai/seed/infra", async () => ({ api: (await import("@/test/imobshotaiApiMock")).api }));
 * and a `rota(path, handler)` per test; an unrouted call FAILS the test instead of returning a guessed shape.
 */
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ApiError } from "@noctusai/lib/api";

type Handler = (arg: any) => unknown;
const rotas = new Map<string, Handler>();

function responder(metodo: string, path: string, arg: unknown) {
  const chave = `${metodo} ${path}`;
  // A path with a query string (the picker builds `?q=..&limit=..` itself) falls back to its bare route.
  const h = rotas.get(chave) ?? rotas.get(`${metodo} ${path.split("?")[0]}`);
  if (!h) return Promise.reject(new Error(`Rota não mockada: ${chave}`));
  try {
    return Promise.resolve(h(arg));
  } catch (e) {
    return Promise.reject(e);
  }
}

export const api = {
  get: vi.fn((path: string, params?: unknown) => responder("GET", path, params)),
  post: vi.fn((path: string, body?: unknown) => responder("POST", path, body)),
  upload: vi.fn((path: string, form?: unknown) => responder("UPLOAD", path, form)),
  patch: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  download: vi.fn(),
};

/** Answer `METODO path` with `handler(paramsOuBody)`; a thrown value becomes a rejection. */
export function rota(metodo: "GET" | "POST" | "UPLOAD", path: string, handler: Handler) {
  rotas.set(`${metodo} ${path}`, handler);
}

export function limparRotas() {
  rotas.clear();
  Object.values(api).forEach((f) => f.mockClear());
}

/** An API error exactly as the contract's `api_error` serialises it. */
export function erroDoContrato(status: number, code: string, message: string) {
  return new ApiError(status, message, { detail: { detail: message, code } });
}

export function renderComQuery(ui: ReactElement, entrada = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entrada]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

// ─── Fixtures (contract §3, §4; Edição de Fotos shapes) ─────────────────────

export const IMOVEL = { org_id: "org-1", codigo: "ONE8990", titulo: "Apartamento amplo", bairro: "Pinheiros" };

export function cardResumo(over: Record<string, unknown> = {}) {
  return {
    id: "card-1",
    imovel: IMOVEL,
    etapa: "fotos_enviadas",
    etapa_desde: "2026-11-13T10:00:00Z",
    capa_url: null,
    total_fotos: 12,
    fotos_aprovadas: 0,
    total_videos: 0,
    criado_em: "2026-11-13T09:00:00Z",
    atualizado_em: "2026-11-13T10:00:00Z",
    ...over,
  };
}

export function paginaDeCards(items: unknown[], total = items.length) {
  return { items, page: 1, page_size: 100, total };
}

export function loteResumo(over: Record<string, unknown> = {}) {
  return {
    id: "lote-1",
    nome: "Fotos ONE8990 13/11",
    criado_em: "2026-11-13T09:00:00Z",
    imovel: { org_id: "org-1", codigo: "ONE8990" },
    velocidade: "urgente",
    estado_agregado: "rascunho",
    total_fotos: 0,
    fotos_decididas: 0,
    ...over,
  };
}

export function cardDetalhe(over: Record<string, unknown> = {}) {
  return {
    ...cardResumo({ etapa: "fotos_em_revisao", capa_url: "https://cdn/capa.jpg", fotos_aprovadas: 1 }),
    lotes: [loteResumo({ estado_agregado: "aguardando_revisao", total_fotos: 2 })],
    fotos: [
      { id: "f1", lote_id: "lote-1", comodo: null, status: "aprovada", original_url: "https://cdn/f1-o.jpg", editada_url: "https://cdn/f1-e.jpg" },
      { id: "f2", lote_id: "lote-1", comodo: null, status: "editando", original_url: "https://cdn/f2-o.jpg", editada_url: null },
    ],
    videos: [],
    eventos: [
      { tipo: "etapa_mudou", etapa_de: "fotos_enviadas", etapa_para: "fotos_em_revisao", ator_id: null, em: "2026-11-13T12:00:00Z", detalhe: {} },
      { tipo: "lote_vinculado", etapa_de: null, etapa_para: null, ator_id: "u1", em: "2026-11-13T09:30:00Z", detalhe: { lote_id: "lote-1" } },
      { tipo: "card_criado", etapa_de: null, etapa_para: null, ator_id: "u1", em: "2026-11-13T09:00:00Z", detalhe: {} },
    ],
    ...over,
  };
}

export const CAPACIDADES = {
  pode_criar_lote: true,
  pode_ver_veredito: true,
  pode_gerir_pool: false,
  pode_aprovar_regras: false,
  pode_ativar_guia: false,
  dashboard: "org",
  modelo_configurado: true,
  economico_disponivel: true,
  economico_bloqueado_motivo: null,
  tipos_edicao_ativos: ["cor_luz"],
  limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
};

export const CONFIGURACOES = {
  tipos_edicao_ativos: ["cor_luz"],
  modelo_editor_imagem: "gpt-image-1",
  velocidade_padrao: "urgente",
  notificacoes_ativas: true,
};

export function fotoRevisao(over: Record<string, unknown> = {}) {
  return {
    id: "f1",
    url_antes: "https://cdn/f1-o.jpg",
    url_depois: "https://cdn/f1-e.jpg",
    comodo: null,
    estado: "aguardando_decisao",
    decisao: null,
    comentario: null,
    ...over,
  };
}
