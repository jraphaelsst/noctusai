/**
 * `<ImovelCertidoesCard/>` — the imóvel's CND group for the contract
 * (migration 118): CND de IPTU, CND de condomínio, and the matrícula
 * certidão's own emission date.
 *
 * 🔴 THE 30-DAY RULE IS A WARNING, NOT A REFUSAL
 * -----------------------------------------------
 * The office requires each certidão to be LESS than 30 days old at signing,
 * so an old one is called out loudly — but nothing here blocks anything. Same
 * posture as the situação-de-ônus fields (`useImovelDados`): the policy for
 * what to do about a stale certidão is the user's, and a gate written before
 * its policy is a gate that gets worked around. What the UI owes the operator
 * is the AGE, in days, next to the date — not a verdict.
 *
 * 🔴 ONLY THE FIELDS THIS TIPO CARRIES ARE OFFERED
 * -------------------------------------------------
 * `confirmar_extracao` 400s any field a `tipo_documento` does not have (a
 * `resultado` on a guia de IPTU, a `numero` on a condomínio declaration), so
 * the editor renders `CAMPOS_POR_TIPO[tipo]` and nothing else. Offering a
 * field the backend refuses turns a review screen into a 400 the operator
 * cannot act on.
 *
 * PRESENTATIONAL: props in, callbacks out. `ImovelContratoContainer` fetches.
 */
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FileCheck2, Loader2, Sparkles, Upload } from "lucide-react";
import { useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  CAMPOS_POR_TIPO,
  CERTIDAO_MAX_DIAS,
  RESULTADO_LABEL,
  certidaoDesatualizada,
  diasDesdeEmissao,
  type CertidaoResultado,
  type DocumentoExtracaoPatch,
  type ImovelCertidao,
} from "@/hooks/useImovelContrato";

/** Radix `SelectItem` refuses `""`, so "not read" needs a real token. */
const SEM_RESULTADO = "__sem_resultado__";

/** The group, in the order the contract asks for it — mirrors
 *  `documentos_service.CERTIDOES_TIPOS`. */
export const TIPOS_CERTIDAO = [
  { value: "cnd_iptu", label: "CND de IPTU" },
  { value: "cnd_condominio", label: "CND de condomínio" },
  { value: "matricula", label: "Certidão da matrícula" },
] as const;

/** What THIS card uploads. The matrícula is uploaded on the documents card
 *  (it also starts the transcription); here the operator adds the two CNDs
 *  migration 118 introduced. */
const TIPOS_UPLOAD = TIPOS_CERTIDAO.filter((t) => t.value !== "matricula");

const CAMPO_LABEL: Record<keyof DocumentoExtracaoPatch, string> = {
  numero: "Número",
  emitida_em: "Emitida em",
  validade_ate: "Validade até",
  resultado: "Resultado",
  inscricao_imobiliaria: "Inscrição imobiliária",
};

export interface ImovelCertidoesCardProps {
  certidoes: ImovelCertidao[] | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  uploading: boolean;
  /** The document whose confirmation is in flight, or `null`. */
  savingDocumentoId: string | null;
  errorMessage?: string | null;
  onUpload: (file: File, tipoDocumento: string) => void;
  onConfirmar: (
    documentoId: string,
    tipo: string,
    patch: DocumentoExtracaoPatch,
  ) => void;
  /** Test seam for the 30-day rule — defaults to now. */
  hoje?: Date;
}

type Draft = Record<string, string>;

function toDraft(certidao: ImovelCertidao, campos: readonly (keyof DocumentoExtracaoPatch)[]): Draft {
  const draft: Draft = {};
  for (const campo of campos) {
    const valor = certidao[campo as keyof ImovelCertidao] as string | null | undefined;
    draft[campo] =
      campo === "emitida_em" || campo === "validade_ate"
        ? (valor ?? "").slice(0, 10)
        : campo === "resultado"
          ? (valor ?? SEM_RESULTADO)
          : (valor ?? "");
  }
  return draft;
}

function limpo(v: string): string | null {
  const t = v.trim();
  return t === "" ? null : t;
}

/**
 * Only what changed — absent key = keep, `null` = clear, `{}` = "I reviewed
 * this and it is correct". Exported for its own test: this is the contract
 * with `PATCH .../extracao`.
 */
