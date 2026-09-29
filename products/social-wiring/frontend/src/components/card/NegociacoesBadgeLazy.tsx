/**
 * NegociacoesBadgeLazy — the comprador/vendedor party-row signal
 * (`pessoa-mesma-cpf-multideal-CONTRACT.md`, brief 2026-09-28 §3): "em N
 * outras negociações" / "possível duplicata" for a PARTY (not the titular —
 * see `NegociacoesDoClienteSection` for that one), rendered inside
 * `ClienteCardDialog.renderParte`'s `PessoaDocumentosSection`.
 *
 * 🔴 WHY THIS LIVES IN THE EXPANDED BODY, NOT THE COLLAPSED ROW HEADER.
 * `PessoaDocumentosSection`'s `children` is a thunk `CollapsibleSection`
 * (`@noctusai/lib/components`) invokes ONLY while the row is open — a closed
 * section costs nothing (that component's own docblock). §2's read is a
 * per-cliente call with no batched shape for "every party on this card at
 * once", so mounting this badge unconditionally in the row's HEADER (always
 * rendered, open or not) would fire one `GET .../negociacoes` per party the
 * instant the card opens — exactly the N+1 the brief asked to avoid
 * ("keep requests efficient... fetch lazily on expand"). Mounting it here
 * instead means the badge appears the moment the operator opens that
 * person's panel — one request, for the one row they are actually looking
 * at — rather than for every party on the card whether looked at or not.
 */
import { NegociacoesResumoBadges } from "@/components/clientes/NegociacoesResumoBadges";
import { outrasNegociacoes, useNegociacoesDoCliente } from "@/hooks/useClientes";

export interface NegociacoesBadgeLazyProps {
  clienteId: string;
  /** The current card's own atendimento — excluded, same rule as
   *  `NegociacoesDoClienteSection`. */
  excludeAtendimentoId?: string | null;
}

export function NegociacoesBadgeLazy({
  clienteId,
  excludeAtendimentoId,
}: NegociacoesBadgeLazyProps) {
  const query = useNegociacoesDoCliente(clienteId);
  if (query.isPending || query.isError || !query.data) return null;

  const outras = outrasNegociacoes(query.data.negociacoes, excludeAtendimentoId);
  return (
    <NegociacoesResumoBadges
      clienteId={clienteId}
      outras={outras}
      candidatosPendentes={query.data.candidatos_pendentes}
    />
  );
}
