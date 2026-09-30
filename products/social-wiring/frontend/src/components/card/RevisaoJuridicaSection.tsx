/**
 * RevisaoJuridicaSection — one final legal review per contract version
 * (owner decision 2026-09-30, backend migration 177).
 *
 * Owner, verbatim: asked "replace the per-field confirmations with one final
 * review of the finished contract by the legal team?" → "yes". A version
 * generated from machine-extracted values nobody validated is
 * "Aguardando revisão jurídica": this section lists those values
 * ("extraído automaticamente — revisar no documento": the value itself is
 * read in the PDF, never repeated here) and offers the ONE action,
 * "Aprovar revisão jurídica". The server is the gate — signature and
 * "Baixar para impressão" are refused (409) until it is approved; the
 * button is only a UI convenience for admins (the POST 403s anyone else,
 * reading the TRUSTED `noctus_users` row).
 *
 * States: `nao_exigida` renders nothing; `aguardando` the amber list + the
 * button (or, for a non-admin, who can approve); `aprovada` a green line with
 * who/when. The review state comes off the version already on screen — no
 * query of its own, so no skeleton to lie with.
 *
 * Presentational (S3) — `ContratosContainer` owns the mutation.
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
import type { VersaoOut } from "@/hooks/useContratos";
import { revisaoJuridicaStatus } from "@/hooks/useContratos";
import { CONFIANCA_ROTULO, ORIGEM_ROTULO } from "@/hooks/useValidacaoExtracao";

export interface RevisaoJuridicaSectionProps {
  contratoId: string;
  versao: VersaoOut;
  /** UI convenience only — the server re-checks the trusted role. */
  isAdmin: boolean;
  /** Omitted ⇒ no button (the caller has not wired the action). */
  onAprovar?: (versaoId: string) => void;
  aprovando?: boolean;
}

export function RevisaoJuridicaSection({
  contratoId,
  versao,
  isAdmin,
  onAprovar,
  aprovando = false,
}: RevisaoJuridicaSectionProps) {
  const [confirmarAberto, setConfirmarAberto] = useState(false);
  const status = revisaoJuridicaStatus(versao);
  const revisao = versao.revisao_juridica;

  if (status === "nao_exigida" || !revisao) return null;

  if (status === "aprovada") {
    return (
      <p
        className="flex flex-wrap items-center gap-1.5 text-xs text-emerald-700"
        data-testid={`contrato-revisao-aprovada-${contratoId}`}
      >
        <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
        Revisão jurídica aprovada
        {revisao.revisado_por?.nome ? ` · por ${revisao.revisado_por.nome}` : ""}
        {revisao.revisado_em ? ` · ${new Date(revisao.revisado_em).toLocaleString("pt-BR")}` : ""}
      </p>
    );
  }

  const campos = revisao.campos;
  return (
    <div
      className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-2.5"
      data-testid={`contrato-revisao-aguardando-${contratoId}`}
    >
      <div className="space-y-0.5">
        <p className="flex items-center gap-1.5 text-sm font-medium text-amber-900">
          <FileSearch className="h-4 w-4 shrink-0" />
          Aguardando revisão jurídica
        </p>
        <p className="text-xs text-amber-800">
          Esta versão (rascunho) usa {campos.length === 1 ? "um dado" : `${campos.length} dados`}{" "}
          extraído{campos.length === 1 ? "" : "s"} automaticamente de documentos. Confira{" "}
          {campos.length === 1 ? "o valor" : "os valores"} no PDF e aprove a revisão para liberar
          o envio para assinatura e a impressão.
        </p>
      </div>
      <ul className="space-y-1" data-testid={`contrato-revisao-campos-${contratoId}`}>
        {campos.map((c) => (
          <li
            key={c.chave}
            className="flex flex-wrap items-baseline gap-x-1.5 rounded border border-amber-200 bg-white/70 px-2 py-1 text-xs"
            data-testid={`contrato-revisao-campo-${c.chave}`}
          >
            <span className="font-medium">{c.rotulo}</span>
            {c.grupo && <span className="text-muted-foreground">· {c.grupo}</span>}
            <span className="w-full text-[11px] text-amber-800 sm:w-auto">
              extraído automaticamente
              {c.origem ? ` (${ORIGEM_ROTULO[c.origem] ?? c.origem}` : ""}
              {c.origem && c.fonte_nome ? ` · ${c.fonte_nome}` : ""}
              {c.origem && c.confianca ? ` · ${CONFIANCA_ROTULO[c.confianca] ?? c.confianca}` : ""}
              {c.origem ? ")" : ""} — revisar no documento
            </span>
          </li>
        ))}
      </ul>
      {onAprovar && isAdmin ? (
        <Button
          type="button"
          size="sm"
          className="min-h-10 w-full sm:w-auto"
          disabled={aprovando}
          onClick={() => setConfirmarAberto(true)}
          data-testid={`contrato-revisao-aprovar-${contratoId}`}
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
          data-testid={`contrato-revisao-so-admin-${contratoId}`}
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
                Confirme que o contrato da versão {versao.numero} foi revisado por inteiro. Os{" "}
                {campos.length} dado{campos.length === 1 ? "" : "s"} extraído
                {campos.length === 1 ? "" : "s"} automaticamente passa
                {campos.length === 1 ? "" : "m"} a constar como confirmado
                {campos.length === 1 ? "" : "s"} por você.
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
                data-testid={`contrato-revisao-aprovar-confirmar-${contratoId}`}
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