export function buildCertidaoPatch(
  draft: Draft,
  certidao: ImovelCertidao,
  campos: readonly (keyof DocumentoExtracaoPatch)[],
): DocumentoExtracaoPatch {
  const patch: DocumentoExtracaoPatch = {};
  for (const campo of campos) {
    const bruto = draft[campo] ?? "";
    const novo = campo === "resultado" && bruto === SEM_RESULTADO ? null : limpo(bruto);
    const atual = (certidao[campo as keyof ImovelCertidao] as string | null | undefined) ?? null;
    const atualNormalizado =
      campo === "emitida_em" || campo === "validade_ate"
        ? (atual ? atual.slice(0, 10) : null)
        : atual;
    if (novo !== atualNormalizado) {
      // `as never` — the per-field value type is narrowed by `campo`, which
      // TS cannot follow through a dynamic key on a union of field types.
      patch[campo] = novo as never;
    }
  }
  return patch;
}

function CertidaoEditor({
  tipo,
  label,
  certidao,
  saving,
  hoje,
  onConfirmar,
}: {
  tipo: string;
  label: string;
  certidao: ImovelCertidao;
  saving: boolean;
  hoje: Date;
  onConfirmar: (documentoId: string, tipo: string, patch: DocumentoExtracaoPatch) => void;
}) {
  const campos = CAMPOS_POR_TIPO[tipo] ?? [];
  const [draft, setDraft] = useState<Draft>(() => toDraft(certidao, campos));

  // Re-seed on the SERVER's values (serialised), not object identity — a
  // background refetch that changed nothing must not stomp an edit.
  const assinatura = JSON.stringify(campos.map((c) => certidao[c as keyof ImovelCertidao] ?? null));
  useEffect(() => {
    setDraft(toDraft(certidao, campos));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assinatura]);

  const patch = buildCertidaoPatch(draft, certidao, campos);
  const semAlteracoes = Object.keys(patch).length === 0;
  const dias = diasDesdeEmissao(certidao.emitida_em, hoje);
  const velha = certidaoDesatualizada(certidao.emitida_em, hoje);

  return (
    <div className="space-y-2 rounded-md border p-2.5" data-testid={`certidao-${tipo}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{label}</p>
        {certidao.confirmado ? (
          <Badge variant="secondary" className="gap-1 text-[10px]" data-testid={`certidao-${tipo}-confirmada`}>
            <CheckCircle2 className="h-3 w-3" />
            Conferida
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="gap-1 border-amber-500 bg-amber-50 text-[10px] text-amber-700"
            data-testid={`certidao-${tipo}-sugestao`}
          >
            <Sparkles className="h-3 w-3" />
            Leitura automática — confira
          </Badge>
        )}
      </div>

      {/* 🔴 The office's 30-day rule, as an age rather than a verdict. */}
      {velha && (
        <p
          className="flex items-start gap-1.5 rounded border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive"
          data-testid={`certidao-${tipo}-idade`}
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Emitida há {dias} dias. O cartório exige certidão com menos de {CERTIDAO_MAX_DIAS} dias
          na assinatura — peça uma nova.
        </p>
      )}
      {!velha && dias !== null && (
        <p className="text-[11px] text-muted-foreground" data-testid={`certidao-${tipo}-idade-ok`}>
          Emitida há {dias} dia(s).
        </p>
      )}
      {certidao.emitida_em === null && (
        <p className="text-[11px] text-muted-foreground" data-testid={`certidao-${tipo}-sem-data`}>
          A data de emissão não foi lida — informe-a para conferir o prazo de 30 dias.
        </p>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        {campos.map((campo) =>
          campo === "resultado" ? (
            <div key={campo} className="space-y-1">
              <Label className="text-xs" htmlFor={`certidao-${tipo}-resultado`}>
                {CAMPO_LABEL[campo]}
              </Label>
              <Select
                value={draft[campo] ?? SEM_RESULTADO}
                onValueChange={(v) => setDraft((d) => ({ ...d, [campo]: v }))}
                disabled={saving}
              >
                <SelectTrigger
                  id={`certidao-${tipo}-resultado`}
                  className="h-8 text-sm"
                  data-testid={`certidao-${tipo}-resultado`}
                >
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SEM_RESULTADO}>Não informado</SelectItem>
                  {(Object.keys(RESULTADO_LABEL) as CertidaoResultado[]).map((r) => (
                    <SelectItem key={r} value={r}>
                      {RESULTADO_LABEL[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div key={campo} className="space-y-1">
              <Label className="text-xs" htmlFor={`certidao-${tipo}-${campo}`}>
                {CAMPO_LABEL[campo]}
              </Label>
              <Input
                id={`certidao-${tipo}-${campo}`}
                type={campo === "emitida_em" || campo === "validade_ate" ? "date" : "text"}
                className="h-8 text-sm"
                value={draft[campo] ?? ""}
                disabled={saving}
                onChange={(e) => setDraft((d) => ({ ...d, [campo]: e.target.value }))}
                data-testid={`certidao-${tipo}-${campo}`}
              />
            </div>
          ),
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={saving}
          onClick={() => onConfirmar(certidao.documento_id, tipo, patch)}
          data-testid={`certidao-${tipo}-confirmar`}
        >
          {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {semAlteracoes ? "Confirmar como está" : "Salvar e confirmar"}
        </Button>
        <span className="text-[11px] text-muted-foreground">
          {semAlteracoes
            ? "Nada alterado — confirma a leitura atual."
            : `${Object.keys(patch).length} campo(s) alterado(s).`}
        </span>
      </div>
    </div>
  );
}

export default function ImovelCertidoesCard({
  certidoes,
  showSkeleton,
  isRefreshing,
  isError,
  uploading,
  savingDocumentoId,
  errorMessage,
  onUpload,
  onConfirmar,
  hoje = new Date(),
}: ImovelCertidoesCardProps) {
  // Its own input, held by a ref — never a shared `getElementById`, same
  // reason `ImovelDocumentosCard` documents: a shared input files every
  // card's upload onto whichever one rendered it.
  const inputRef = useRef<HTMLInputElement>(null);
  const [tipoUpload, setTipoUpload] = useState<string>(TIPOS_UPLOAD[0].value);

  const porTipo = new Map((certidoes ?? []).map((c) => [c.tipo, c]));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileCheck2 className="h-4 w-4" />
          Certidões do imóvel
          {isRefreshing && (
            <Loader2
              className="h-3.5 w-3.5 animate-spin text-muted-foreground"
              data-testid="imovel-certidoes-refreshing"
            />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Select value={tipoUpload} onValueChange={setTipoUpload} disabled={uploading}>
            <SelectTrigger className="flex-1" aria-label="Tipo de certidão">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIPOS_UPLOAD.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
            data-testid="imovel-certidao-enviar"
          >
            {uploading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            Enviar
          </Button>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file, tipoUpload);
              // Reset so choosing the SAME file twice still fires a change.
              e.target.value = "";
            }}
            data-testid="imovel-certidao-input"
          />
        </div>

        {errorMessage && (
          <p className="text-xs text-destructive" data-testid="imovel-certidoes-erro-mutacao">
            {errorMessage}
          </p>
        )}

        {showSkeleton ? (
          // The testid lives on a wrapper, not on `Skeleton`: that is a
          // re-exported `@noctusai/lib/design-system` organ and this file must
          // not depend on whether it forwards arbitrary DOM props.
          <div data-testid="imovel-certidoes-skeleton">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : isError ? (
          <p className="text-xs text-destructive" data-testid="imovel-certidoes-erro">
            Não foi possível carregar as certidões do imóvel.
          </p>
        ) : (
          TIPOS_CERTIDAO.map(({ value, label }) => {
            const certidao = porTipo.get(value);
            if (!certidao) {
              return (
                <p
                  key={value}
                  className="rounded-md border border-dashed p-2.5 text-xs text-muted-foreground"
                  data-testid={`certidao-${value}-ausente`}
                >
                  {label}: nenhum documento enviado.
                  {value === "matricula"
                    ? " Envie a matrícula em Documentos do imóvel."
                    : " Envie o arquivo acima para ler número, data e resultado."}
                </p>
              );
            }
            return (
              <CertidaoEditor
                key={value}
                tipo={value}
                label={label}
                certidao={certidao}
                saving={savingDocumentoId === certidao.documento_id}
                hoje={hoje}
                onConfirmar={onConfirmar}
              />
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
