/**
 * AtendimentoImoveisSection — the imóveis linked to THIS atendimento
 * (contract §3.1–3.4): photo, código, endereço, valor, origem, a "Principal"
 * badge; add (registry-backed `ImovelCodigoPicker`), remove, set principal.
 *
 * 🔴 "IMÓVEL PENDENTE" IS A WARNING, NOT AN EMPTY STATE. An atendimento can
 * exist with no imóvel (an inbound lead that arrived without a resolvable
 * código is accepted and flagged, never dropped). The server derives
 * `imovel_pendente` from "zero live rows"; the section shows it loudly so the
 * corretor fills the gap, and the picker sits right under it.
 *
 * Self-fetching by `clienteId` (same precedent as `CertidoesMatrizSection`),
 * so the dialog needs no new prop plumbing per field.
 *
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching &&
 * !!data` (computed in the hook) — rows that exist are never unmounted by a
 * refetch. → KB § PATTERNS/frontend/lying-loading-state.md
 */
import { useState } from "react";
import { AlertTriangle, Loader2, Plus, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  useAtendimentoImoveis,
  useAtendimentoImoveisMutations,
} from "@/hooks/useAtendimentoImoveis";
import { formatCurrency } from "@/lib/utils";
import type { AtendimentoImovel, AtendimentoImovelOrigem } from "@/types/atendimentoImoveis";

import { ImovelCodigoPicker } from "./ImovelCodigoPicker";
import { mensagemDoErro } from "./mensagemDoErro";

export const ORIGEM_LABEL: Record<AtendimentoImovelOrigem, string> = {
  lead: "Lead",
  manual: "Manual",
  campanha: "Campanha",
  negociacao: "Negociação",
};

export interface AtendimentoImoveisSectionProps {
  clienteId: string;
  atendimentoId?: string | null;
}

function enderecoDe(item: AtendimentoImovel): string {
  const { imovel } = item;
  return (
    imovel.endereco ??
    ([imovel.bairro, imovel.cidade].filter(Boolean).join(", ") || "Endereço não informado")
  );
}

function valorDe(item: AtendimentoImovel): string | null {
  const { valor, valor_tipo } = item.imovel;
  if (valor == null) return null;
  return `${formatCurrency(valor)}${valor_tipo === "locacao" ? " /mês" : ""}`;
}

export function AtendimentoImoveisSection({
  clienteId,
  atendimentoId,
}: AtendimentoImoveisSectionProps) {
  const query = useAtendimentoImoveis(clienteId, atendimentoId);
  const { adicionar, definirPrincipal, remover } = useAtendimentoImoveisMutations(clienteId);
  const [codigo, setCodigo] = useState<string | null>(null);

  const items = query.data?.items ?? [];
  const pendente = query.data?.imovel_pendente === true;
  const ocupado = adicionar.isPending || definirPrincipal.isPending || remover.isPending;

  function handleAdicionar() {
    if (!codigo) return;
    adicionar.mutate(
      {
        codigo,
        origem: "manual",
        ...(atendimentoId ? { atendimento_id: atendimentoId } : {}),
      },
      {
        onSuccess: () => setCodigo(null),
        onError: (err) => toast.error(mensagemDoErro(err, "Não foi possível vincular o imóvel.")),
      },
    );
  }

  return (
    <section className="space-y-3" data-testid="atendimento-imoveis-section">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">Imóveis do atendimento</h3>
        {query.isRefreshing && (
          <Loader2
            className="h-3.5 w-3.5 animate-spin text-muted-foreground"
            data-testid="atendimento-imoveis-refreshing"
          />
        )}
      </div>

      {query.showSkeleton ? (
        <p className="text-sm text-muted-foreground" data-testid="atendimento-imoveis-loading">
          Carregando…
        </p>
      ) : query.isError && !query.data ? (
        <p className="text-sm text-destructive" role="alert" data-testid="atendimento-imoveis-erro">
          {mensagemDoErro(query.error, "Não foi possível carregar os imóveis do atendimento.")}
        </p>
      ) : (
        <>
          {pendente && (
            <div
              className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
              role="alert"
              data-testid="imovel-pendente-aviso"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Imóvel pendente</p>
                <p className="text-xs">
                  Este atendimento ainda não tem imóvel vinculado. Selecione um abaixo.
                </p>
              </div>
            </div>
          )}

          {items.length === 0 && !pendente && (
            <p className="text-sm text-muted-foreground" data-testid="atendimento-imoveis-vazio">
              Nenhum imóvel vinculado.
            </p>
          )}

          <ul className="space-y-2">
            {items.map((item) => {
              const valor = valorDe(item);
              return (
                <li
                  key={item.id}
                  className="flex items-center gap-3 rounded-md border p-2"
                  data-testid={`atendimento-imovel-${item.codigo}`}
                >
                  {item.imovel.foto_destaque ? (
                    <img
                      src={item.imovel.foto_destaque}
                      alt={`Foto do imóvel ${item.codigo}`}
                      className="h-14 w-20 shrink-0 rounded object-cover"
                    />
                  ) : (
                    <div className="flex h-14 w-20 shrink-0 items-center justify-center rounded bg-muted text-[10px] text-muted-foreground">
                      Sem foto
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-semibold">{item.codigo}</span>
                      {item.principal && (
                        <span
                          className="rounded bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground"
                          data-testid={`atendimento-imovel-principal-${item.codigo}`}
                        >
                          Principal
                        </span>
                      )}
                      {item.em_negociacao && (
                        <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">
                          Em negociação
                        </span>
                      )}
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {ORIGEM_LABEL[item.origem] ?? item.origem}
                      </span>
                    </div>
                    <p className="truncate text-xs text-muted-foreground">{enderecoDe(item)}</p>
                    {valor && <p className="text-xs font-medium">{valor}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {!item.principal && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={ocupado}
                        title="Definir como principal"
                        onClick={() =>
                          definirPrincipal.mutate(
                            { id: item.id },
                            {
                              onError: (err) =>
                                toast.error(
                                  mensagemDoErro(err, "Não foi possível definir o imóvel principal."),
                                ),
                            },
                          )
                        }
                        data-testid={`atendimento-imovel-definir-principal-${item.codigo}`}
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={ocupado}
                      title="Remover do atendimento"
                      onClick={() =>
                        remover.mutate(
                          { id: item.id },
                          {
                            onError: (err) =>
                              toast.error(mensagemDoErro(err, "Não foi possível remover o imóvel.")),
                          },
                        )
                      }
                      data-testid={`atendimento-imovel-remover-${item.codigo}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="flex items-end gap-2" data-testid="atendimento-imoveis-adicionar">
            <div className="min-w-0 flex-1">
              <ImovelCodigoPicker
                id="atendimento-imovel-picker"
                value={codigo}
                onChange={setCodigo}
                disabled={adicionar.isPending}
                data-testid="atendimento-imovel-picker"
              />
            </div>
            <Button
              size="sm"
              disabled={!codigo || adicionar.isPending}
              onClick={handleAdicionar}
              data-testid="atendimento-imovel-adicionar-btn"
            >
              <Plus className="mr-1 h-4 w-4" />
              {adicionar.isPending ? "Vinculando…" : "Vincular"}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
