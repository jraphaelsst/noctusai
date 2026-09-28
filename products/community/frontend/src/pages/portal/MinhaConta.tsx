/**
 * MinhaConta — `/portal` (ninho-vazio CONTRACT.md §Member portal / FE-B).
 *
 * Plan + status, grace banner when `assinatura.estado === "carencia"`
 * (with `carencia_ate` and the open invoice link), next charge, payments,
 * upgrade cards → `/assinar?plano=<id>` (the public checkout, pre-filled for
 * a logged-in member), and cancel with a plain confirmation that says
 * access continues until `pago_ate`. No dark patterns: cancelling is one
 * clearly-labelled button and one confirmation, nothing hidden.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Receipt } from "lucide-react";
import { formatDate } from "@noctusai/lib";
import { Button, Dialog, DialogBody, DialogFooter } from "@noctusai/lib/design-system";

import { EmptyState, ErrorState, FormError, Textarea } from "@/components/FormControls";
import { BOTAO_PRIMARIO, PortalCard, PortalShell } from "@/components/PortalShell";
import {
  ESTADOS_CANCELAVEIS,
  useCancelarAssinatura,
  useMinhaConta,
  type MinhaConta as MinhaContaData,
  type PortalAssinatura,
  type PortalPagamento,
} from "@/hooks/usePortal";
import { errorMessage } from "@/lib/errors";
import { formatBRLFromCents } from "@/lib/money";
import {
  ASSINATURA_ESTADO_LABEL,
  MEMBRO_STATUS_LABEL,
  NIVEL_DESCRICAO,
  PAGAMENTO_ESTADO_LABEL,
  labelDe,
  precoPorCiclo,
} from "@/lib/ninhoVazio";

/** The invoice a member in grace should pay: the most recent open one with a link. */
export function faturaEmAberto(pagamentos: PortalPagamento[]): PortalPagamento | null {
  const abertas = pagamentos.filter((p) => p.url_fatura && p.estado !== "pago" && p.estado !== "estornado");
  if (abertas.length === 0) return null;
  return [...abertas].sort((a, b) => (b.vencimento ?? "").localeCompare(a.vencimento ?? ""))[0];
}

function BannerCarencia({ assinatura, pagamentos }: { assinatura: PortalAssinatura; pagamentos: PortalPagamento[] }) {
  const fatura = faturaEmAberto(pagamentos);
  return (
    <div
      role="alert"
      data-testid="banner-carencia"
      className="flex flex-col gap-3 rounded-xl border border-amber-500/50 bg-amber-50 p-5 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100"
    >
      <p className="flex items-start gap-2 text-lg font-medium">
        <AlertTriangle className="mt-1 h-5 w-5 shrink-0" aria-hidden="true" />
        Não conseguimos confirmar o seu último pagamento.
      </p>
      <p className="text-base">
        Seu acesso continua normalmente até <strong>{formatDate(assinatura.carencia_ate)}</strong>. Se o
        pagamento for feito até lá, nada muda.
      </p>
      {fatura?.url_fatura ? (
        <a href={fatura.url_fatura} target="_blank" rel="noopener noreferrer" className={`${BOTAO_PRIMARIO} self-start`}>
          <Receipt className="h-5 w-5" aria-hidden="true" />
          Abrir a fatura ({formatBRLFromCents(fatura.valor_centavos)})
        </a>
      ) : (
        <p className="text-base">A fatura foi enviada para o seu e-mail.</p>
      )}
    </div>
  );
}

