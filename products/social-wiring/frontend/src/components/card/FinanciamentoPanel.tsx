/**
 * `<FinanciamentoPanel/>` — the card's Financiamento/Escritura subpage.
 *
 * The decision (pendente / aprovado / recusado), then the paperwork: the
 * escritura set always, the FGTS set only when FGTS is in play.
 *
 * 🔴 ONE SLOT PER DOCUMENT TYPE, NOT A FREE PILE
 * -----------------------------------------------
 * Every required type is rendered whether or not a file exists for it, so the
 * panel answers "what is still missing" without anyone having to hold the
 * list in their head. A plain uploads list would show what HAS arrived and
 * say nothing about what has not — which is the question this screen exists
 * to answer.
 *
 * 🔴 OPENING A DOCUMENT IS A RECORDED ACCESS
 * -------------------------------------------
 * These are income tax returns and employment records. The signed-URL call is
 * made only on an explicit click — never on render, never on a timer — because
 * each one appends to the server-side access log naming the viewer.
 */
import { useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import type {
  Financiamento,
  FinanciamentoDocumento,
  FinanciamentoPatch,
  SituacaoFinanciamento,
} from "@/hooks/useFinanciamento";
import { SITUACAO_LABEL, TIPO_LABEL, formatBytes } from "@/hooks/useFinanciamento";

interface Props {
  financiamento: Financiamento | undefined;
  loading: boolean;
  saving: boolean;
  uploading: boolean;
  error?: string | null;
  onSave: (patch: FinanciamentoPatch) => void;
  onUpload: (file: File, tipoDocumento: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
}

const SITUACOES: SituacaoFinanciamento[] = ["pendente", "aprovado", "recusado"];

const SITUACAO_ICON = {
  pendente: Clock,
  aprovado: CheckCircle2,
  recusado: XCircle,
} as const;

export default function FinanciamentoPanel({
  financiamento,
  loading,
  saving,
  uploading,
  error,
  onSave,
  onUpload,
  onRemove,
  onOpen,
}: Props) {
  const [observacoes, setObservacoes] = useState<string | null>(null);

  const f = financiamento;
  const situacao = f?.situacao ?? "pendente";
  const docsPorTipo = new Map<string, FinanciamentoDocumento>();
  (f?.documentos ?? []).forEach((d) => {
    // Newest first from the server, so the first one wins — a re-uploaded
    // document supersedes its predecessor in the slot without hiding it from
    // the audit trail, which lives server-side.
    if (!docsPorTipo.has(d.tipo_documento)) docsPorTipo.set(d.tipo_documento, d);
  });

  const faltando = [
    ...(f?.tipos_escritura ?? []),
    ...(f?.fgts ? f?.tipos_fgts ?? [] : []),
  ].filter((t) => !docsPorTipo.has(t)).length;

  return (
    <div className="space-y-4" data-testid="financiamento-panel">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Situação do financiamento</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {SITUACOES.map((s) => {
              const Icon = SITUACAO_ICON[s];
              const ativa = s === situacao;
              return (
                <Button
                  key={s}
                  type="button"
                  size="sm"
                  variant={ativa ? "default" : "outline"}
                  disabled={loading || saving}
                  onClick={() => onSave({ situacao: s })}
                  data-testid={`financiamento-situacao-${s}`}
                  aria-pressed={ativa}
                >
                  <Icon className="mr-1.5 h-3.5 w-3.5" />
                  {SITUACAO_LABEL[s]}
                </Button>
              );
            })}
          </div>

          {f?.situacao_em && situacao !== "pendente" && (
            <p className="text-xs text-muted-foreground">
              {SITUACAO_LABEL[situacao]} em{" "}
              {new Date(f.situacao_em).toLocaleString("pt-BR")}
            </p>
          )}

          <div className="flex items-center justify-between rounded-md border p-3">
            <Label htmlFor="fgts-financiamento" className="cursor-pointer">
              Vai usar FGTS
            </Label>
            <Switch
              id="fgts-financiamento"
              checked={f?.fgts ?? false}
              onCheckedChange={(v) => onSave({ fgts: v })}
              disabled={loading || saving}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="financiamento-observacoes">Observações</Label>
            <Textarea
              id="financiamento-observacoes"
              rows={2}
              value={observacoes ?? f?.observacoes ?? ""}
              onChange={(e) => setObservacoes(e.target.value)}
              onBlur={() => {
                if (observacoes !== null && observacoes !== (f?.observacoes ?? "")) {
                  onSave({ observacoes: observacoes.trim() || null });
                }
              }}
              disabled={loading}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Secao
        titulo="Escritura"
        tipos={f?.tipos_escritura ?? []}
        docsPorTipo={docsPorTipo}
        loading={loading}
        uploading={uploading}
        onUpload={onUpload}
        onRemove={onRemove}
        onOpen={onOpen}
      />

      {f?.fgts && (
        <Secao
          titulo="FGTS"
          tipos={f?.tipos_fgts ?? []}
          docsPorTipo={docsPorTipo}
          loading={loading}
          uploading={uploading}
          onUpload={onUpload}
          onRemove={onRemove}
          onOpen={onOpen}
        />
      )}

      {faltando > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="financiamento-faltando">
          {faltando} documento{faltando > 1 ? "s" : ""} ainda não enviado
          {faltando > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}

function Secao({
  titulo,
  tipos,
  docsPorTipo,
  loading,
  uploading,
  onUpload,
  onRemove,
  onOpen,
}: {
  titulo: string;
  tipos: string[];
  docsPorTipo: Map<string, FinanciamentoDocumento>;
  loading: boolean;
  uploading: boolean;
  onUpload: (file: File, tipo: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4" />
          {titulo}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {tipos.map((tipo) => (
          <Slot
            key={tipo}
            tipo={tipo}
            documento={docsPorTipo.get(tipo)}
            loading={loading}
            uploading={uploading}
            onUpload={onUpload}
            onRemove={onRemove}
            onOpen={onOpen}
          />
        ))}
      </CardContent>
    </Card>
  );
}

/** One required document type — filled or not. */
function Slot({
  tipo,
  documento,
  loading,
  uploading,
  onUpload,
  onRemove,
  onOpen,
}: {
  tipo: string;
  documento: FinanciamentoDocumento | undefined;
  loading: boolean;
  uploading: boolean;
  onUpload: (file: File, tipo: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
}) {
  // 🔴 Its OWN input, per slot, held by a ref — never a shared
  // `getElementById`. That is the bug that would file every slot's upload
  // onto whichever one rendered the shared node.
  const inputRef = useRef<HTMLInputElement>(null);
  const label = TIPO_LABEL[tipo] ?? tipo;

  return (
    <div className="flex items-center justify-between gap-3 rounded-md border p-3">
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-medium">{label}</p>
        {documento ? (
          <button
            type="button"
            onClick={() => onOpen(documento.id)}
            className="truncate text-xs text-muted-foreground hover:underline"
            title="Abrir (registra um acesso)"
          >
            {documento.nome_original} · {formatBytes(documento.tamanho_bytes)}
          </button>
        ) : (
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <AlertCircle className="h-3 w-3" />
            Não enviado
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {documento && (
          <Badge variant="secondary" className="text-[10px]">
            enviado
          </Badge>
        )}
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label={`Enviar ${label}`}
          title={documento ? "Substituir" : "Enviar"}
          disabled={loading || uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
        </Button>
        {documento && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label={`Remover ${label}`}
            title="Remover"
            onClick={() => {
              const motivo = window.prompt(
                "Por que este documento está sendo removido?",
              );
              // Cancelled or blank is a CANCEL, not a delete with no reason —
              // an LGPD delete without a recorded reason is not one.
              if (motivo && motivo.trim()) onRemove(documento.id, motivo.trim());
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept="application/pdf,image/jpeg,image/png,image/webp"
          data-testid={`financiamento-input-${tipo}`}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(file, tipo);
            // Reset so choosing the SAME file twice still fires a change.
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
