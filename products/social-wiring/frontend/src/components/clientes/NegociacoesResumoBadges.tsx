/**
 * NegociacoesResumoBadges — the two card-party signals the brief asks for
 * (`pessoa-mesma-cpf-multideal-CONTRACT.md`, brief 2026-09-28 §3): "em N
 * outras negociações" (a Popover listing them) when `total_negociacoes > 1`,
 * and "possível duplicata" linking to the CPF review tab when
 * `candidatos_pendentes` is non-empty.
 *
 * Presentational — the caller (`NegociacoesDoClienteSection` for the
 * titular, `NegociacoesBadgeLazy` for a comprador/vendedor party row) owns
 * the fetch. Renders nothing when there is no signal (never an empty badge
 * row).
 */
import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import type { CandidatoPendenteCpf, NegociacaoDoCliente } from "@/hooks/useClientes";

/** pt-BR role label — same small local map `RevisaoCpfGrupoCard` carries
 *  (kept per-file rather than shared: neither file is the other's canonical
 *  home, and both trace to the same one-line contract shape). */
const PAPEL_LABEL: Record<string, string> = {
  titular: "Titular",
  comprador: "Comprador",
  conjuge: "Cônjuge",
  fiador: "Fiador",
  procurador: "Procurador",
  proprietario: "Proprietário",
  inventariante: "Inventariante",
  antigo_proprietario: "Antigo proprietário",
  outro: "Outro",
};

export interface NegociacoesResumoBadgesProps {
  /** Every entry in `outras` belongs to this SAME person (§2: one
   *  `negociacoes` response is always scoped to one `cliente_id`) —
   *  carried once here rather than per-row, to build the funil deep link
   *  (`/funil?atendimento=&cliente=`, see `FunilVendas`'s own docblock on
   *  reading it). */
  clienteId: string;
  outras: NegociacaoDoCliente[];
  candidatosPendentes: CandidatoPendenteCpf[];
}

export function NegociacoesResumoBadges({
  clienteId,
  outras,
  candidatosPendentes,
}: NegociacoesResumoBadgesProps) {
  if (outras.length === 0 && candidatosPendentes.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="negociacoes-resumo-badges">
      {outras.length > 0 && (
        <Popover>
          <PopoverTrigger asChild>
            <button type="button" data-testid="badge-outras-negociacoes">
              <Badge variant="secondary" className="cursor-pointer hover:bg-secondary/80">
                em {outras.length} outra{outras.length > 1 ? "s" : ""} negociaç
                {outras.length > 1 ? "ões" : "ão"}
              </Badge>
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-72">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Outras negociações
            </p>
            <ul className="space-y-2">
              {outras.map((n) => (
                <li key={n.atendimento_id} className="text-sm">
                  <Link
                    to={`/funil?atendimento=${encodeURIComponent(n.atendimento_id)}&cliente=${encodeURIComponent(clienteId)}`}
                    className="font-medium hover:underline"
                  >
                    {n.titulo || "Negociação sem título"}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {n.lado === "comprador" ? "Compra" : "Venda"} ·{" "}
                    {PAPEL_LABEL[n.papel] ?? n.papel}
                    {n.etapa_label ? ` · ${n.etapa_label}` : ""}
                    {n.imovel_codigo ? ` · imóvel ${n.imovel_codigo}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      )}
      {candidatosPendentes.length > 0 && (
        <Link to="/clientes/revisao?tab=cpf" data-testid="badge-possivel-duplicata">
          <Badge
            variant="outline"
            className="cursor-pointer border-destructive/40 bg-destructive/10 text-destructive hover:bg-destructive/20"
          >
            <ShieldAlert className="mr-1 h-3 w-3" />
            possível duplicata
          </Badge>
        </Link>
      )}
    </div>
  );
}
