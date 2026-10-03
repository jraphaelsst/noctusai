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
 *
 * TWO CONFLICT TABLES, ONE CARD (2026-10-03). `imovel_campo_conflitos`
 * (migration 154) has the same decide shape as `cliente_campo_conflitos`, so
 * `ImovelConflitosCard` mounts THIS card rather than a copy: the props that
 * differ per table are seams — `rotuloCampo` / `formatarValor` (the imóvel
 * fields and their JSONB group values), `renderDetalhe` (the source document
 * and, in the org queue, the imóvel link), `itemTestId` and `titulo`. The
 * cliente call sites pass none of them and render exactly as before.
 */
import type { ReactNode } from "react";
import { Check, Clock3, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { formatIdentificador } from "@noctusai/lib/identificador";

import type { ConflitoCampo } from "@/hooks/useCardHub";

/** Free-text `campo` -> a label an operator recognizes — mirrors
 *  `DadosPessoaisForm`'s own field labels so the same fact reads the same
 *  way in both places. */
const CAMPO_ROTULOS: Record<string, string> = {
  nome_oficial: "Nome completo (como no documento)",
  cpf: "CPF",
  rg: "RG",
  rg_orgao_expedidor: "Órgão expedidor do RG",
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

/** `campo` -> the identifier type the value is a number of. A conflicting
 *  CPF / RG renders in its canonical PUNCTUATED form (the ONE seam — owner
 *  rule 2026-10-01), so a human compares `30128742` against `30.128.742-9`
 *  as the two spellings of one RG they are, not as two strangers; a value that
 *  does not fit its type is shown as stored. */
const CAMPO_TIPO_IDENTIFICADOR: Record<string, string> = {
  cpf: "cpf",
  rg: "rg",
  rg_orgao_expedidor: "orgao_expedidor",
};

function valorDoConflito(campo: string, valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const tipo = CAMPO_TIPO_IDENTIFICADOR[campo];
  return tipo ? formatIdentificador(tipo, valor) : valor;
}

/** The fields both conflict tables share — all the card itself reads.
 *  `valor_*` are `unknown` because `imovel_campo_conflitos` stores JSONB
 *  (a pointer GROUP is an object); the cliente table's are strings. */
export interface ConflitoPendenteBase {
  id: string;
  campo: string;
  status: string;
  valor_anterior: unknown;
  valor_proposto: unknown;
  origem_proposto: string;
  /** cliente table only — read when `mostrarCliente` is set. */
  cliente_id?: string;
}

/** Default value rendering: identifiers punctuated (the cliente fields),
 *  any other non-string (an imóvel JSONB group) as compact JSON — never a
 *  blank and never `[object Object]`. */
function valorPadrao(campo: string, valor: unknown): string {
  if (valor == null || valor === "") return "—";
  if (typeof valor === "string") return valorDoConflito(campo, valor);
  if (typeof valor === "number" || typeof valor === "boolean") return String(valor);
  return JSON.stringify(valor);
}

export interface ConflitosPendentesCardProps<T extends ConflitoPendenteBase = ConflitoCampo> {
  conflitos: T[];
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
  /** Field label seam — defaults to the cliente field labels. */
  rotuloCampo?: (campo: string) => string;
  /** Value rendering seam — defaults to `valorPadrao`. */
  formatarValor?: (campo: string, valor: unknown) => string;
  /** Extra per-row content under the values (source document, a link to
   *  the record the row is about). */
  renderDetalhe?: (conflito: T) => ReactNode;
  /** Per-row test id; defaults to `${testId}-item-${id}`. The buttons are
   *  `<itemTestId>-aprovar` / `-rejeitar`. */
  itemTestId?: (conflitoId: string) => string;
  titulo?: string;
  testId?: string;
}

export function ConflitosPendentesCard<T extends ConflitoPendenteBase = ConflitoCampo>({
  conflitos,
  onDecidir,
  decidingId,
  isAdmin,
  mostrarCliente = false,
  nomeDoCliente,
  rotuloCampo: rotular = rotuloCampo,
  formatarValor = valorPadrao,
  renderDetalhe,
  itemTestId,
  titulo = "Pendências de confirmação",
  testId = "conflitos-pendentes",
}: ConflitosPendentesCardProps<T>) {
  const pendentes = conflitos.filter((c) => c.status === "pendente");
  if (pendentes.length === 0) return null;
  const idDoItem = itemTestId ?? ((id: string) => `${testId}-item-${id}`);

  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Clock3 className="h-4 w-4 text-amber-600" />
          <CardTitle className="text-sm">
            {titulo} ({pendentes.length})
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {pendentes.map((c) => {
          const deciding = decidingId === c.id;
          const itemId = idDoItem(c.id);
          return (
            <div
              key={c.id}
              className="rounded-md border p-3 text-sm"
              data-testid={itemId}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="font-medium">{rotular(c.campo)}</span>
                <Badge variant="outline" className="text-[11px]">
                  {c.origem_proposto === "manual" ? "edição manual" : "extração"}
                </Badge>
              </div>
              {mostrarCliente && c.cliente_id && (
                <p className="mb-1 text-xs text-muted-foreground">
                  {nomeDoCliente?.(c.cliente_id) ?? c.cliente_id}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Documento/atual: <span className="font-mono">{formatarValor(c.campo, c.valor_anterior)}</span>
                {" → "}
                proposto: <span className="font-mono">{formatarValor(c.campo, c.valor_proposto)}</span>
              </p>
              {renderDetalhe?.(c)}
              {isAdmin && (
                <div className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    variant="default"
                    disabled={deciding}
                    onClick={() => onDecidir(c.id, true)}
                    data-testid={`${itemId}-aprovar`}
                  >
                    <Check className="mr-1 h-3.5 w-3.5" />
                    Aprovar
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={deciding}
                    onClick={() => onDecidir(c.id, false)}
                    data-testid={`${itemId}-rejeitar`}
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
