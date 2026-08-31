/**
 * The permanent document checklist — the identity fields every lead owes us
 * once they become a client.
 *
 * Lifted OUT of `ClienteCardDialog.tsx` when the rows became interactive: the
 * dialog was already 1691 lines and this section grew an inline editor, an
 * upload path and a file-discard path. It was already imported from two
 * places (the card and `PessoaDocumentosPanel`), so the import that used to
 * reach into the dialog now reaches a file that is only this.
 *
 * There is no add/remove: the list is the SAME for every client by
 * definition, so it is defined server-side once
 * (`documento_checklist_service.ITENS`).
 *
 * Ticks are DERIVED (migration 068): an item is done when the client record
 * carries the field or the document has been uploaded. Nothing here posts a
 * tick when data arrives — the next read simply reflects it, which is what
 * makes every ingestion channel (Meta, OLX, ImovelWeb, Vista, import, manual)
 * covered without any of them knowing this list exists.
 *
 * So a checkbox here is an OVERRIDE control, not the state itself. Clicking it
 * asserts a human opinion; the ↩ button beside an overridden item withdraws
 * that opinion and hands the item back to the data. Without that affordance
 * the first click on an item would pin it forever. Both live on the row now
 * (`ChecklistItemRow`), unchanged in meaning.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 *
 * 🔴 LOADING NEVER UNMOUNTS ROWS THAT EXIST.
 * -------------------------------------------
 * The 8 rows here used to vanish behind a single skeleton bar on EVERY save —
 * not just the first load, but every background refetch a mutation elsewhere
 * on the card triggered (a checklist tick, a dados-pessoais save). The caller
 * gated `loading` on `isPending || isFetching`, which is correct for never
 * showing the EMPTY state over live data, but this component then treated
 * that single boolean as "hide everything" — so the moment `isFetching`
 * flipped true mid-refetch, the whole section unmounted and the card jumped.
 *
 * The fix is two-part, and both halves matter:
 *   - `loading` here means "genuinely nothing to render yet" — the caller
 *     still computes it off `isPending` (v5's `isPending` is `data ===
 *     undefined`, which `isLoading` is NOT during a background refetch), but
 *     this component ALSO refuses to skeleton when `items` is non-empty, so a
 *     stale `true` from upstream can never blank real rows.
 *   - `refreshing` is a SEPARATE, non-reserving signal (a small spinner
 *     beside the progress count) for "a fetch is in flight and we already
 *     have data" — visible, but it never changes this section's height or
 *     removes a row.
 */
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type {
  DocumentoChecklistItem,
  ExtracaoSugestao,
} from "@/types/cardHub";

import { ChecklistItemRow } from "./ChecklistItemRow";
import type { DadosPessoais } from "./DadosPessoaisForm";
import { formatarDataISO } from "./format";

export interface DocumentoChecklistSectionProps {
  items: DocumentoChecklistItem[];
  /** No `items` yet — the FIRST load only. Ignored once `items` is non-empty
   *  (see the file docblock); a stale `true` here can never blank real rows. */
  loading?: boolean;
  /** A fetch is in flight AND `items` already has data — shows a small,
   *  non-reserving spinner beside the progress count. Never unmounts rows. */
  refreshing?: boolean;
  onToggle: (key: string, concluido: boolean | null) => void;
  onResolverSugestao?: (
    documentoId: string,
    acao: "confirmar" | "descartar",
    itemKey: string,
  ) => void;
  sugestaoSaving?: boolean;
  sugestoesExtras?: Record<string, ExtracaoSugestao>;
  nomeOficial?: string | null;
  nomeRegistro?: string | null;

  /** Current values behind the TEXT items, so a row can show and edit one. */
  valores?: DadosPessoais;
  /** Saves ONE field — the row sends only what was edited. */
  onSaveCampo?: (patch: DadosPessoais) => void;
  savingCampo?: boolean;
  /** Uploads the file that satisfies a DOCUMENT item (`rg` / `cpf`). */
  onUploadDocumento?: (item: DocumentoChecklistItem, file: File) => void;
  /** Discards that file. The row stays — the list is server-defined. */
  onRemoverDocumento?: (documentoId: string, item: DocumentoChecklistItem) => void;
  uploading?: boolean;
  /** Disambiguates testids when several people's checklists are on screen. */
  testIdPrefix?: string;
}

