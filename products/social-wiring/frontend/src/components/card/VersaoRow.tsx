/**
 * `<VersaoRow/>` — one row of a document's version history: number, rótulo,
 * origem marks (gerado / rascunho awaiting the legal review / assinado),
 * file + author + date, and Abrir / Baixar PDF / Baixar .docx (+ Excluir).
 *
 * Extracted from `ContratosPanel` so a contract AND an aditivo
 * (`aditivos/AditivosSection`) render their versions through ONE row — the
 * aditivo version IS the contract version shape (contrato-aditivos-CONTRACT
 * §1.3).
 */
import { FileDown, FileType2, Eye, Loader2, Trash2 } from "lucide-react";

import { TooltipIconButton } from "@noctusai/lib/components";

import type { VersaoOut } from "@/hooks/useContratos";
import { aguardandoRevisaoJuridica, formatBytes } from "@/hooks/useContratos";

export function VersaoRow({
  versao,
  deleting,
  podeExcluir,
  baixandoDocx,
  onOpen,
  onDownload,
  onDownloadDocx,
  onExcluir,
  testIdPrefix = "contrato-versao",
}: {
  versao: VersaoOut;
  deleting: boolean;
  podeExcluir: boolean;
  baixandoDocx: boolean;
  onOpen: () => void;
  onDownload: () => void;
  onDownloadDocx: () => void;
  /** Omitted ⇒ no delete button (e.g. aditivo versions — no such route). */
  onExcluir?: () => void;
  /** Test-id prefix. Default `"contrato-versao"`. */
  testIdPrefix?: string;
}) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed p-2 text-xs"
      data-testid={`${testIdPrefix}-${versao.id}`}
    >
      <div className="min-w-0 space-y-0.5">
        <p className="truncate">
          Versão {versao.numero}
          {versao.rotulo ? ` · ${versao.rotulo}` : ""}
          {versao.origem === "gerado" && (
            <span className="ml-1.5 text-muted-foreground">(gerado automaticamente)</span>
          )}
          {aguardandoRevisaoJuridica(versao) && (
            <span
              className="ml-1.5 text-amber-700"
              data-testid={`${testIdPrefix}-rascunho-${versao.id}`}
            >
              (rascunho)
            </span>
          )}
          {versao.origem === "assinado" && (
            <span
              className="ml-1.5 text-muted-foreground"
              data-testid={`${testIdPrefix}-assinado-${versao.id}`}
            >
              (Assinado)
            </span>
          )}
        </p>
        <p className="truncate text-muted-foreground">
          {versao.nome_original} · {formatBytes(versao.tamanho_bytes)}
          {versao.enviado_por?.nome ? ` · ${versao.enviado_por.nome}` : ""} ·{" "}
          {new Date(versao.created_at).toLocaleString("pt-BR")}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <TooltipIconButton
          label="Abrir"
          icon={Eye}
          className="h-7 w-7"
          onClick={onOpen}
          testId={`${testIdPrefix}-abrir-${versao.id}`}
        />
        <TooltipIconButton
          label="Baixar PDF"
          icon={FileDown}
          className="h-7 w-7"
          onClick={onDownload}
          testId={`${testIdPrefix}-baixar-${versao.id}`}
        />
        {versao.docx_disponivel && (
          <TooltipIconButton
            label="Baixar .docx"
            icon={baixandoDocx ? Loader2 : FileType2}
            iconClassName={baixandoDocx ? "animate-spin" : undefined}
            className="h-7 w-7"
            disabled={baixandoDocx}
            onClick={onDownloadDocx}
            testId={`${testIdPrefix}-baixar-docx-${versao.id}`}
          />
        )}
        {podeExcluir && onExcluir && (
          <TooltipIconButton
            label="Excluir versão"
            icon={Trash2}
            className="h-7 w-7"
            disabled={deleting}
            onClick={onExcluir}
            testId={`${testIdPrefix}-excluir-${versao.id}`}
          />
        )}
      </div>
    </div>
  );
}
