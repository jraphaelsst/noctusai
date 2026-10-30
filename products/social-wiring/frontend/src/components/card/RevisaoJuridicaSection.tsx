/**
 * RevisaoJuridicaSection — one final legal review per generated version
 * (owner decision 2026-09-30, backend migration 177) — of a contract AND of
 * an aditivo (contrato-aditivos-CONTRACT §3, same review shape).
 *
 * Owner, verbatim: asked "replace the per-field confirmations with one final
 * review of the finished contract by the legal team?" → "yes". EVERY version
 * the system generated is "Aguardando revisão jurídica" until approved — the
 * review is of the finished instrument, not only of the values it relied on
 * (backend `contratos_service.revisao_juridica_status` keys on the version's
 * ORIGEM, so a version with ZERO machine-extracted values still waits; only
 * an upload / signed copy is `nao_exigida`). `revisao_juridica.campos` is
 * what the reviewer looks at FIRST, never the condition for a review:
 *   - a machine-extracted value — ONE row per fact, grouped by person, the
 *     VALUE first (owner 2026-10-13: a 43-row list of field names with no
 *     values was "trash"; CPF/RG masked until "Revelar"), then "fonte: <tipo>
 *     · <arquivo>", then why it is listed + the MEASURED precision of that
 *     source (never a document's own "confiança"). Copied/inferred values
 *     ("Derivados (conferir)") and values ≥2 documents agree on ("Confirmado
 *     por documentos") are collapsed and never counted as extracted;
 *   - an aditivo's own wording (`origem: "gerado"`) and each free clause the
 *     team wrote (`origem: "manual"`).
 * The copy therefore never says "usa 0 dados extraídos": it counts the
 * extracted values only when there are some, and otherwise asks for the
 * whole-document read.
 *
 * The server is the gate — signature and "Baixar para impressão" are refused
 * (409) until it is approved; the button is only a UI convenience for admins
 * (the POST 403s anyone else, reading the TRUSTED `noctus_users` row).
 *
 * States: `nao_exigida` renders nothing; `aguardando` the amber block + the
 * button (or, for a non-admin, who can approve); `aprovada` a green line with
 * who/when. The review state comes off the version already on screen — no
 * query of its own, so no skeleton to lie with.
 *
 * Presentational (S3) — `ContratosContainer` / `AditivosContainer` own the
 * mutation.
 */
import { useState } from "react";
import { CheckCircle2, FileSearch, Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CampoRevisaoJuridica, VersaoOut } from "@/hooks/useContratos";
import { revisaoJuridicaStatus } from "@/hooks/useContratos";
import { ORIGEM_ROTULO } from "@/hooks/useValidacaoExtracao";

import { ItensRevisaoLista } from "./ItensRevisaoLista";

/** `origem` values that are NOT a machine reading of a document — an
 *  aditivo's generated wording and a clause the team wrote by hand. */
const ORIGEM_NAO_EXTRAIDA: Record<string, string> = {
  gerado: "texto gerado pelo sistema",
  manual: "redigido pela equipe",
};

/** A campo read off a document by a machine that nobody vouched for —
 *  anything but the two wording origins above (including a missing `origem`,
 *  which the pre-aditivo rows never had), and neither a `derivado` (copied /
 *  inferred) nor a `corroborado` (≥2 documents agree) value. */
export function campoExtraido(campo: CampoRevisaoJuridica): boolean {
  if (campo.origem && campo.origem in ORIGEM_NAO_EXTRAIDA) return false;
  return !campo.secao || campo.secao === "extraido";
}

/** The rows of `campos` in their (server-given) order, grouped by `grupo` —
 *  person/entity first, identity → civil status → address → contact inside. */
function porGrupo(campos: CampoRevisaoJuridica[]): [string, CampoRevisaoJuridica[]][] {
  const grupos = new Map<string, CampoRevisaoJuridica[]>();
  for (const c of campos) {
    const g = c.grupo ?? "";
    grupos.set(g, [...(grupos.get(g) ?? []), c]);
  }
  return [...grupos.entries()];
}

interface LinhaCampoProps {
  campo: CampoRevisaoJuridica;
  testIdPrefix: string;
  revelado: boolean;
  onAlternarRevelar: (chave: string) => void;
}

/** One fact: the VALUE first (masked until "Revelar" for an identity
 *  number — the favorecidos pattern), then the field, then
 *  "fonte: <tipo> · <arquivo>", then why it is listed + the measured
 *  precision. A row recorded before values existed reads "confira no PDF". */
