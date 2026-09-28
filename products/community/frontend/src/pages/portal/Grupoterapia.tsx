/**
 * Portal Grupoterapia — `/portal/grupoterapia` (ninho-vazio CONTRACT.md
 * §Grupoterapia member + FE-B).
 *
 * Per session, by `acesso`:
 * - `bloqueado` → the plan doesn't include it: an upgrade card, NO room link.
 * - `ouvir` → "Assistir" link to the room.
 * - `falar` → reserve / cancel the speaking seat (`vagas_restantes`), plus
 *   the room link.
 * Every grupoterapia screen carries the care line (PortalShell footer).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, Clock, Mic, Headphones, Lock } from "lucide-react";
import { formatDate } from "@noctusai/lib";
import { Button } from "@noctusai/lib/design-system";

import { EmptyState, ErrorState, FormError } from "@/components/FormControls";
import { BOTAO_PRIMARIO, BOTAO_SECUNDARIO, PortalCard, PortalShell } from "@/components/PortalShell";
import {
  useCancelarReservaFala,
  usePortalGrupoterapia,
  useReservarVagaFala,
  type PortalSessao,
} from "@/hooks/usePortalGrupoterapia";
import { errorMessage } from "@/lib/errors";
import { NIVEL_DESCRICAO } from "@/lib/ninhoVazio";

function LinkSala({ sessao, rotulo }: { sessao: PortalSessao; rotulo: string }) {
  if (!sessao.link_sala) {
    return <p className="text-base text-muted-foreground">O link da sala aparece aqui antes do encontro.</p>;
  }
  return (
    <a href={sessao.link_sala} target="_blank" rel="noopener noreferrer" className={BOTAO_PRIMARIO}>
      {rotulo}
    </a>
  );
}

function VezDeFala({ sessao }: { sessao: PortalSessao }) {
  const reservar = useReservarVagaFala();
  const cancelar = useCancelarReservaFala();
  const [erro, setErro] = useState<string | null>(null);
  const ocupado = reservar.isPending || cancelar.isPending;

  const onError = (err: unknown) => setErro(errorMessage(err));

  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-base text-foreground">
        <Mic className="h-5 w-5 text-primary" aria-hidden="true" />
        {sessao.minha_reserva
          ? "Sua vez de fala está reservada."
          : sessao.vagas_restantes > 0
            ? `${sessao.vagas_restantes} ${sessao.vagas_restantes === 1 ? "vaga de fala disponível" : "vagas de fala disponíveis"}.`
            : "As vagas de fala deste encontro já foram preenchidas. Você ainda pode assistir."}
      </p>
      <FormError message={erro} />
      <div className="flex flex-wrap gap-3">
        {sessao.minha_reserva ? (
          <Button
            variant="outline"
            className="h-12 px-6 text-base"
            disabled={ocupado}
            onClick={() => {
              setErro(null);
              cancelar.mutate(sessao.id, { onError });
            }}
          >
            {cancelar.isPending ? "Cancelando…" : "Cancelar minha vez de fala"}
          </Button>
        ) : sessao.vagas_restantes > 0 ? (
          <Button
            variant="primary"
            className="h-12 px-6 text-base"
            disabled={ocupado}
            onClick={() => {
              setErro(null);
              reservar.mutate(sessao.id, { onError });
            }}
          >
            {reservar.isPending ? "Reservando…" : "Reservar minha vez de fala"}
          </Button>
        ) : null}
        <LinkSala sessao={sessao} rotulo="Entrar na sala" />
      </div>
    </div>
  );
}

function SessaoCard({ sessao }: { sessao: PortalSessao }) {
  return (
    <PortalCard>
      <article className="space-y-3" data-testid={`sessao-${sessao.id}`}>
        <h2 className="text-xl font-semibold text-foreground">{sessao.titulo}</h2>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-base text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays className="h-5 w-5" aria-hidden="true" />
            {formatDate(sessao.inicio, true)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-5 w-5" aria-hidden="true" />
            {sessao.duracao_minutos} minutos
          </span>
        </p>
        {sessao.descricao ? <p className="text-base text-foreground">{sessao.descricao}</p> : null}

        {sessao.acesso === "bloqueado" ? (
          <div className="space-y-3 rounded-lg bg-muted/50 p-4" data-testid="sessao-bloqueada">
            <p className="flex items-start gap-2 text-base text-foreground">
              <Lock className="mt-1 h-5 w-5 shrink-0" aria-hidden="true" />
              O seu plano ainda não inclui as grupoterapias. Com outro plano, você pode assistir — ou também
              ter a sua vez de fala.
            </p>
            <Link to="/portal" className={BOTAO_SECUNDARIO}>
              Ver planos
            </Link>
          </div>
        ) : sessao.acesso === "ouvir" ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 text-base text-foreground">
              <Headphones className="h-5 w-5 text-primary" aria-hidden="true" />
              Você participa ouvindo.
            </p>
            <LinkSala sessao={sessao} rotulo="Assistir" />
          </div>
        ) : (
          <VezDeFala sessao={sessao} />
        )}
      </article>
    </PortalCard>
  );
}

export default function PortalGrupoterapia() {
  const { data, isPending, isFetching, error } = usePortalGrupoterapia();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <PortalShell
      title="Grupoterapia"
      subtitle={
        <>
          Encontros ao vivo com a Mônica para atravessar juntas este momento.
          {/* lying-loading-ok: text-only suffix, never unmounts real content */}
          {isRefreshing ? " Atualizando…" : ""}
        </>
      }
    >
      {showSkeleton ? (
        <div className="space-y-4" data-testid="grupoterapia-skeleton">
          {[1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : !data ? (
        <ErrorState message={errorMessage(error)} />
      ) : (
        <>
          <p className="text-base text-foreground" data-testid="nivel-atual">
            Seu plano: {NIVEL_DESCRICAO[data.nivel]}.
          </p>
          {data.items.length === 0 ? (
            <EmptyState message="Nenhum encontro agendado no momento. Assim que houver, ele aparece aqui." />
          ) : (
            <div className="space-y-4">
              {data.items.map((s) => (
                <SessaoCard key={s.id} sessao={s} />
              ))}
            </div>
          )}
        </>
      )}
    </PortalShell>
  );
}
