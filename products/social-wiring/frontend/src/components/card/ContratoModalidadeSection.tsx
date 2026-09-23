/**
 * ContratoModalidadeSection — migration 157: the Digital / Física signing
 * GATE on a contract, and the física close-out.
 *
 * - The segmented toggle writes `modalidade_assinatura` (PATCH). Going
 *   `fisica` while an e-signature envelope is live is refused by the server
 *   (409 `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO`); the toggle mirrors
 *   that by disabling "Física" and saying why — the server stays the gate.
 * - `digital` renders `digitalContent` untouched (the existing
 *   "Enviar para assinatura" / envelope-status section).
 * - `fisica` NEVER renders the send-for-signature path. It shows
 *   "Baixar para impressão" — only for a version GENERATED as física (the
 *   one with signature lines; `versaoParaImpressao`) — and
 *   "Marcar como assinado", with an optional scanned PDF.
 *
 * Mobile-first: the toggle is full-width at 390px, every touch target is
 * ≥ 40px (`min-h-10`), actions stack and only go side-by-side from `sm`.
 */
import { type ChangeEvent, type ReactNode, useRef, useState } from "react";
import { CheckCircle2, FileDown, Loader2, PenLine, Printer, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ContratoOut, ModalidadeAssinatura } from "@/hooks/useContratos";
import {
  CONTRATO_ASSINADO_ACCEPT_ATTR,
  MODALIDADE_ASSINATURA_LABEL,
  validateContratoAssinadoFile,
  versaoParaImpressao,
} from "@/hooks/useContratos";

const MODALIDADES: ModalidadeAssinatura[] = ["digital", "fisica"];

export interface ContratoModalidadeSectionProps {
  contrato: ContratoOut;
  /** A live (pendente/parcial) e-signature envelope exists. */
  envelopeVivo: boolean;
  /** The PATCH for THIS contract is in flight. */
  patching?: boolean;
  onPatchModalidade?: (modalidade: ModalidadeAssinatura) => void;
  onBaixarImpressao: (versaoId: string) => void;
  onMarcarAssinado?: (file: File | null) => void;
  marcandoAssinado?: boolean;
  /** Rendered only for `digital` — the existing send-for-signature section. */
  digitalContent?: ReactNode;
}

