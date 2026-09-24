/**
 * `<CertidoesMatrizSection/>` — the "Certidões" card tab (Levantamento de
 * Certidões.xlsx, first tab): every certidão TYPE (rows) crossed with every
 * vendedor party + their PJ-requiring empresas (columns), colored by status,
 * with per-column totals and a legend.
 *
 * A CONTAINER, same shape as `EmpresasSection`/`NegociacaoContainer`:
 * self-fetching via `useCertidoesMatriz` (keyed by `clienteId`), rendered
 * through `ClienteCardDialog`'s `renderCertidoes` thunk so a card nobody
 * opens this tab on never fires the request. The grid itself is READ-ONLY —
 * clicking a cell opens that COLUMN's existing certidões flow
 * (`CertidoesPartePanel`, reused as-is, never forked) in a dialog; the
 * emission workflow itself still lives on `pages/Certidoes.tsx` /
 * `CertidoesPartePanel`'s own hooks (`useCreateConsulta` et al.) — this tab
 * is a new READING surface over the same data, not a second writer.
 */
import { useState } from "react";
import { FileText } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { CertidoesPartePanel } from "@/components/CertidoesPartePanel";
import { useCertidoesMatriz } from "@/hooks/useCertidoesMatriz";
import { formatDate } from "@/lib/utils";
import type {
  CertidaoMatrizCelula,
  CertidaoMatrizCelulaStatus,
  CertidaoMatrizColuna,
} from "@/types/certidoesMatriz";

/** Color + accessible label per cell status — text travels WITH the color,
 *  never color alone (colorblind users, print, screen readers). */
const STATUS_ESTILO: Record<CertidaoMatrizCelulaStatus, string> = {
  nao_constam: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  constam: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  pendente: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  na: "bg-muted text-muted-foreground",
};

const TOTAL_ROTULO: Record<"nao_constam" | "constam" | "pendente", string> = {
  nao_constam: "Não constam",
  constam: "Constam",
  pendente: "Pendente",
};

export interface CertidoesMatrizSectionProps {
  clienteId: string;
}

