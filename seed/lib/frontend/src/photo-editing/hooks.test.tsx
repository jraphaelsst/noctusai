/**
 * Tests for the Edição de Fotos hook factory — focused on the binding
 * loading-state contract (CLAUDE.md §1 / contract §9): every read hook must
 * expose `showSkeleton`/`isRefreshing` already correctly computed, and
 * `useRevisao` must carry `placeholderData` so a `loteId` key change never
 * drops to an empty list mid-fetch.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import {
  createEdicaoFotosHooks,
  type Capacidades,
  type FotoRevisao,
  type LoteResumo,
  type LotesPage,
} from './hooks';
import type { ApiClient } from '../api';

afterEach(cleanup);

function makeApi(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
    ...overrides,
  } as unknown as ApiClient;
}

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

const CAPACIDADES: Capacidades = {
  pode_criar_lote: true,
  pode_ver_veredito: false,
  pode_gerir_pool: false,
  pode_aprovar_regras: false,
  pode_ativar_guia: false,
  dashboard: null,
  modelo_configurado: true,
  economico_disponivel: false,
  economico_bloqueado_motivo: 'modelo_sem_batch',
  tipos_edicao_ativos: ['cor_luz'],
  limites: { fotos_por_lote: 100, bytes_por_foto: 26214400 },
};

// ── useCapacidades — showSkeleton / not lying ────────────────────────────────

describe('useCapacidades: loading contract', () => {
  it('showSkeleton is true while pending with no data, false once resolved', async () => {
    const api = makeApi({ get: vi.fn().mockResolvedValue(CAPACIDADES) });
    const { useCapacidades } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useCapacidades(), { wrapper: wrapper() });

    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await waitFor(() => expect(result.current.capacidades).toEqual(CAPACIDADES));
    expect(result.current.showSkeleton).toBe(false);
  });

  it('isRefreshing is true (not showSkeleton) during a background refetch that keeps existing data', async () => {
    let resolveSecond: (v: Capacidades) => void;
    const secondCall = new Promise<Capacidades>((resolve) => {
      resolveSecond = resolve;
    });
    const get = vi
      .fn()
      .mockResolvedValueOnce(CAPACIDADES)
      .mockReturnValueOnce(secondCall);
    const api = makeApi({ get });
    const { useCapacidades } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useCapacidades(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.capacidades).toEqual(CAPACIDADES));

    act(() => {
      void result.current.refetch();
    });

    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    // Never a lying skeleton — data is still there, this is a refresh, not a load.
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.capacidades).toEqual(CAPACIDADES);

    resolveSecond!({ ...CAPACIDADES, pode_criar_lote: false });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.capacidades?.pode_criar_lote).toBe(false);
  });
});

// ── useRevisao — placeholderData across a loteId key change ─────────────────

describe('useRevisao: batch-key change never drops to empty', () => {
  const FOTOS_LOTE_A: FotoRevisao[] = [
    {
      id: 'f1',
      url_antes: 'a.jpg',
      url_depois: 'a-edit.jpg',
      estado: 'aguardando_decisao',
      decisao: null,
      comentario: null,
    },
  ];

  it('keeps the previous batch photos as placeholder data while the next batch loads', async () => {
    let resolveLoteB: (v: FotoRevisao[]) => void;
    const loteBPromise = new Promise<FotoRevisao[]>((resolve) => {
      resolveLoteB = resolve;
    });
    const get = vi.fn((path: string): Promise<any> => {
      if (path === '/api/edicao-fotos/revisao/lote-a') return Promise.resolve(FOTOS_LOTE_A);
      if (path === '/api/edicao-fotos/revisao/lote-b') return loteBPromise;
      throw new Error(`unexpected path ${path}`);
    });
    const api = makeApi({ get });
    const { useRevisao } = createEdicaoFotosHooks(api);

    const Wrapper = wrapper();
    const { result, rerender } = renderHook(({ loteId }) => useRevisao(loteId), {
      wrapper: Wrapper,
      initialProps: { loteId: 'lote-a' as string },
    });

    await waitFor(() => expect(result.current.fotos).toEqual(FOTOS_LOTE_A));

    rerender({ loteId: 'lote-b' });

    // placeholderData keeps lote A's photos visible — never an empty flash.
    expect(result.current.fotos).toEqual(FOTOS_LOTE_A);
    expect(result.current.isRefreshing).toBe(true);
    expect(result.current.showSkeleton).toBe(false);

    resolveLoteB!([]);
    await waitFor(() => expect(result.current.fotos).toEqual([]));
  });

  it('does not fire the query when loteId is falsy', () => {
    const get = vi.fn();
    const api = makeApi({ get });
    const { useRevisao } = createEdicaoFotosHooks(api);
    renderHook(() => useRevisao(undefined), { wrapper: wrapper() });
    expect(get).not.toHaveBeenCalled();
  });
});

// ── useLotes — paginated list, placeholderData across a page change ────────

describe('useLotes: list + placeholderData', () => {
  const LOTE_A: LoteResumo = {
    id: 'l1',
    nome: 'Lote 1',
    criado_em: '2026-09-16T00:00:00Z',
    imovel: null,
    velocidade: 'urgente',
    estado_agregado: 'processando',
    total_fotos: 10,
    fotos_decididas: 0,
  };
  const PAGE_1: LotesPage = { items: [LOTE_A], page: 1, page_size: 50, total: 1 };

  it('requests page/page_size and exposes items/total, showSkeleton only on first load', async () => {
    const get = vi.fn().mockResolvedValue(PAGE_1);
    const api = makeApi({ get });
    const { useLotes } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useLotes(), { wrapper: wrapper() });

    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.lotes).toEqual([LOTE_A]));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/lotes', { page: 1, page_size: 50 });
    expect(result.current.total).toBe(1);
    expect(result.current.showSkeleton).toBe(false);
  });

  it('keeps the previous page as placeholder data across a page change (never an empty flash)', async () => {
    let resolvePage2: (v: LotesPage) => void;
    const page2Promise = new Promise<LotesPage>((resolve) => {
      resolvePage2 = resolve;
    });
    const get = vi.fn((_path: string, params: any): Promise<any> => {
      if (params.page === 1) return Promise.resolve(PAGE_1);
      return page2Promise;
    });
    const api = makeApi({ get });
    const { useLotes } = createEdicaoFotosHooks(api);

    const { result, rerender } = renderHook(({ page }) => useLotes({ page }), {
      wrapper: wrapper(),
      initialProps: { page: 1 },
    });

    await waitFor(() => expect(result.current.lotes).toEqual([LOTE_A]));

    rerender({ page: 2 });

    expect(result.current.lotes).toEqual([LOTE_A]);
    expect(result.current.isRefreshing).toBe(true);
    expect(result.current.showSkeleton).toBe(false);

    resolvePage2!({ items: [], page: 2, page_size: 50, total: 1 });
    await waitFor(() => expect(result.current.lotes).toEqual([]));
  });
});

// ── useUploadFotos — multipart field shape ──────────────────────────────────

describe('useUploadFotos: multipart field name', () => {
  it('appends every file under the "fotos" field and posts to the lote-scoped route', async () => {
    const upload = vi.fn().mockResolvedValue({ ok: true });
    const api = makeApi({ upload });
    const { useUploadFotos } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useUploadFotos(), { wrapper: wrapper() });

    const file = new File(['x'], 'foto.jpg', { type: 'image/jpeg' });
    await act(async () => {
      await result.current.mutateAsync({ loteId: 'lote-1', files: [file] });
    });

    expect(upload).toHaveBeenCalledTimes(1);
    const [path, form] = upload.mock.calls[0];
    expect(path).toBe('/api/edicao-fotos/lotes/lote-1/fotos');
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).getAll('fotos')).toEqual([file]);
  });
});

// ── useBaixarZip — download + 409 "not ready" surfaces as ApiError ─────────

describe('useBaixarZip: zip download', () => {
  it('downloads via api.download() and triggers a browser save', async () => {
    const blob = new Blob(['zip-bytes']);
    const download = vi.fn().mockResolvedValue(blob);
    const api = makeApi({ download });
    const { useBaixarZip } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useBaixarZip(), { wrapper: wrapper() });

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await act(async () => {
      await result.current.mutateAsync({ loteId: 'lote-1', nomeArquivo: 'lote-1.zip' });
    });

    expect(download).toHaveBeenCalledWith('/api/edicao-fotos/lotes/lote-1/zip');
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
  });

  it('propagates a 409 (fotos ainda sem decisão) as a rejected mutation', async () => {
    const { ApiError } = await import('../api');
    const download = vi.fn().mockRejectedValue(new ApiError(409, 'pendente'));
    const api = makeApi({ download });
    const { useBaixarZip } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useBaixarZip(), { wrapper: wrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ loteId: 'lote-1', nomeArquivo: 'lote-1.zip' }),
      ).rejects.toMatchObject({ status: 409 });
    });
  });
});

// ── W6: reference pool (multipart + pool state) + guias de estilo ─────────

describe('useCriarReferencia: multipart pair upload', () => {
  it('uploads both files + tags through api.upload (never api.post)', async () => {
    const upload = vi.fn().mockResolvedValue({ id: 'r1' });
    const post = vi.fn();
    const api = makeApi({ upload, post });
    const { useCriarReferencia } = createEdicaoFotosHooks(api);
    const { result } = renderHook(() => useCriarReferencia(), { wrapper: wrapper() });

    const antes = new File(['a'], 'antes.jpg', { type: 'image/jpeg' });
    const depois = new File(['d'], 'depois.jpg', { type: 'image/jpeg' });
    await act(async () => {
      await result.current.mutateAsync({
        antes,
        depois,
        comodo: 'sala',
        tipos_edicao: ['cor_luz', 'ceu'],
        nota: 'Céu limpo',
      });
    });

    expect(post).not.toHaveBeenCalled();
    const [path, form] = upload.mock.calls[0];
    expect(path).toBe('/api/edicao-fotos/referencias');
    const data = form as FormData;
    expect(data.get('antes')).toEqual(antes);
    expect(data.get('depois')).toEqual(depois);
    expect(data.get('comodo')).toBe('sala');
    expect(data.getAll('tipos_edicao')).toEqual(['cor_luz', 'ceu']);
    expect(data.get('nota')).toBe('Céu limpo');
  });

  it('omits an empty note', async () => {
    const upload = vi.fn().mockResolvedValue({ id: 'r1' });
    const { useCriarReferencia } = createEdicaoFotosHooks(makeApi({ upload }));
    const { result } = renderHook(() => useCriarReferencia(), { wrapper: wrapper() });
    const f = new File(['x'], 'x.jpg');
    await act(async () => {
      await result.current.mutateAsync({ antes: f, depois: f, comodo: 'outro', tipos_edicao: [], nota: null });
    });
    expect((upload.mock.calls[0][1] as FormData).has('nota')).toBe(false);
  });
});

describe('useReferencias: paged pool with occupancy', () => {
  it('passes page + archived toggle and exposes items, pool and opcoes', async () => {
    const page = {
      items: [{ id: 'r1', antes_url: 'a', depois_url: 'd', comodo: 'sala', tipos_edicao: [], nota: null }],
      page: 1,
      page_size: 24,
      total: 1,
      pool: { pares_ativos: 1, limite_pares: 5, cheio: false },
      opcoes: { comodos: ['sala'], tipos_edicao: ['ceu'] },
    };
    const get = vi.fn().mockResolvedValue(page);
    const { useReferencias } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useReferencias({ page: 1, pageSize: 24, incluirArquivadas: true }), {
      wrapper: wrapper(),
    });
    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/referencias', {
      page: 1,
      page_size: 24,
      incluir_arquivadas: true,
    });
    expect(result.current.referencias).toHaveLength(1);
    expect(result.current.pool).toEqual(page.pool);
    expect(result.current.opcoes).toEqual(page.opcoes);
  });

  it('keeps the previous page as placeholder while the archived toggle flips', async () => {
    const first = { items: [{ id: 'r1' }], page: 1, page_size: 50, total: 1, pool: { pares_ativos: 1, limite_pares: null, cheio: false }, opcoes: { comodos: [], tipos_edicao: [] } };
    let resolveSecond: (v: unknown) => void = () => {};
    const get = vi
      .fn()
      .mockResolvedValueOnce(first)
      .mockImplementationOnce(() => new Promise((r) => { resolveSecond = r; }));
    const { useReferencias } = createEdicaoFotosHooks(makeApi({ get }));
    const { result, rerender } = renderHook(
      ({ arquivadas }: { arquivadas: boolean }) => useReferencias({ incluirArquivadas: arquivadas }),
      { wrapper: wrapper(), initialProps: { arquivadas: false } },
    );
    await waitFor(() => expect(result.current.referencias).toHaveLength(1));
    rerender({ arquivadas: true });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.referencias).toHaveLength(1);
    await act(async () => {
      resolveSecond({ ...first, items: [{ id: 'r1' }, { id: 'r0' }], total: 2 });
    });
    await waitFor(() => expect(result.current.referencias).toHaveLength(2));
  });
});

describe('guias de estilo hooks', () => {
  it('useGuias exposes versions + the active version number', async () => {
    const get = vi.fn().mockResolvedValue({ items: [{ versao: 1 }], page: 1, page_size: 20, total: 1, versao_ativa: null });
    const { useGuias } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useGuias(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/guias', { page: 1, page_size: 20 });
    expect(result.current.guias).toHaveLength(1);
    expect(result.current.versaoAtiva).toBeNull();
  });

  it('mutations hit the contract routes', async () => {
    const post = vi.fn().mockResolvedValue({});
    const api = makeApi({ post });
    const hooks = createEdicaoFotosHooks(api);
    const w = wrapper();
    const criar = renderHook(() => hooks.useCriarGuia(), { wrapper: w }).result;
    const ativar = renderHook(() => hooks.useAtivarGuia(), { wrapper: w }).result;
    const restaurar = renderHook(() => hooks.useRestaurarGuia(), { wrapper: w }).result;
    const regenerar = renderHook(() => hooks.useRegenerarGuia(), { wrapper: w }).result;
    await act(async () => {
      await criar.current.mutateAsync({ texto: '- Luz' });
      await ativar.current.mutateAsync(2);
      await restaurar.current.mutateAsync(1);
      await regenerar.current.mutateAsync();
    });
    expect(post.mock.calls).toEqual([
      ['/api/edicao-fotos/guias', { texto: '- Luz' }],
      ['/api/edicao-fotos/guias/2/ativar', {}],
      ['/api/edicao-fotos/guias/1/restaurar', {}],
      ['/api/edicao-fotos/guias/regenerar', {}],
    ]);
  });

  it('useConfiguracoesPlataforma stays idle (no skeleton, no request) when disabled', () => {
    const get = vi.fn();
    const { useConfiguracoesPlataforma } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useConfiguracoesPlataforma({ enabled: false }), { wrapper: wrapper() });
    expect(result.current.showSkeleton).toBe(false);
    expect(get).not.toHaveBeenCalled();
  });
});

describe('regras de aprendizado hooks (W7)', () => {
  it('useRegras sends the status filter only when set', async () => {
    const get = vi.fn().mockResolvedValue({ items: [{ id: 'r1' }], total: 1 });
    const { useRegras } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useRegras({ status: 'proposta' }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/regras', { status: 'proposta' });
    expect(result.current.regras).toHaveLength(1);
    expect(result.current.total).toBe(1);

    get.mockClear();
    renderHook(() => useRegras(), { wrapper: wrapper() });
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/regras', undefined);
  });

  it('mutations hit the contract routes and invalidate regras + guia-efetivo', async () => {
    const post = vi.fn().mockResolvedValue({});
    const put = vi.fn().mockResolvedValue({});
    const api = makeApi({ post, put });
    const hooks = createEdicaoFotosHooks(api);
    const w = wrapper();
    const criar = renderHook(() => hooks.useCriarRegra(), { wrapper: w }).result;
    const editar = renderHook(() => hooks.useEditarRegra(), { wrapper: w }).result;
    const aprovar = renderHook(() => hooks.useAprovarRegra(), { wrapper: w }).result;
    const rejeitar = renderHook(() => hooks.useRejeitarRegra(), { wrapper: w }).result;
    const proporAgora = renderHook(() => hooks.useProporRegrasAgora(), { wrapper: w }).result;
    await act(async () => {
      await criar.current.mutateAsync({ texto: 'Não X' });
      await editar.current.mutateAsync({ regraId: 'r1', texto: 'Não X revisado' });
      await aprovar.current.mutateAsync('r1');
      await rejeitar.current.mutateAsync('r1');
      await proporAgora.current.mutateAsync();
    });
    expect(post.mock.calls).toEqual([
      ['/api/edicao-fotos/regras', { texto: 'Não X' }],
      ['/api/edicao-fotos/regras/r1/aprovar', {}],
      ['/api/edicao-fotos/regras/r1/rejeitar', {}],
      ['/api/edicao-fotos/regras/propor-agora', {}],
    ]);
    expect(put).toHaveBeenCalledWith('/api/edicao-fotos/regras/r1', { texto: 'Não X revisado' });
  });

  it('useGuiaEfetivo exposes the current guide + history, and tolerates atual=null', async () => {
    const get = vi.fn().mockResolvedValue({
      atual: null,
      historico: { items: [], page: 1, page_size: 20, total: 0 },
    });
    const { useGuiaEfetivo } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useGuiaEfetivo(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/regras/guia-efetivo', { page: 1, page_size: 20 });
    expect(result.current.atual).toBeNull();
    expect(result.current.historico).toEqual([]);
    expect(result.current.total).toBe(0);
  });
});

describe('curadores hooks', () => {
  it('useCuradores exposes the roster', async () => {
    const get = vi.fn().mockResolvedValue({
      items: [{ user_id: 'u1', nome: 'Cris', email: 'cris@x.com', concedido_por: null, created_at: null }],
      total: 1,
    });
    const { useCuradores } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useCuradores(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/curadores');
    expect(result.current.curadores).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('useAdicionarCurador / useRemoverCurador hit the contract routes', async () => {
    const post = vi.fn().mockResolvedValue({});
    const del = vi.fn().mockResolvedValue({});
    const hooks = createEdicaoFotosHooks(makeApi({ post, delete: del }));
    const w = wrapper();
    const adicionar = renderHook(() => hooks.useAdicionarCurador(), { wrapper: w }).result;
    const remover = renderHook(() => hooks.useRemoverCurador(), { wrapper: w }).result;
    await act(async () => {
      await adicionar.current.mutateAsync({ user_id: 'u2' });
      await remover.current.mutateAsync('u1');
    });
    expect(post).toHaveBeenCalledWith('/api/edicao-fotos/curadores', { user_id: 'u2' });
    expect(del).toHaveBeenCalledWith('/api/edicao-fotos/curadores/u1');
  });
});

describe('notificação preferência hooks (self-service opt-in)', () => {
  it('useNotificacaoPreferencia fetches the caller own row', async () => {
    const get = vi.fn().mockResolvedValue({ ativo: true, whatsapp_number: '+5511999998888' });
    const { useNotificacaoPreferencia } = createEdicaoFotosHooks(makeApi({ get }));
    const { result } = renderHook(() => useNotificacaoPreferencia(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(get).toHaveBeenCalledWith('/api/edicao-fotos/notificacoes/preferencias');
    expect(result.current.preferencia).toEqual({ ativo: true, whatsapp_number: '+5511999998888' });
  });

  it('useAtualizarNotificacaoPreferencia PUTs the whole object', async () => {
    const put = vi.fn().mockResolvedValue({ ativo: true, whatsapp_number: null });
    const { useAtualizarNotificacaoPreferencia } = createEdicaoFotosHooks(makeApi({ put }));
    const { result } = renderHook(() => useAtualizarNotificacaoPreferencia(), { wrapper: wrapper() });
    await act(async () => {
      await result.current.mutateAsync({ ativo: true, whatsapp_number: null });
    });
    expect(put).toHaveBeenCalledWith('/api/edicao-fotos/notificacoes/preferencias', {
      ativo: true, whatsapp_number: null,
    });
  });
});
