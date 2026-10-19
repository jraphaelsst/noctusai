import { Link } from "react-router-dom";

import type { Painel } from "@/hooks/useJuliaPainel";
import { JULIA_PAGES } from "@/nav/julia";

const CARD = "rounded-lg border bg-card p-4";

export function Atividades({ a }: { a: Painel["atividades"] }) {
  return (
    <section aria-labelledby="painel-atividades" className="space-y-3">
      <h2 id="painel-atividades" className="text-lg font-semibold">Atividades</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className={CARD} data-testid="atividade-consumo">
          <p className="text-sm text-muted-foreground">Consumo</p>
          {a.consumo ? (
            <>
              <p className="text-2xl font-bold">{a.consumo.turnos} turnos</p>
              <p className="text-sm">US$ {a.consumo.custo_usd.toFixed(2)} de US$ {a.consumo.limite_diario_usd.toFixed(2)} (limite diário)</p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Consumo indisponível</p>
          )}
        </div>
        <Link to={`${JULIA_PAGES.notificacoes.href}?tipo=cobranca_atendimento`} className={`${CARD} hover:bg-accent`} data-testid="atividade-cobrancas">
          <p className="text-sm text-muted-foreground">Cobranças de atendimento</p>
          <p className="text-2xl font-bold">{a.cobrancas}</p>
        </Link>
        <Link to={JULIA_PAGES.visitas.href} className={`${CARD} hover:bg-accent`} data-testid="atividade-pre-agendamentos">
          <p className="text-sm text-muted-foreground">Pré-agendamento de visitas</p>
          <p className="text-2xl font-bold">{a.pre_agendamentos}</p>
        </Link>
      </div>
    </section>
  );
}

const PERSONALIZACOES = [
  { nome: "Pré-agendamento de visita", href: JULIA_PAGES.visitas.href },
  { nome: "Perguntas essenciais", href: JULIA_PAGES.perguntas.href },
  { nome: "Reengajamento", href: JULIA_PAGES.reengajamento.href },
];

export function Personalizacoes() {
  return (
    <section aria-labelledby="painel-personalizacoes" className="space-y-3">
      <h2 id="painel-personalizacoes" className="text-lg font-semibold">Personalizações de comportamento</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {PERSONALIZACOES.map((p) => (
          <Link key={p.href} to={p.href} className={`${CARD} text-sm font-medium hover:bg-accent`}>{p.nome}</Link>
        ))}
      </div>
    </section>
  );
}