export function CertidoesMatrizSection({ clienteId }: CertidoesMatrizSectionProps) {
  const matriz = useCertidoesMatriz(clienteId);
  const [colunaAberta, setColunaAberta] = useState<CertidaoMatrizColuna | null>(null);

  // Two signals off `data`, never `isLoading` — a background refetch must
  // never unmount rows that already exist.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = matriz.isPending && !matriz.data;
  const isRefreshing = matriz.isFetching && !!matriz.data;
  const data = matriz.data;

  if (showSkeleton) {
    return (
      <div className="space-y-2" data-testid="certidoes-matriz-skeleton">
        <div className="h-10 animate-pulse rounded bg-muted" />
        <div className="h-40 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  if (!data || data.colunas.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="certidoes-matriz-empty">
        Nenhum vendedor ou empresa vinculada a este atendimento ainda.
      </p>
    );
  }

  const { linhas, colunas, celulas, totais } = data;

  return (
    <div className="space-y-4" data-testid="certidoes-matriz">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Levantamento de certidões</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Data do levantamento: {formatDate(data.data_levantamento)}
          </p>
        </div>
        {isRefreshing && (
          <p className="text-xs text-muted-foreground" data-testid="certidoes-matriz-refreshing">
            Atualizando…
          </p>
        )}
      </div>

      <TooltipProvider delayDuration={200}>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-max border-collapse text-xs">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="sticky left-0 z-10 min-w-[220px] border-r bg-muted/50 p-2 text-left font-semibold">
                  Certidão
                </th>
                {colunas.map((coluna) => (
                  <th key={`${coluna.kind}-${coluna.id}`} className="min-w-[140px] p-2 text-left font-semibold">
                    <div>{coluna.rotulo}</div>
                    <div className="font-normal text-muted-foreground">{coluna.nome}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {linhas.map((linha) => (
                <tr key={linha.tipo} className="border-b last:border-b-0">
                  <td className="sticky left-0 z-10 border-r bg-background p-2 font-medium">
                    <span className="text-muted-foreground">{linha.linha}</span>{" "}
                    {linha.rotulo}
                  </td>
                  {colunas.map((coluna) => {
                    const celula: CertidaoMatrizCelula | undefined =
                      celulas[linha.tipo]?.[coluna.id];
                    if (!celula) return <td key={coluna.id} className="p-2" />;
                    const clicavel = celula.status !== "na";
                    return (
                      <td key={coluna.id} className="p-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              disabled={!clicavel}
                              onClick={() => clicavel && setColunaAberta(coluna)}
                              data-testid={`certidoes-matriz-celula-${linha.tipo}-${coluna.id}`}
                              className={`w-full rounded px-2 py-1.5 text-left font-medium transition-colors ${STATUS_ESTILO[celula.status]} ${
                                clicavel ? "cursor-pointer hover:opacity-80" : "cursor-default"
                              }`}
                            >
                              {celula.texto}
                            </button>
                          </TooltipTrigger>
                          {(celula.numero ||
                            celula.emitida_em ||
                            celula.validade_ate ||
                            celula.analise_ia ||
                            celula.erro_mensagem) && (
                            <TooltipContent className="max-w-xs space-y-1 text-xs">
                              {celula.numero && <p>Número: {celula.numero}</p>}
                              {celula.emitida_em && <p>Emitida em: {formatDate(celula.emitida_em)}</p>}
                              {celula.validade_ate && <p>Válida até: {formatDate(celula.validade_ate)}</p>}
                              {celula.analise_ia && <p>{celula.analise_ia}</p>}
                              {celula.erro_mensagem && (
                                <p className="text-red-300">{celula.erro_mensagem}</p>
                              )}
                            </TooltipContent>
                          )}
                        </Tooltip>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t bg-muted/30">
                <td colSpan={colunas.length + 1} className="p-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Totais
                </td>
              </tr>
              {(["nao_constam", "constam", "pendente"] as const).map((chave) => (
                <tr key={chave} className="border-t">
                  <td className="sticky left-0 z-10 border-r bg-background p-2 font-medium">
                    {TOTAL_ROTULO[chave]}
                  </td>
                  {colunas.map((coluna) => (
                    <td key={coluna.id} className="p-2 text-center font-semibold">
                      {totais[coluna.id]?.[chave] ?? 0}
                    </td>
                  ))}
                </tr>
              ))}
            </tfoot>
          </table>
        </div>
      </TooltipProvider>

      <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
        <p className="mb-1 font-semibold uppercase tracking-wide">Legenda</p>
        <p>
          <span className={`mr-1 rounded px-1.5 py-0.5 ${STATUS_ESTILO.nao_constam}`}>Não constam</span>
          = certidão negativa / nada consta.{" "}
          <span className={`mr-1 rounded px-1.5 py-0.5 ${STATUS_ESTILO.constam}`}>Constam</span>
          = há apontamento (processo, débito, protesto, restrição ou certidão não emitida por irregularidade).
        </p>
        <p className="mt-1">
          <span className={`mr-1 rounded px-1.5 py-0.5 ${STATUS_ESTILO.pendente}`}>Pendente</span>
          = certidão ainda não emitida/registrada.{" "}
          <span className={`mr-1 rounded px-1.5 py-0.5 ${STATUS_ESTILO.na}`}>N/A</span>
          = não se aplica (FGTS só para empresas). VEND = vendedores (titular e cônjuge). EMP = empresas dos vendedores.
        </p>
      </div>

      <Dialog open={!!colunaAberta} onOpenChange={(open) => !open && setColunaAberta(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Certidões — {colunaAberta?.nome || colunaAberta?.rotulo}
            </DialogTitle>
            <DialogDescription>
              Registre, envie ou corrija as certidões desta{" "}
              {colunaAberta?.kind === "empresa" ? "empresa" : "pessoa"}.
            </DialogDescription>
          </DialogHeader>
          {colunaAberta &&
            (colunaAberta.kind === "empresa" ? (
              <CertidoesPartePanel
                empresaId={colunaAberta.id}
                nomeParte={colunaAberta.nome}
                documento={colunaAberta.cnpj ?? undefined}
              />
            ) : (
              <CertidoesPartePanel clienteId={colunaAberta.id} nomeParte={colunaAberta.nome} />
            ))}
        </DialogContent>
      </Dialog>
    </div>
  );
}