export function ContratoModalidadeSection({
  contrato,
  envelopeVivo,
  patching = false,
  onPatchModalidade,
  onBaixarImpressao,
  onMarcarAssinado,
  marcandoAssinado = false,
  digitalContent,
}: ContratoModalidadeSectionProps) {
  const modalidade = contrato.modalidade_assinatura ?? "digital";
  const id = contrato.id;
  const [dialogAberto, setDialogAberto] = useState(false);

  const fisicaBloqueada = envelopeVivo && modalidade === "digital";
  const encerrado = contrato.status === "cancelado";
  const impressao = versaoParaImpressao(contrato);
  const assinado = contrato.status === "assinado";

  return (
    <div className="space-y-2" data-testid={`contrato-modalidade-${id}`}>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground" id={`contrato-modalidade-label-${id}`}>
          Assinatura
        </p>
        <div
          role="radiogroup"
          aria-labelledby={`contrato-modalidade-label-${id}`}
          className="grid w-full grid-cols-2 gap-1 rounded-md border bg-muted/40 p-1 sm:inline-grid sm:w-auto"
          data-testid={`contrato-modalidade-toggle-${id}`}
        >
          {MODALIDADES.map((m) => {
            const ativo = m === modalidade;
            const desabilitado =
              !onPatchModalidade || patching || encerrado || (m === "fisica" && fisicaBloqueada);
            return (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={ativo}
                disabled={desabilitado}
                onClick={() => {
                  if (!ativo && onPatchModalidade) onPatchModalidade(m);
                }}
                className={[
                  "min-h-10 rounded px-4 text-sm font-medium transition-colors",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                  ativo
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                ].join(" ")}
                data-testid={`contrato-modalidade-${m}-${id}`}
              >
                {MODALIDADE_ASSINATURA_LABEL[m]}
              </button>
            );
          })}
        </div>
        {fisicaBloqueada && (
          <p className="text-[11px] text-muted-foreground" data-testid={`contrato-modalidade-bloqueio-${id}`}>
            Há uma assinatura digital em andamento — cancele o envio para mudar para física.
          </p>
        )}
      </div>

      {modalidade === "digital" ? (
        digitalContent ?? null
      ) : (
        <div className="space-y-2 rounded-md border p-2.5" data-testid={`contrato-fisica-${id}`}>
          <p className="text-xs text-muted-foreground">
            Assinatura física: imprima o contrato, colete as assinaturas das partes e das
            testemunhas e marque-o como assinado. Nada é enviado por e-mail.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Button
              type="button"
              variant="outline"
              className="min-h-10 w-full sm:w-auto"
              disabled={!impressao}
              onClick={() => impressao && onBaixarImpressao(impressao.id)}
              data-testid={`contrato-baixar-impressao-${id}`}
            >
              <Printer className="mr-1.5 h-4 w-4" />
              Baixar para impressão
            </Button>
            {onMarcarAssinado && !encerrado && (
              <Button
                type="button"
                className="min-h-10 w-full sm:w-auto"
                disabled={marcandoAssinado}
                onClick={() => setDialogAberto(true)}
                data-testid={`contrato-marcar-assinado-${id}`}
              >
                {marcandoAssinado ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : assinado ? (
                  <Upload className="mr-1.5 h-4 w-4" />
                ) : (
                  <PenLine className="mr-1.5 h-4 w-4" />
                )}
                {assinado ? "Anexar contrato assinado" : "Marcar como assinado"}
              </Button>
            )}
          </div>
          {!impressao && (
            <p className="text-[11px] text-muted-foreground" data-testid={`contrato-impressao-hint-${id}`}>
              Gere uma nova versão do contrato com a assinatura física para imprimir com as
              linhas de assinatura.
            </p>
          )}
          {assinado && (
            <p
              className="flex items-center gap-1.5 text-xs text-emerald-700"
              data-testid={`contrato-fisica-assinado-${id}`}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Assinado
              {contrato.status_por?.nome ? ` · marcado por ${contrato.status_por.nome}` : ""}
              {contrato.status_em
                ? ` · ${new Date(contrato.status_em).toLocaleString("pt-BR")}`
                : ""}
            </p>
          )}
          {onMarcarAssinado && (
            <_MarcarAssinadoDialog
              contratoId={id}
              open={dialogAberto}
              onOpenChange={setDialogAberto}
              jaAssinado={assinado}
              enviando={marcandoAssinado}
              onConfirmar={(file) => {
                onMarcarAssinado(file);
                setDialogAberto(false);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

function _MarcarAssinadoDialog({
  contratoId,
  open,
  onOpenChange,
  jaAssinado,
  enviando,
  onConfirmar,
}: {
  contratoId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jaAssinado: boolean;
  enviando: boolean;
  onConfirmar: (file: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function fechar(aberto: boolean) {
    if (!aberto) {
      setArquivo(null);
      setErro(null);
    }
    onOpenChange(aberto);
  }

  function escolher(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    e.target.value = "";
    if (!file) return;
    const problema = validateContratoAssinadoFile(file);
    setErro(problema);
    setArquivo(problema ? null : file);
  }

  // Already signed ⇒ this dialog exists to attach the scan; it is required.
  const podeConfirmar = !enviando && !erro && (!jaAssinado || !!arquivo);

  return (
    <Dialog open={open} onOpenChange={fechar}>
      <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{jaAssinado ? "Anexar contrato assinado" : "Marcar como assinado"}</DialogTitle>
          <DialogDescription>
            {jaAssinado
              ? "Anexe o PDF digitalizado do contrato assinado."
              : "Confirme que o contrato impresso foi assinado pelas partes e testemunhas. Se quiser, anexe o PDF digitalizado."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <input
            ref={inputRef}
            type="file"
            accept={CONTRATO_ASSINADO_ACCEPT_ATTR}
            className="hidden"
            onChange={escolher}
            data-testid={`contrato-assinado-arquivo-${contratoId}`}
          />
          <Button
            type="button"
            variant="outline"
            className="min-h-10 w-full"
            onClick={() => inputRef.current?.click()}
          >
            <FileDown className="mr-1.5 h-4 w-4" />
            {arquivo ? arquivo.name : "Escolher PDF digitalizado (opcional)"}
          </Button>
          {erro && (
            <p className="text-xs text-destructive" data-testid={`contrato-assinado-arquivo-erro-${contratoId}`}>
              {erro}
            </p>
          )}
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row">
          <Button type="button" variant="ghost" className="min-h-10" onClick={() => fechar(false)}>
            Voltar
          </Button>
          <Button
            type="button"
            className="min-h-10"
            disabled={!podeConfirmar}
            onClick={() => onConfirmar(arquivo)}
            data-testid={`contrato-marcar-assinado-confirmar-${contratoId}`}
          >
            {jaAssinado ? "Anexar" : "Confirmar assinatura"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ContratoModalidadeSection;
