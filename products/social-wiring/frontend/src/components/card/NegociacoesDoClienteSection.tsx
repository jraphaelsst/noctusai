/**
 * NegociacoesDoClienteSection — the titular's own "Negociações" block on the
 * client detail view (`pessoa-mesma-cpf-multideal-CONTRACT.md` §2/3, brief
 * 2026-09-28 item 2): every OTHER deal this person is attached to — título,
 * etapa, papel/lado, imóvel código — each linking to that deal's funil card.
 * Empty state when there is nothing besides the card already open.
 *
 * A CONTAINER, same shape as `EmpresasSection`/`ConflitosPendentesPanel`:
 * self-fetching, keyed by `clienteId`, rendered via `ClienteCardDialog`'s
 * `renderNegociacoesDoCliente` thunk so a card nobody opens never fires the
 * request. Also carries `NegociacoesResumoBadges` at its own header — the
 * titular IS the card (no separate collapsible "party row" to badge, unlike
 * a comprador/vendedor — see `NegociacoesBadgeLazy`'s docblock), so this one
 * fetch serves both brief items 2 and 3 for the titular.
 */
import { rotuloDePapel } from "@/types/cardHub";
import { AlertCircle, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

import { NegociacoesResumoBadges } from "@/components/clientes/NegociacoesResumoBadges";
import { outrasNegociacoes, useNegociacoesDoCliente } from "@/hooks/useClientes";

/** Same local pt-BR role map every negociações-facing file carries. */
/** `titular` is this list's own (the deal's owner is not a party row);
 *  every party role reads through the shared `rotuloDePapel`. */
const rotuloDoPapelNaNegociacao = (papel: string) =>
  papel === "titular" ? "Titular" : rotuloDePapel(papel);

export interface NegociacoesDoClienteSectionProps {
  clienteId: string;
  /** The FUNIL card's own `atendimentos.id` this modal is already open for
   *  (when opened with one) — excluded from the list per the contract's own
   *  "the FE computes N OTHER deals client-side" rule (§2). `undefined`
   *  (e.g. opened from the Clientes board, which has no atendimento) excludes
   *  nothing — every deal is an "other" one there. */
  atendimentoAtualId?: string | null;
}

export function NegociacoesDoClienteSection({
  clienteId,
  atendimentoAtualId,
}: NegociacoesDoClienteSectionProps) {
  const query = useNegociacoesDoCliente(clienteId);
  const loading = query.isPending && !query.data;
  const refreshing = query.isFetching && !!query.data;
  const outras = outrasNegociacoes(query.data?.negociacoes, atendimentoAtualId);
  const candidatosPendentes = query.data?.candidatos_pendentes ?? [];

  return (
    <div className="space-y-2 rounded-lg border p-3" data-testid="negociacoes-do-cliente">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Negociações
          </span>
          {refreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="negociacoes-do-cliente-refreshing"
            />
          )}
        </div>
        <NegociacoesResumoBadges
          clienteId={clienteId}
          outras={outras}
          candidatosPendentes={candidatosPendentes}
        />
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground">Carregando negociações…</p>
      ) : query.isError ? (
        <div className="flex items-center gap-2 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5" />
          <span>Não foi possível carregar as negociações.</span>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => query.refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : outras.length === 0 ? (
        <p className="text-xs text-muted-foreground" data-testid="negociacoes-do-cliente-vazio">
          Esta é a única negociação desta pessoa.
        </p>
      ) : (
        <ul className="space-y-1.5" data-testid="negociacoes-do-cliente-lista">
          {outras.map((n) => (
            <li
              key={n.atendimento_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-2 text-sm"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{n.titulo || "Negociação sem título"}</p>
                <p className="text-xs text-muted-foreground">
                  {n.lado === "comprador" ? "Compra" : "Venda"} · {rotuloDoPapelNaNegociacao(n.papel)}
                  {n.etapa_label ? ` · ${n.etapa_label}` : ""}
                  {n.imovel_codigo ? ` · imóvel ${n.imovel_codigo}` : ""}
                </p>
              </div>
              <Link
                to={`/funil?atendimento=${encodeURIComponent(n.atendimento_id)}&cliente=${encodeURIComponent(clienteId)}`}
                className="shrink-0 text-xs font-medium text-primary hover:underline"
                data-testid="negociacoes-do-cliente-abrir"
              >
                Abrir
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