function SeuPlano({ conta }: { conta: MinhaContaData }) {
  const { plano, assinatura, membro } = conta;
  return (
    <PortalCard>
      <h2 className="text-lg font-semibold text-foreground">Seu plano</h2>
      {plano ? (
        <div className="mt-3 space-y-1">
          <p className="text-2xl font-semibold text-foreground" data-testid="plano-atual">
            {plano.nome}
          </p>
          <p className="text-base text-muted-foreground">{precoPorCiclo(plano.preco_centavos, plano.ciclo)}</p>
          <p className="text-base text-foreground">{NIVEL_DESCRICAO[plano.nivel_grupoterapia]}</p>
        </div>
      ) : (
        <p className="mt-3 text-base text-muted-foreground">Você ainda não tem um plano.</p>
      )}
      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm text-muted-foreground">Situação da conta</dt>
          <dd className="text-base font-medium text-foreground">{labelDe(MEMBRO_STATUS_LABEL, membro.status)}</dd>
        </div>
        {assinatura ? (
          <div>
            <dt className="text-sm text-muted-foreground">Assinatura</dt>
            <dd className="text-base font-medium text-foreground">{labelDe(ASSINATURA_ESTADO_LABEL, assinatura.estado)}</dd>
          </div>
        ) : null}
        {assinatura && assinatura.estado === "ativa" && assinatura.proxima_cobranca ? (
          <div>
            <dt className="text-sm text-muted-foreground">Próxima cobrança</dt>
            <dd className="text-base font-medium text-foreground" data-testid="proxima-cobranca">
              {formatDate(assinatura.proxima_cobranca)}
            </dd>
          </div>
        ) : null}
        {assinatura && assinatura.estado === "cancelada" ? (
          <div className="sm:col-span-2">
            <dt className="text-sm text-muted-foreground">Acesso</dt>
            <dd className="text-base text-foreground">
              Sua assinatura foi cancelada. Você continua com acesso até{" "}
              <strong>{formatDate(assinatura.pago_ate)}</strong>.
            </dd>
          </div>
        ) : null}
      </dl>
    </PortalCard>
  );
}

