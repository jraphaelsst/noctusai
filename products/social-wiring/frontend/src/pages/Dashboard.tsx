/**
 * Painel — the first screen after login.
 *
 * 🔴 WHAT THIS REPLACED, AND WHY
 * -------------------------------
 * This page used to be the connected YouTube channel's dashboard: four KPI
 * cards, a subscriber trend chart, top-5 videos, an upload queue. Measured in
 * production on 2026-08-25, a real-estate agency logging in saw all four cards
 * empty, an empty chart, and "Nenhum canal conectado" — after four requests
 * taking 1,6–1,9 s each for a channel that does not exist.
 *
 * Nothing was lost by replacing it: `YouTube.tsx` already carries the same
 * `VisaoGeralPanel` under its "Visão geral" tab, so the channel view is still
 * one click away for the orgs that use it. This page was duplicating it onto
 * the landing route.
 *
 * WHAT REPLACED IT
 * ----------------
 * Five numbers a person can act on today, each a link to the screen where the
 * acting happens. A metric nobody can act on is decoration, and that is
 * precisely what this route was.
 */
import { Link } from "react-router-dom";
import {
  AlarmClock,
  CalendarDays,
  Handshake,
  Sparkles,
  Users,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { usePainel, type PainelItem } from "@/hooks/usePainel";

const BRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

function quando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function diasAtras(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const dias = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (dias <= 0) return "hoje";
  return `há ${dias} dia${dias === 1 ? "" : "s"}`;
}

const TIPO_LABEL: Record<string, string> = {
  visita: "Visita",
  ligacao: "Ligação",
  reuniao: "Reunião",
  outro: "Compromisso",
};

function Tile({
  icone: Icone,
  rotulo,
  valor,
  detalhe,
  para,
  destaque,
  testid,
}: {
  icone: typeof Users;
  rotulo: string;
  valor: string;
  detalhe: string;
  para: string;
  destaque?: boolean;
  testid: string;
}) {
  return (
    <Link
      to={para}
      className="block rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      data-testid={testid}
    >
      <Card className={destaque ? "border-primary/40 bg-primary/5 h-full" : "h-full"}>
        <CardContent className="p-5">
          <div className="mb-3 flex items-center gap-2 text-muted-foreground">
            <Icone className="h-4 w-4" />
            <span className="text-xs font-medium uppercase tracking-wide">
              {rotulo}
            </span>
          </div>
          <p className="text-3xl font-semibold tabular-nums">{valor}</p>
          <p className="mt-1 text-xs text-muted-foreground">{detalhe}</p>
        </CardContent>
      </Card>
    </Link>
  );
}

function ListaVazia({ children }: { children: string }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{children}</p>;
}

export default function Dashboard() {
  const { data, loading, isError, refetch } = usePainel();

  if (loading && !data) {
    return (
      <div className="container mx-auto p-4 sm:p-6" data-testid="painel-loading">
        <Skeleton className="mb-6 h-9 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="container mx-auto p-4 sm:p-6">
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="text-sm text-muted-foreground">
              Não foi possível carregar o painel.
            </p>
            <Button variant="outline" onClick={() => refetch()} data-testid="painel-retry">
              Tentar novamente
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="mb-1 text-2xl font-bold">Painel</h1>
        <p className="text-sm text-muted-foreground">
          O que precisa de você hoje.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Tile
          testid="painel-tile-novos"
          icone={Sparkles}
          rotulo="Leads novos"
          valor={data.novos.toLocaleString("pt-BR")}
          detalhe="chegaram nos últimos 7 dias"
          para="/funil"
        />
        <Tile
          testid="painel-tile-parados"
          icone={AlarmClock}
          rotulo="Parados"
          valor={data.parados.toLocaleString("pt-BR")}
          detalhe="sem movimento há 14 dias ou mais"
          para="/funil"
          destaque={data.parados > 0}
        />
        <Tile
          testid="painel-tile-agenda"
          icone={CalendarDays}
          rotulo="Agenda"
          valor={data.agendamentos.toLocaleString("pt-BR")}
          detalhe="compromissos nos próximos 7 dias"
          para="/funil"
        />
        <Tile
          testid="painel-tile-revisao"
          icone={Users}
          rotulo="Duplicados"
          valor={data.revisao.toLocaleString("pt-BR")}
          detalhe="grupos aguardando decisão"
          para="/clientes/revisao"
        />
        <Tile
          testid="painel-tile-negociacao"
          icone={Handshake}
          rotulo="Em negociação"
          valor={BRL.format(data.em_negociacao)}
          detalhe="soma dos valores negociados em aberto"
          para="/funil"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="p-5">
            <h2 className="mb-3 font-semibold">Próximos compromissos</h2>
            {data.proximos_agendamentos.length === 0 ? (
              <ListaVazia>Nada agendado para os próximos 7 dias.</ListaVazia>
            ) : (
              <ul className="divide-y">
                {data.proximos_agendamentos.map((i: PainelItem) => (
                  <li
                    key={`${i.atendimento_id}-${i.quando}`}
                    className="flex items-center justify-between gap-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {i.titulo || "Atendimento"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {TIPO_LABEL[i.tipo ?? "outro"] ?? "Compromisso"}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {quando(i.quando)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <h2 className="mb-3 font-semibold">Parados há mais tempo</h2>
            {data.atendimentos_parados.length === 0 ? (
              <ListaVazia>Nenhum atendimento esquecido. Bom sinal.</ListaVazia>
            ) : (
              <ul className="divide-y">
                {data.atendimentos_parados.map((i: PainelItem) => (
                  <li
                    key={i.atendimento_id}
                    className="flex items-center justify-between gap-3 py-2.5"
                  >
                    <p className="min-w-0 truncate text-sm font-medium">
                      {i.titulo || "Atendimento"}
                    </p>
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {diasAtras(i.quando)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
