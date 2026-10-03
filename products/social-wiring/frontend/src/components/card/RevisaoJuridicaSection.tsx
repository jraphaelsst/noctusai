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
 *   - a machine-extracted value ("extraído automaticamente — revisar no
 *     documento": the value itself is read in the PDF, never repeated here);
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
import { CONFIANCA_ROTULO, ORIGEM_ROTULO } from "@/hooks/useValidacaoExtracao";

import { ItensRevisaoLista } from "./ItensRevisaoLista";

/** `origem` values that are NOT a machine reading of a document — an
 *  aditivo's generated wording and a clause the team wrote by hand. */
const ORIGEM_NAO_EXTRAIDA: Record<string, string> = {
  gerado: "texto gerado pelo sistema",
  manual: "redigido pela equipe",
};

/** A campo read off a document by a machine (anything but the two above —
 *  including a missing `origem`, which the pre-aditivo rows never had). */
export function campoExtraido(campo: CampoRevisaoJuridica): boolean {
  return !(campo.origem && campo.origem in ORIGEM_NAO_EXTRAIDA);
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
  isAdmin: boolean;
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
  isAdmin,
  onAprovar,
  aprovando = false,
  documento = "contrato",
  testIdPrefix = "contrato-revisao",
}: RevisaoJuridicaSectionProps) {
  const [confirmarAberto, setConfirmarAberto] = useState(false);
  const status = revisaoJuridicaStatus(versao);
  const revisao = versao.revisao_juridica;

  if (status === "nao_exigida" || !revisao) return null;

  if (status === "aprovada") {
    return (
      <p
        className="flex flex-wrap items-center gap-1.5 text-xs text-emerald-700"
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
  return (
    <div
      className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-2.5"
      data-testid={`${testIdPrefix}-aguardando-${contratoId}`}
    >
      <div className="space-y-0.5">
        <p className="flex items-center gap-1.5 text-sm font-medium text-amber-900">
          <FileSearch className="h-4 w-4 shrink-0" />
          Aguardando revisão jurídica
        </p>
        <p className="text-xs text-amber-800" data-testid={`${testIdPrefix}-texto-${contratoId}`}>
          {textoRevisaoAguardando(campos, documento)}
        </p>
      </div>
      {campos.length > 0 && (
        <ul className="space-y-1" data-testid={`${testIdPrefix}-campos-${contratoId}`}>
          {campos.map((c) => (
            <li
              key={c.chave}
              className="flex flex-wrap items-baseline gap-x-1.5 rounded border border-amber-200 bg-white/70 px-2 py-1 text-xs"
              data-testid={`${testIdPrefix}-campo-${c.chave}`}
            >
              <span className="font-medium">{c.rotulo}</span>
              {c.grupo && <span className="text-muted-foreground">· {c.grupo}</span>}
              <span className="w-full text-[11px] text-amber-800 sm:w-auto">
                {campoExtraido(c) ? (
                  <>
                    extraído automaticamente
                    {c.origem ? ` (${ORIGEM_ROTULO[c.origem] ?? c.origem}` : ""}
                    {c.origem && c.fonte_nome ? ` · ${c.fonte_nome}` : ""}
                    {c.origem && c.confianca ? ` · ${CONFIANCA_ROTULO[c.confianca] ?? c.confianca}` : ""}
                    {c.origem ? ")" : ""}
                  </>
                ) : (
                  ORIGEM_NAO_EXTRAIDA[c.origem as string]
                )}{" "}
                — revisar no documento
              </span>
            </li>
          ))}
        </ul>
      )}
      <ItensRevisaoLista
        itens={revisao.itens}
        titulo="Textos para leitura obrigatória antes de aprovar"
        testId={`${testIdPrefix}-itens-${contratoId}`}
        tom="revisao"
      />
      {onAprovar && isAdmin ? (
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
          className="text-[11px] text-amber-800"
          data-testid={`${testIdPrefix}-so-admin-${contratoId}`}
        >
          A revisão jurídica é aprovada por um administrador do escritório.
        </p>
      )}
      {onAprovar && isAdmin && (
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