function Pagamentos({ pagamentos }: { pagamentos: PortalPagamento[] }) {
  return (
    <PortalCard>
      <h2 className="text-lg font-semibold text-foreground">Pagamentos</h2>
      {pagamentos.length === 0 ? (
        <EmptyState message="Nenhum pagamento por aqui ainda." />
      ) : (
        <ul className="mt-3 divide-y divide-border" data-testid="lista-pagamentos">
          {pagamentos.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="text-base font-medium text-foreground">{formatBRLFromCents(p.valor_centavos)}</p>
                <p className="text-sm text-muted-foreground">
                  {p.pago_em ? `Pago em ${formatDate(p.pago_em)}` : `Vencimento ${formatDate(p.vencimento)}`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-foreground">{labelDe(PAGAMENTO_ESTADO_LABEL, p.estado)}</span>
                {p.url_fatura ? (
                  <a
                    href={p.url_fatura}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-base font-medium text-primary underline underline-offset-2"
                  >
                    Ver fatura
                  </a>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </PortalCard>
  );
}

function OutrosPlanos({ conta }: { conta: MinhaContaData }) {
  const precoAtual = conta.plano?.preco_centavos ?? 0;
  const opcoes = conta.planos_disponiveis.filter(
    (p) => p.id !== conta.plano?.id && p.preco_centavos > precoAtual,
  );
  if (opcoes.length === 0) return null;
  return (
    <section className="space-y-3" aria-labelledby="outros-planos">
      <h2 id="outros-planos" className="text-lg font-semibold text-foreground">
        Quer ir além?
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {opcoes.map((p) => (
          <PortalCard key={p.id}>
            <p className="text-xl font-semibold text-foreground">{p.nome}</p>
            <p className="text-base text-muted-foreground">{precoPorCiclo(p.preco_centavos, p.ciclo)}</p>
            <p className="mt-2 text-base text-foreground">{NIVEL_DESCRICAO[p.nivel_grupoterapia]}</p>
            {p.descricao ? <p className="mt-1 text-base text-muted-foreground">{p.descricao}</p> : null}
            <Link to={`/assinar?plano=${encodeURIComponent(p.id)}`} className={`${BOTAO_PRIMARIO} mt-4 w-full`}>
              Quero o {p.nome}
            </Link>
          </PortalCard>
        ))}
      </div>
    </section>
  );
}

function CancelarAssinatura({ assinatura }: { assinatura: PortalAssinatura }) {
  const [aberto, setAberto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [feito, setFeito] = useState<PortalAssinatura | null>(null);
  const cancelar = useCancelarAssinatura();

  function fechar() {
    if (cancelar.isPending) return;
    setAberto(false);
    setErro(null);
  }

  function confirmar() {
    setErro(null);
    cancelar.mutate(
      { motivo: motivo.trim() ? motivo.trim() : null },
      {
        onSuccess: (res) => {
          setFeito(res);
          setAberto(false);
        },
        onError: (err) => setErro(errorMessage(err)),
      },
    );
  }

  if (feito) {
    return (
      <p role="status" className="flex items-start gap-2 text-base text-foreground" data-testid="cancelamento-feito">
        <CheckCircle2 className="mt-1 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        Assinatura cancelada. Você continua com acesso até {formatDate(feito.pago_ate)}.
      </p>
    );
  }

  return (
    <PortalCard>
      <h2 className="text-lg font-semibold text-foreground">Cancelar assinatura</h2>
      <p className="mt-2 text-base text-muted-foreground">
        Você pode cancelar quando quiser. O acesso continua até {formatDate(assinatura.pago_ate)} e, depois
        disso, sua conta segue no plano gratuito, com a plataforma e os conteúdos.
      </p>
      <Button variant="outline" className="mt-4 h-12 px-6 text-base" onClick={() => setAberto(true)}>
        Cancelar assinatura
      </Button>
      <Dialog open={aberto} onClose={fechar} title="Cancelar assinatura">
        <DialogBody>
          <div className="space-y-4 text-base">
            <p>
              Ao confirmar, as próximas cobranças deixam de acontecer. Seu acesso continua até{" "}
              <strong>{formatDate(assinatura.pago_ate)}</strong>.
            </p>
            <label className="block space-y-1">
              <span className="text-sm text-muted-foreground">Se quiser, conte o motivo (opcional)</span>
              <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={500} rows={3} />
            </label>
            <FormError message={erro} />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" className="h-11 px-5 text-base" onClick={fechar} disabled={cancelar.isPending}>
            Manter assinatura
          </Button>
          <Button variant="destructive" className="h-11 px-5 text-base" onClick={confirmar} disabled={cancelar.isPending}>
            {cancelar.isPending ? "Cancelando…" : "Confirmar cancelamento"}
          </Button>
        </DialogFooter>
      </Dialog>
    </PortalCard>
  );
}

export default function MinhaConta() {
  const { data, isPending, isFetching, error } = useMinhaConta();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const pagamentos = useMemo(() => data?.pagamentos ?? [], [data]);

  return (
    <PortalShell
      title={data ? `Olá, ${data.membro.nome.split(" ")[0]}` : "Minha conta"}
      subtitle={
        <>
          Aqui ficam o seu plano e os seus pagamentos.
          {/* lying-loading-ok: text-only suffix, never unmounts real content */}
          {isRefreshing ? " Atualizando…" : ""}
        </>
      }
    >
      {showSkeleton ? (
        <div className="space-y-4" data-testid="minha-conta-skeleton">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : !data ? (
        <ErrorState message={errorMessage(error)} />
      ) : (
        <>
          {data.assinatura?.estado === "carencia" ? (
            <BannerCarencia assinatura={data.assinatura} pagamentos={pagamentos} />
          ) : null}
          <SeuPlano conta={data} />
          <OutrosPlanos conta={data} />
          <Pagamentos pagamentos={pagamentos} />
          {data.assinatura && ESTADOS_CANCELAVEIS.includes(data.assinatura.estado) ? (
            <CancelarAssinatura assinatura={data.assinatura} />
          ) : null}
        </>
      )}
    </PortalShell>
  );
}
