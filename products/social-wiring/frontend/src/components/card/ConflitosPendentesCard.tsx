/**
 * `<ConflitosPendentesCard/>` — the admin decide surface for
 * `cliente_campo_conflitos` (migration 138 + its reverse direction, owner
 * directive 2026-09-19): "humans input data, extracted from official files
 * are the truth. if a robot input a data, then a human edits an
 * extracted-data, human overwrites with admin confirmation and logs for
 * history and rollback."
 *
 * Presentational (S3): `onDecidir` is the only callback out, `conflitos` /
 * `isAdmin` / `decidingId` are the only inputs. Three call sites share it —
 * `ClienteDetailModal` (the titular, via `ClienteCardDialog`'s
 * `renderConflitosPendentes` thunk), `PessoaDocumentosPanel` (each
 * comprador/vendedor, keyed by their own `cliente_id`), and `Settings.tsx`'s
 * "Pendências de dados" tab (`mostrarCliente`, the org-wide queue with no
 * single person already in view) — mirroring `DadosPessoaisForm`'s own
 * reuse pattern rather than three copies of the same list+buttons.
 *
 * NON-ADMINS SEE THE LIST, NOT THE BUTTONS. Read is open — a corretor
 * should be able to see a data correction is awaiting review, the same
 * "read open, write admin-gated" split `DocumentoRetencaoTab` /
 * `ClientesInactivityTab` already use — only Aprovar/Rejeitar require
 * `isAdmin` (the server's OWN `decidir_conflito_route` enforces this for
 * real; `isAdmin` here is a UI convenience, same posture `Equipe.tsx`'s
 * button-visibility already takes — a spoofed client would still 403).
 */
import { Check, Clock3, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { ConflitoCampo } from "@/hooks/useCardHub";

/** Free-text `campo` -> a label an operator recognizes — mirrors
 *  `DadosPessoaisForm`'s own field labels so the same fact reads the same
 *  way in both places. */
const CAMPO_ROTULOS: Record<string, string> = {
  nome_oficial: "Nome completo (como no documento)",
  cpf: "CPF",
  rg: "RG",
  data_nascimento: "Data de nascimento",
  genero: "Gênero",
  estado_civil: "Estado civil",
  regime_bens: "Regime de bens",
  data_casamento: "Data de casamento",
  nacionalidade: "Nacionalidade",
};

function rotuloCampo(campo: string): string {
  return CAMPO_ROTULOS[campo] ?? campo;
}

export interface ConflitosPendentesCardProps {
  conflitos: ConflitoCampo[];
  onDecidir: (conflitoId: string, aceitar: boolean) => void;
  /** The `conflitoId` currently in flight — disables both its buttons so a
   *  double-click can't fire two decisions for the same row. */
  decidingId?: string | null;
  isAdmin: boolean;
  /** The org-wide queue (`Settings.tsx`) has no single person already in
   *  view — each row names WHO it is about. A per-card mount already knows
   *  (it's scoped to one `cliente_id`), so this defaults to hidden there. */
  mostrarCliente?: boolean;
  /** Resolves `cliente_id` -> a display name, only consulted when
   *  `mostrarCliente` is true. Falls back to the raw id when absent —
   *  never a blank row. */
  nomeDoCliente?: (clienteId: string) => string | undefined;
  testId?: string;
}

export function ConflitosPendentesCard({
  conflitos,
  onDecidir,
  decidingId,
  isAdmin,
  mostrarCliente = false,
  nomeDoCliente,
  testId = "conflitos-pendentes",
}: ConflitosPendentesCardProps) {
  const pendentes = conflitos.filter((c) => c.status === "pendente");
  if (pendentes.length === 0) return null;

  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Clock3 className="h-4 w-4 text-amber-600" />
          <CardTitle className="text-sm">
            Pendências de confirmação ({pendentes.length})
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {pendentes.map((c) => {
          const deciding = decidingId === c.id;
          return (
            <div
              key={c.id}
              className="rounded-md border p-3 text-sm"
              data-testid={`${testId}-item-${c.id}`}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="font-medium">{rotuloCampo(c.campo)}</span>
                <Badge variant="outline" className="text-[11px]">
                  {c.origem_proposto === "manual" ? "edição manual" : "extração"}
                </Badge>
              </div>
              {mostrarCliente && (
                <p className="mb-1 text-xs text-muted-foreground">
                  {nomeDoCliente?.(c.cliente_id) ?? c.cliente_id}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Documento/atual: <span className="font-mono">{c.valor_anterior ?? "—"}</span>
                {" → "}
                proposto: <span className="font-mono">{c.valor_proposto}</span>
              </p>
              {isAdmin && (
                <div className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    variant="default"
                    disabled={deciding}
                    onClick={() => onDecidir(c.id, true)}
                    data-testid={`${testId}-item-${c.id}-aprovar`}
                  >
                    <Check className="mr-1 h-3.5 w-3.5" />
                    Aprovar
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={deciding}
                    onClick={() => onDecidir(c.id, false)}
                    data-testid={`${testId}-item-${c.id}-rejeitar`}
                  >
                    <X className="mr-1 h-3.5 w-3.5" />
                    Rejeitar
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
