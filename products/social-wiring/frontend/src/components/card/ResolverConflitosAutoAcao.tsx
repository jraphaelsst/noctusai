/**
 * `<ResolverConflitosAutoAcao/>` — the admin's "Resolver conflitos
 * automaticamente" (`POST /api/clientes/conflitos/resolver-automaticamente`,
 * owner/admin only server-side): re-runs the automatic divergence resolver
 * over EVERY pending conflict in the office (people and imóveis).
 *
 * Behind a confirmation that says exactly what it does — and what it never
 * does: it settles only the conflicts a rule can decide (a corroborating
 * document, a source the policy trusts more) and never overrides a value a
 * person typed; anything ambiguous stays pending for a human. After the run
 * the per-queue counts are shown inline.
 *
 * Presentational (S3) — the caller (`Settings › Pendências`) owns the
 * mutation (`useResolverConflitosAutomaticamente`).
 */
import { useState } from "react";
import { Loader2, Wand2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

import type { ResolverConflitosAutoContagem } from "@/hooks/useCardHub";

export interface ResolverConflitosAutoAcaoProps {
  /** UI convenience only — the server re-checks the trusted role (403). */
  isAdmin: boolean;
  onResolver: () => void;
  resolvendo: boolean;
  /** The last run's counts — `null` before any run in this session. */
  resultado: { clientes: ResolverConflitosAutoContagem; imoveis: ResolverConflitosAutoContagem } | null;
}

function linha(rotulo: string, c: ResolverConflitosAutoContagem): string {
  const partes = [
    `${c.resolvidos} resolvido${c.resolvidos === 1 ? "" : "s"}`,
    `${c.aindaPendentes} ainda pendente${c.aindaPendentes === 1 ? "" : "s"}`,
  ];
  if (c.ignorados > 0) partes.push(`${c.ignorados} para decisão manual (campo composto)`);
  return `${rotulo}: ${partes.join(", ")}.`;
}

export function ResolverConflitosAutoAcao({
  isAdmin,
  onResolver,
  resolvendo,
  resultado,
}: ResolverConflitosAutoAcaoProps) {
  const [confirmar, setConfirmar] = useState(false);
  if (!isAdmin) return null;
  return (
    <div className="space-y-2" data-testid="resolver-conflitos-auto">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={resolvendo}
        onClick={() => setConfirmar(true)}
        data-testid="resolver-conflitos-auto-btn"
      >
        {resolvendo ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Wand2 className="mr-1.5 h-3.5 w-3.5" />
        )}
        Resolver conflitos automaticamente
      </Button>
      {resultado && (
        <div
          className="rounded-md border bg-muted/30 p-2.5 text-xs"
          data-testid="resolver-conflitos-auto-resultado"
        >
          <p>{linha("Pessoas", resultado.clientes)}</p>
          <p>{linha("Imóveis", resultado.imoveis)}</p>
        </div>
      )}
      <AlertDialog open={confirmar} onOpenChange={setConfirmar}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Resolver conflitos automaticamente?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>
                  As regras de resolução são aplicadas a todas as pendências de dados do escritório
                  (pessoas e imóveis).
                </p>
                <p>
                  Só são resolvidos os conflitos que uma regra consegue decidir — por exemplo, quando
                  outro documento confirma o valor. Um valor digitado por uma pessoa nunca é
                  substituído, e o que continuar ambíguo fica pendente para decisão manual.
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Voltar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirmar(false);
                onResolver();
              }}
              data-testid="resolver-conflitos-auto-confirmar"
            >
              Resolver
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default ResolverConflitosAutoAcao;
