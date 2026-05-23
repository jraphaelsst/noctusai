/**
 * <FleetControl/> — platform-admin panel to switch product containers ON/OFF
 * (start / stop / restart) and view live status.
 *
 * Backend: GET /api/fleet (status list) + POST /api/fleet/{slug}/{verb}
 * (verb ∈ start|stop|restart), both admin-gated. The container-control logic
 * is the seed primitive noctusai_lib.domain.fleet_control — this page is a thin
 * UI over it. Works identically for local dev and the prod VPS (the Core
 * container shares its host's docker socket).
 *
 * TanStack v5: the queryFn ALWAYS returns a value (never undefined — a 404 or
 * topology-degrade path returns an empty list, never undefined, so the
 * "data is undefined" failure mode can't surface). Mutations invalidate the
 * ['fleet'] key so status refreshes after every action.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Power, RotateCw, Play, Square } from 'lucide-react';
import { api } from '../lib/api';

type Verb = 'start' | 'stop' | 'restart';

interface FleetProduct {
  slug: string;
  container: string;
  display: string;
  state: string;
  health: string;
  running: boolean;
}

interface FleetResponse {
  products: FleetProduct[];
  count: number;
}

function useFleet() {
  return useQuery<FleetResponse, Error>({
    queryKey: ['fleet'],
    queryFn: async () => {
      // api.get returns the parsed JSON body directly. Guard the shape so the
      // queryFn NEVER returns undefined (TanStack v5 contract).
      const res = (await api.get('/api/fleet')) as Partial<FleetResponse> | null;
      const products = res?.products ?? [];
      return { products, count: products.length };
    },
    staleTime: 1000 * 10,
    retry: false,
  });
}

function StatusBadge({ p }: { p: FleetProduct }) {
  const tone = p.running
    ? p.health === 'unhealthy'
      ? 'bg-warning-light text-warning-foreground'
      : 'bg-success-light text-success-foreground'
    : p.state === 'absent'
      ? 'bg-muted text-muted-foreground'
      : 'bg-danger/10 text-danger';
  const label = p.running
    ? p.health === 'unhealthy'
      ? 'Instável'
      : p.health === 'starting'
        ? 'Iniciando'
        : 'Ativo'
    : p.state === 'absent'
      ? 'Ausente'
      : 'Parado';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${p.running ? 'bg-current' : 'bg-current opacity-60'}`} />
      {label}
    </span>
  );
}

export function FleetControl() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useFleet();

  const act = useMutation<FleetProduct, Error, { slug: string; verb: Verb }>({
    mutationFn: async ({ slug, verb }) => {
      // Returns the action result; never undefined.
      const res = (await api.post(`/api/fleet/${slug}/${verb}`)) as FleetProduct;
      return res;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet'] });
    },
  });

  const pendingFor = (slug: string) =>
    act.isPending && act.variables?.slug === slug ? act.variables?.verb : null;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Fleet Control</h1>
        <p className="text-sm text-muted-foreground">
          Ligue, desligue e reinicie os contêineres de cada produto. Funciona em
          dev local e no servidor de produção (o contêiner Core opera o docker
          do próprio host).
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          Falha ao carregar o status da frota: {error.message}
        </div>
      )}

      {act.isError && (
        <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          Ação falhou: {act.error.message}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Produto</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Contêiner</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  Carregando frota...
                </td>
              </tr>
            )}
            {!isLoading &&
              (data?.products ?? []).map((p) => {
                const pending = pendingFor(p.slug);
                return (
                  <tr key={p.slug} className="hover:bg-muted/40 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">{p.display}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{p.container}</td>
                    <td className="px-4 py-3"><StatusBadge p={p} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {p.running ? (
                          <button
                            disabled={!!pending}
                            onClick={() => act.mutate({ slug: p.slug, verb: 'stop' })}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
                            title="Desligar"
                          >
                            <Square className="h-3.5 w-3.5" />
                            {pending === 'stop' ? 'Desligando...' : 'Desligar'}
                          </button>
                        ) : (
                          <button
                            disabled={!!pending}
                            onClick={() => act.mutate({ slug: p.slug, verb: 'start' })}
                            className="inline-flex items-center gap-1.5 rounded-md bg-success text-success-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
                            title="Ligar"
                          >
                            <Play className="h-3.5 w-3.5" />
                            {pending === 'start' ? 'Ligando...' : 'Ligar'}
                          </button>
                        )}
                        <button
                          disabled={!!pending}
                          onClick={() => act.mutate({ slug: p.slug, verb: 'restart' })}
                          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
                          title="Reiniciar"
                        >
                          <RotateCw className={`h-3.5 w-3.5 ${pending === 'restart' ? 'animate-spin' : ''}`} />
                          {pending === 'restart' ? 'Reiniciando...' : 'Reiniciar'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            {!isLoading && (data?.products ?? []).length === 0 && !error && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  <Power className="mx-auto mb-2 h-6 w-6 opacity-40" />
                  Nenhum contêiner de produto encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default FleetControl;