function LinhaCampo({ campo: c, testIdPrefix, revelado, onAlternarRevelar }: LinhaCampoProps) {
  const extraido = !(c.origem && c.origem in ORIGEM_NAO_EXTRAIDA);
  const mascarado = Boolean(c.valor_mascarado) && !revelado;
  const valor = mascarado ? c.valor_mascarado : c.valor;
  const fonteTipo = c.fonte_tipo ?? (c.origem ? (ORIGEM_ROTULO[c.origem] ?? c.origem) : null);
  const fonte = [fonteTipo, c.fonte_nome].filter(Boolean).join(" · ");
  const motivo = extraido
    ? (c.motivo ?? "extraído automaticamente — revisar no documento")
    : `${ORIGEM_NAO_EXTRAIDA[c.origem as string]} — revisar no documento`;
  return (
    <li
      className="space-y-0.5 rounded border border-warning/40 bg-white/70 px-2 py-1.5 text-xs"
      data-testid={`${testIdPrefix}-campo-${c.chave}`}
    >
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-[11px] text-muted-foreground">{c.rotulo}</span>
        {c.valor != null ? (
          <span
            className="break-all text-sm font-semibold text-foreground"
            data-testid={`${testIdPrefix}-valor-${c.chave}`}
          >
            {valor}
          </span>
        ) : (
          extraido && <span className="text-[11px] italic text-warning-foreground">valor: confira no PDF</span>
        )}
        {c.valor_mascarado && c.valor != null && (
          <button
            type="button"
            className="min-h-8 text-[11px] font-medium text-warning-foreground underline"
            onClick={() => onAlternarRevelar(c.chave)}
            data-testid={`${testIdPrefix}-revelar-${c.chave}`}
          >
            {revelado ? "Ocultar" : "Revelar"}
          </button>
        )}
      </div>
      {extraido && fonte && (
        <p className="text-[11px] text-muted-foreground">fonte: {fonte}</p>
      )}
      <p className="text-[11px] text-warning-foreground">
        {motivo}
        {extraido ? ` · ${c.precisao ?? "sem medição"}` : ""}
      </p>
      {c.valor_confere === false && (
        <p className="text-[11px] font-medium text-destructive" data-testid={`${testIdPrefix}-mudou-${c.chave}`}>
          O valor mudou depois que esta versão foi gerada — gere uma nova versão antes de aprovar.
        </p>
      )}
    </li>
  );
}

/** The pt-BR intro of the `aguardando` block — one sentence per case, so an
 *  all-human version never reads "usa 0 dados extraídos". */
export function textoRevisaoAguardando(
  campos: CampoRevisaoJuridica[],
  documento: "contrato" | "aditivo" = "contrato",
): string {
  const doc = documento === "aditivo" ? "o aditivo" : "o contrato";
  const base =
    "Esta versão (rascunho) foi gerada pelo sistema e precisa da revisão jurídica final " +
    "antes do envio para assinatura e da impressão.";
  const n = campos.filter(campoExtraido).length;
  if (n === 0) {
    return `${base} Nenhum dado foi extraído automaticamente de documentos — revise ${doc} por inteiro no PDF e aprove.`;
  }
  const dados = n === 1 ? "um dado extraído" : `${n} dados extraídos`;
  const valores = n === 1 ? "esse valor" : "esses valores";
  return `${base} Ela usa ${dados} automaticamente de documentos — confira ${valores} no PDF primeiro e revise ${doc} por inteiro antes de aprovar.`;
}

export interface RevisaoJuridicaSectionProps {
  /** Suffix of every test id — the contract's id, or the aditivo's. */
  contratoId: string;
  versao: VersaoOut;
  /** UI convenience only — the server re-checks the trusted role. */
  podeAprovarRevisao: boolean;
  /** Omitted ⇒ no button (the caller has not wired the action). */
  onAprovar?: (versaoId: string) => void;
  aprovando?: boolean;
  /** What the version is — drives the copy. Default `"contrato"`. */
  documento?: "contrato" | "aditivo";
  /** Test-id prefix. Default `"contrato-revisao"`. */
  testIdPrefix?: string;
}

