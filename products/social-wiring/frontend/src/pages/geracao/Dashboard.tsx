/**
 * Dashboard (P1, `/media-creation/dashboard`) — contract §7.1.
 * "Olá, {nome}!" + MarcaSwitcher · KPI cards (Headlines geradas · Roteiros
 * gerados · Itens pendentes -> Minha Pesquisa; CoreStudio's "Diagnóstico" is
 * dropped, §1.3) · Histórico with its order select · Headlines Sugeridas widget
 * (Criar roteiro / Editar / Abrir link). Loading = two signals off `data`.
 */
import { useState } from "react";
import { AlertCircle, ChevronDown, ExternalLink, FileText, Pencil } from "lucide-react";
import { Link } from "react-router-dom";

import { EditarHeadlineModal } from "@/components/geracao/headlines/EditarHeadlineModal";
import { MetricaPill } from "@/components/geracao/MetricaPill";
import { NoPostBadge } from "@/components/geracao/PostEsteira";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  HISTORICO_ORDEM_ROTULO,
  useDashboardCriacao,
  type HistoricoOrdem,
} from "@/hooks/geracao/useDashboardCriacao";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { EventoHistorico, Headline } from "@/types/geracao";

const SUGERIDAS = "/media-creation/headlines/sugeridas";
const PESQUISA_PENDENTES = "/media-creation/pesquisa?status=pending";

function dataHora(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleDateString("pt-BR")} - ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

function Kpi({ titulo, valor, to }: { titulo: string; valor: number; to?: string }) {
  const corpo = (
    <Card className={to ? "transition-colors hover:bg-muted/50" : undefined}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{titulo}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold" data-testid={`kpi-${titulo}`}>
          {valor.toLocaleString("pt-BR")}
        </p>
      </CardContent>
    </Card>
  );
  return to ? (
    <Link to={to} aria-label={`${titulo}: ver na Minha Pesquisa`}>
      {corpo}
    </Link>
  ) : (
    corpo
  );
}

function Historico({ eventos }: { eventos: EventoHistorico[] }) {
  if (eventos.length === 0) {
    return <p className="text-sm text-muted-foreground">Nenhuma atividade registrada ainda.</p>;
  }
  return (
    <ol className="space-y-3">
      {eventos.map((e, i) => (
        <li key={`${e.em}-${i}`} className="flex flex-col gap-0.5 border-l-2 pl-3 text-sm">
          <span>
            {e.ator ? <strong>{e.ator} </strong> : null}
            {e.texto}
          </span>
          <time className="text-xs text-muted-foreground" dateTime={e.em}>
            {dataHora(e.em)}
          </time>
        </li>
      ))}
    </ol>
  );
}

export default function Dashboard() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);
  const [ordem, setOrdem] = useState<HistoricoOrdem>("data_desc");
  const dash = useDashboardCriacao(marcaId, ordem);
  const data = dash.data;

  const [roteiroDe, setRoteiroDe] = useState<Headline | null>(null);
  const [editando, setEditando] = useState<Headline | null>(null);

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{data ? `Olá, ${data.saudacao_nome}!` : "Olá!"}</h1>
          <p className="text-sm text-muted-foreground">Veja como está a sua criação de mídia.</p>
        </div>
        <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
      </header>

      {!marcasQ.isPending && marcas.length === 0 && (
        <p className="rounded-md border p-4 text-sm text-muted-foreground">
          Cadastre uma marca para ver o seu dashboard.
        </p>
      )}

      {dash.showSkeleton && (
        <div className="space-y-4" data-testid="dashboard-skeleton">
          <div className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
          <Skeleton className="h-48 w-full" />
        </div>
      )}

      {dash.isError && !data && (
        <div role="alert" className="flex items-center justify-between rounded-md border p-4 text-sm">
          <span className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar o dashboard.
          </span>
          <Button size="sm" variant="outline" onClick={() => dash.refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {data && (
        <div className={dash.isRefreshing ? "space-y-6 opacity-70" : "space-y-6"} aria-busy={dash.isRefreshing}>
          <section className="grid gap-4 sm:grid-cols-3" aria-label="Indicadores">
            <Kpi titulo="Headlines geradas" valor={data.kpis.headlines_geradas} />
            <Kpi titulo="Roteiros gerados" valor={data.kpis.roteiros_gerados} />
            <Kpi titulo="Itens pendentes" valor={data.kpis.itens_pendentes} to={PESQUISA_PENDENTES} />
          </section>

          <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
            <Card>
              <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
                <div>
                  <CardTitle className="text-base">Histórico</CardTitle>
                  <p className="text-sm text-muted-foreground">Linha do tempo do seu uso.</p>
                </div>
                <select
                  aria-label="Filtrar histórico"
                  value={ordem}
                  onChange={(e) => setOrdem(e.target.value as HistoricoOrdem)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {(Object.keys(HISTORICO_ORDEM_ROTULO) as HistoricoOrdem[]).map((o) => (
                    <option key={o} value={o}>
                      {HISTORICO_ORDEM_ROTULO[o]}
                    </option>
                  ))}
                </select>
              </CardHeader>
              <CardContent>
                <Historico eventos={data.historico} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base">Headlines Sugeridas</CardTitle>
                <Link className="text-sm underline" to={SUGERIDAS}>
                  ver todas as headlines
                </Link>
              </CardHeader>
              <CardContent>
                {data.sugeridas.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Nenhuma headline sugerida ainda — elas aparecem aqui todos os dias quando sua Biblioteca tem
                    virais.
                  </p>
                ) : (
                  <ul className="divide-y">
                    {data.sugeridas.map((h) => (
                      <li key={h.id} className="flex items-center gap-3 py-2">
                        <span className="min-w-0 flex-1 truncate text-sm" title={h.texto}>
                          {h.texto}
                        </span>
                        <NoPostBadge post={h.post} />
                        <MetricaPill viral={h.viral} />
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size="sm" variant="outline" aria-label={`Ações da headline ${h.id}`}>
                              Ações <ChevronDown className="ml-1 h-3 w-3" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setRoteiroDe(h)}>
                              <FileText className="mr-2 h-4 w-4" /> Criar roteiro
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => setEditando(h)}>
                              <Pencil className="mr-2 h-4 w-4" /> Editar
                            </DropdownMenuItem>
                            {h.viral?.permalink ? (
                              <DropdownMenuItem asChild>
                                <a href={h.viral.permalink} target="_blank" rel="noopener noreferrer">
                                  <ExternalLink className="mr-2 h-4 w-4" /> Abrir link
                                </a>
                              </DropdownMenuItem>
                            ) : null}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      <RoteiroAvancadoModal
        open={!!roteiroDe}
        onOpenChange={(o) => !o && setRoteiroDe(null)}
        marcaId={marcaId}
        headlineInicial={roteiroDe ? { id: roteiroDe.id, texto: roteiroDe.texto } : undefined}
      />
      <EditarHeadlineModal
        open={!!editando}
        onOpenChange={(o) => !o && setEditando(null)}
        headline={editando}
      />
    </div>
  );
}