export function DocumentoChecklistSection({
  items,
  loading,
  refreshing,
  onToggle,
  onResolverSugestao,
  sugestaoSaving,
  sugestoesExtras,
  nomeOficial,
  nomeRegistro,
  valores,
  onSaveCampo,
  savingCampo,
  onUploadDocumento,
  onRemoverDocumento,
  uploading,
  testIdPrefix = "documento-checklist",
}: DocumentoChecklistSectionProps) {
  // `items.length === 0` is the second half of the guard: even a caller that
  // still sends `loading=true` mid-refetch cannot blank rows that are
  // actually here — see the file docblock.
  if (loading && items.length === 0) {
    return (
      <div className="mb-5" data-testid={`${testIdPrefix}-loading`}>
        <div className="h-4 w-48 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const done = items.filter((i) => i.concluido).length;
  const pct = items.length ? Math.round((done / items.length) * 100) : 0;

  return (
    <div className="mb-5" data-testid={`${testIdPrefix}-section`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Dados obrigatórios
        </p>
        <div className="flex items-center gap-1.5">
          {refreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid={`${testIdPrefix}-refreshing`}
            />
          )}
          <span className="text-xs text-muted-foreground" data-testid={`${testIdPrefix}-progresso`}>
            {done}/{items.length}
          </span>
        </div>
      </div>
      <Progress value={pct} className="mb-2 h-1.5" />
      {items.length === 0 ? (
        <p
          className="text-sm italic text-muted-foreground"
          data-testid={`${testIdPrefix}-empty`}
        >
          Nenhum dado obrigatório definido.
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((item) => (
            <ChecklistItemRow
              key={item.key}
              item={item}
              valor={valorDoItem(valores, item.key)}
              onToggle={onToggle}
              onSaveCampo={onSaveCampo}
              savingCampo={savingCampo}
              onUploadDocumento={onUploadDocumento}
              onRemoverDocumento={onRemoverDocumento}
              uploading={uploading}
              testIdPrefix={testIdPrefix}
            />
          ))}
          {/* Suggestions render BELOW the rows rather than inside them: a
              machine-read value is a question, and a question folded into the
              row it is about reads as an answer already applied. */}
          {items.map((item) =>
            item.sugestao && onResolverSugestao ? (
              <li key={`${item.key}-sugestao`}>
                <SugestaoExtraida
                  itemKey={item.key}
                  label={item.label}
                  sugestao={item.sugestao}
                  onResolver={onResolverSugestao}
                  saving={sugestaoSaving}
                  formatarValor={formatarDataISO}
                  testIdPrefix={testIdPrefix}
                />
              </li>
            ) : null,
          )}
        </ul>
      )}
      <NomeOficial
        oficial={nomeOficial}
        registro={nomeRegistro}
        sugestao={sugestoesExtras?.nome_oficial}
        onResolver={onResolverSugestao}
        saving={sugestaoSaving}
        testIdPrefix={testIdPrefix}
      />
    </div>
  );
}

/**
 * The record's value behind a checklist key, when there is one.
 *
 * The map is keyed by COLUMN and the checklist by ITEM KEY, and they coincide
 * for every typed item today. A key with no column (`rg`, `cpf`) returns
 * `undefined` rather than reaching for a field that does not exist.
 */
function valorDoItem(
  valores: DadosPessoais | undefined,
  key: string,
): string | null | undefined {
  if (!valores) return undefined;
  return (valores as Record<string, string | null | undefined>)[key];
}

/**
 * The name on the document, shown BESIDE the name from the registration.
 *
 * 🔴 The two are never merged, and this component is where that decision
 * becomes visible. The registration name is what the business knows the
 * person as; the document name is the legal one. Holding both is what makes
 * "how accurate is our registration data?" answerable — reconciling them
 * would answer it once, destructively, per row.
 *
 * So a divergence is rendered as INFORMATION, not as an error with a fix
 * button. There is nothing to correct here: both values are true.
 */
function NomeOficial({
  oficial,
  registro,
  sugestao,
  onResolver,
  saving,
  testIdPrefix,
}: {
  oficial?: string | null;
  registro?: string | null;
  sugestao?: ExtracaoSugestao;
  onResolver?: (
    documentoId: string,
    acao: "confirmar" | "descartar",
    itemKey: string,
  ) => void;
  saving?: boolean;
  testIdPrefix: string;
}) {
  if (!oficial && !sugestao) return null;

  const normalizar = (v: string) =>
    v
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toUpperCase()
      .replace(/[^A-Z ]/g, " ")
      .replace(/ +/g, " ")
      .trim();
  const diverge =
    !!oficial && !!registro && normalizar(oficial) !== normalizar(registro);

  return (
    <div className="mt-3" data-testid="nome-oficial-bloco">
      {oficial && (
        <div className="rounded-md border border-border/60 bg-muted/30 p-2.5 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Nome no documento
          </p>
          <p className="mt-0.5 font-medium" data-testid="nome-oficial-valor">
            {oficial}
          </p>
          {diverge && (
            <p
              className="mt-1 text-xs text-muted-foreground"
              data-testid="nome-oficial-divergencia"
            >
              Cadastro: “{registro}” — diferente do documento.
            </p>
          )}
        </div>
      )}
      {sugestao && onResolver && (
        <SugestaoExtraida
          itemKey="nome_oficial"
          label="Nome no documento"
          sugestao={sugestao}
          onResolver={onResolver}
          saving={saving}
          testIdPrefix={testIdPrefix}
        />
      )}
    </div>
  );
}

/**
 * One machine-read value, offered for a human decision.
 *
 * 🔴 Deliberately NOT styled as a filled-in field with an undo, and 🔴 the ONE
 * pair of buttons on this card that KEPT their words. A birthdate on a
 * photographed RG can be misread between two plausible years (1980→1930) in a
 * way no plausibility check catches, so the value must read as a QUESTION
 * until a person answers it. "Confirmar" and "Descartar" as two bare icons
 * would be exactly the reflex-confirm this path exists to prevent: the whole
 * point is to make the operator stop and read.
 *
 * The document name and the source are shown because they are what the
 * operator actually checks against — "we read this off rg.pdf, by OCR" tells
 * them where to look and how much to doubt it.
 *
 * Takes the label and a formatter rather than a `DocumentoChecklistItem`,
 * because it serves two callers whose values are not the same shape: a
 * birthdate (`YYYY-MM-DD`, needs reformatting) and the official name (already
 * display-ready). Threading a checklist item through it would have forced
 * `nome_oficial` to pretend to be a checklist item, which is exactly the
 * conflation the backend keeps apart.
 */
function SugestaoExtraida({
  itemKey,
  label,
  sugestao,
  onResolver,
  saving,
  formatarValor = (v: string) => v,
  testIdPrefix,
}: {
  itemKey: string;
  label: string;
  sugestao: ExtracaoSugestao | null | undefined;
  onResolver: (
    documentoId: string,
    acao: "confirmar" | "descartar",
    itemKey: string,
  ) => void;
  saving?: boolean;
  formatarValor?: (valor: string) => string;
  testIdPrefix: string;
}) {
  const s = sugestao;
  if (!s) return null;

  // OCR is the approximate rung; a PDF text layer is exact. Saying which one
  // produced the value is the difference between "check this" and "glance".
  const fonteLabel = s.fonte === "ocr" ? "leitura de imagem (OCR)" : "texto do PDF";
  const tid = `${testIdPrefix}-${itemKey}-sugestao`;

  return (
    <div
      className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5 text-sm"
      data-testid={tid}
    >
      <p className="text-xs text-muted-foreground">
        Encontramos em{" "}
        <span className="font-medium text-foreground">
          {s.documento_nome ?? "um documento"}
        </span>
        , por {fonteLabel} — confirme antes de salvar:
      </p>
      <p className="my-1 font-medium" data-testid={`${tid}-valor`}>
        {label}: {formatarValor(s.valor)}
      </p>
      {s.substitui && s.valor_atual && (
        /* Accepting this replaces something rather than filling a blank. Say
           what it replaces, on the same screen as the decision — otherwise the
           operator finds out afterwards, by noticing a value they did not
           expect. */
        <p className="text-xs text-muted-foreground">
          Substitui o valor atual: “{s.valor_atual}”
        </p>
      )}
      {s.rotulo && (
        <p className="text-xs text-muted-foreground">Campo lido: “{s.rotulo}”</p>
      )}
      <div className="mt-2 flex gap-2">
        <Button
          size="sm"
          variant="default"
          disabled={saving}
          onClick={() => onResolver(s.documento_id, "confirmar", itemKey)}
          data-testid={`${tid}-confirmar`}
        >
          Confirmar
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={saving}
          onClick={() => onResolver(s.documento_id, "descartar", itemKey)}
          data-testid={`${tid}-descartar`}
        >
          Descartar
        </Button>
      </div>
    </div>
  );
}