export function RevisaoJuridicaSection({
  contratoId,
  versao,
  podeAprovarRevisao,
  onAprovar,
  aprovando = false,
  documento = "contrato",
  testIdPrefix = "contrato-revisao",
}: RevisaoJuridicaSectionProps) {
  const [confirmarAberto, setConfirmarAberto] = useState(false);
  // Per-row, explicit reveal of a masked identity number — never global.
  const [revelados, setRevelados] = useState<ReadonlySet<string>>(new Set());
  const alternarRevelar = (chave: string) =>
    setRevelados((atual) => {
      const novo = new Set(atual);
      if (novo.has(chave)) novo.delete(chave);
      else novo.add(chave);
      return novo;
    });
  const status = revisaoJuridicaStatus(versao);
  const revisao = versao.revisao_juridica;

  if (status === "nao_exigida" || !revisao) return null;

  if (status === "aprovada") {
    return (
      <p
        className="flex flex-wrap items-center gap-1.5 text-xs text-success"
        data-testid={`${testIdPrefix}-aprovada-${contratoId}`}
      >
        <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
        Revisão jurídica aprovada
        {revisao.revisado_por?.nome ? ` · por ${revisao.revisado_por.nome}` : ""}
        {revisao.revisado_em ? ` · ${new Date(revisao.revisado_em).toLocaleString("pt-BR")}` : ""}
      </p>
    );
  }

  const campos = revisao.campos;
  const extraidos = campos.filter(campoExtraido).length;
  const principais = campos.filter((c) => !c.secao || c.secao === "extraido");
  const corroborados = campos.filter((c) => c.secao === "corroborado");
  const derivados = campos.filter((c) => c.secao === "derivado");
  const linha = (c: CampoRevisaoJuridica) => (
    <LinhaCampo
      key={c.chave}
      campo={c}
      testIdPrefix={testIdPrefix}
      revelado={revelados.has(c.chave)}
      onAlternarRevelar={alternarRevelar}
    />
  );
  return (
    <div
      className="space-y-2 rounded-md border border-warning/40 bg-warning-light p-2.5"
      data-testid={`${testIdPrefix}-aguardando-${contratoId}`}
    >
      <div className="space-y-0.5">
        <p className="flex items-center gap-1.5 text-sm font-medium text-warning-foreground">
          <FileSearch className="h-4 w-4 shrink-0" />
          Aguardando revisão jurídica
        </p>
        <p className="text-xs text-warning-foreground" data-testid={`${testIdPrefix}-texto-${contratoId}`}>
          {textoRevisaoAguardando(campos, documento)}
        </p>
      </div>
      {principais.length > 0 && (
        <div className="space-y-2" data-testid={`${testIdPrefix}-campos-${contratoId}`}>
          {porGrupo(principais).map(([grupo, itens]) => (
            <section key={grupo} className="space-y-1">
              {grupo && <p className="text-[11px] font-semibold text-warning-foreground">{grupo}</p>}
              <ul className="space-y-1">{itens.map(linha)}</ul>
            </section>
          ))}
        </div>
      )}
      {corroborados.length > 0 && (
        <details
          className="rounded border border-success/40 bg-white/60 px-2 py-1 text-xs"
          data-testid={`${testIdPrefix}-corroborados-${contratoId}`}
        >
          <summary className="min-h-8 cursor-pointer text-[11px] font-medium text-success">
            Confirmado por documentos ({corroborados.length})
          </summary>
          <ul className="mt-1 space-y-1">{corroborados.map(linha)}</ul>
        </details>
      )}
      {derivados.length > 0 && (
        <details
          className="rounded border border-warning/40 bg-white/60 px-2 py-1 text-xs"
          data-testid={`${testIdPrefix}-derivados-${contratoId}`}
        >
          <summary className="min-h-8 cursor-pointer text-[11px] font-medium text-warning-foreground">
            Derivados (conferir) ({derivados.length})
          </summary>
          <ul className="mt-1 space-y-1">{derivados.map(linha)}</ul>
        </details>
      )}
      <ItensRevisaoLista
        itens={revisao.itens}
        titulo="Textos para leitura obrigatória antes de aprovar"
        testId={`${testIdPrefix}-itens-${contratoId}`}
        tom="revisao"
      />
      {onAprovar && podeAprovarRevisao ? (
        <Button
          type="button"
          size="sm"
          className="min-h-10 w-full sm:w-auto"
          disabled={aprovando}
          onClick={() => setConfirmarAberto(true)}
          data-testid={`${testIdPrefix}-aprovar-${contratoId}`}
        >
          {aprovando ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle2 className="mr-1.5 h-4 w-4" />
          )}
          Aprovar revisão jurídica
        </Button>
      ) : (
        <p
          className="text-[11px] text-warning-foreground"
          data-testid={`${testIdPrefix}-so-admin-${contratoId}`}
        >
          A revisão jurídica é aprovada por um administrador do escritório.
        </p>
      )}
      {onAprovar && podeAprovarRevisao && (
        <Dialog open={confirmarAberto} onOpenChange={setConfirmarAberto}>
          <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Aprovar revisão jurídica</DialogTitle>
              <DialogDescription>
                Confirme que {documento === "aditivo" ? "o aditivo" : "o contrato"} da versão{" "}
                {versao.numero} foi revisado por inteiro
                {(revisao.itens?.length ?? 0) > 0
                  ? `, incluindo ${revisao.itens!.length === 1 ? "o texto listado" : `os ${revisao.itens!.length} textos listados`}`
                  : ""}
                .
                {extraidos > 0 &&
                  (extraidos === 1
                    ? " O dado extraído automaticamente passa a constar como confirmado por você."
                    : ` Os ${extraidos} dados extraídos automaticamente passam a constar como confirmados por você.`)}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="flex-col gap-2 sm:flex-row">
              <Button
                type="button"
                variant="ghost"
                className="min-h-10"
                onClick={() => setConfirmarAberto(false)}
              >
                Voltar
              </Button>
              <Button
                type="button"
                className="min-h-10"
                disabled={aprovando}
                onClick={() => {
                  onAprovar(versao.id);
                  setConfirmarAberto(false);
                }}
                data-testid={`${testIdPrefix}-aprovar-confirmar-${contratoId}`}
              >
                Aprovar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

export default RevisaoJuridicaSection;
