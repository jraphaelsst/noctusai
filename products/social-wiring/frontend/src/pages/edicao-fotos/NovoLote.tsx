/**
 * Edição de Fotos — Novo Lote (`/edicao-fotos/novo`, `status_pagina` row
 * `edicao-fotos-novo-lote`, migration 128). Creates a batch (contract §3
 * `POST /lotes`), then feeds it photos either by upload (≤100 files, ≤25MB
 * each — limits read live off `capacidades.limites`, never hard-coded) or
 * by pulling a Vista imóvel's gallery by `codigo` (§3 `POST /lotes/{id}
 * /vista`, §10 C5), then submits it (§3 `POST /lotes/{id}/submeter`).
 *
 * 🔴 Two v1 scope calls, both flagged so a later slice knows to revisit:
 *   1. **Speed is Urgente-only this release** (brief, explicit) — Econômico
 *      always renders locked, showing `capacidades.economico_bloqueado_motivo`
 *      when present. This is a v1 UI decision layered ON TOP of the
 *      capacidades gate, not a replacement for it.
 *   2. **No `imovel` link is sent on `POST /lotes`.** The contract's body
 *      shape is `{"org_id": str, "codigo": str} | null`, but nothing in the
 *      SW frontend holds the caller's `org_id` client-side (every other
 *      hook lets the backend resolve org scope from the session) — so this
 *      page never fabricates one. The Vista SOURCE still works fully
 *      (`POST /lotes/{id}/vista` only takes `codigo`, org resolved
 *      server-side per contract §10). If a future slice needs the batch's
 *      own `imovel` link populated, that needs either an org-id-bearing
 *      capacidades field or a dedicated "pick an imóvel" lookup.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` from
 * `useCapacidades()` gates the whole form — rendering the Econômico lock
 * before capacidades resolves would show a wrong (always-locked) state.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertCircle, Lock, Upload, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

import {
  useCapacidades,
  useCriarLote,
  useLoteVista,
  useSubmeterLote,
  useUploadFotos,
  fotosPermissions,
} from "@/hooks/useEdicaoFotos";

type Fonte = "upload" | "vista";

const DEFAULT_LIMITE_FOTOS = 100;
const DEFAULT_LIMITE_BYTES = 25 * 1024 * 1024;

function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export default function NovoLote() {
  const navigate = useNavigate();
  const { capacidades, showSkeleton, error, refetch } = useCapacidades();
  const criarLote = useCriarLote();
  const uploadFotos = useUploadFotos();
  const loteVista = useLoteVista();
  const submeterLote = useSubmeterLote();

  const [nome, setNome] = useState("");
  const [fonte, setFonte] = useState<Fonte>("upload");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [codigoVista, setCodigoVista] = useState("");
  const [etapa, setEtapa] = useState<null | "criando" | "enviando_fotos" | "puxando_vista" | "submetendo">(null);

  const limiteFotos = fotosPermissions.limiteFotosPorLote(capacidades) ?? DEFAULT_LIMITE_FOTOS;
  const limiteBytes = fotosPermissions.limiteBytesPorFoto(capacidades) ?? DEFAULT_LIMITE_BYTES;
  const economicoBloqueadoMotivo = fotosPermissions.economicoBloqueadoMotivo(capacidades);

  const arquivosExcedeCount = arquivos.length > limiteFotos;
  const arquivoExcedeTamanho = arquivos.find((f) => f.size > limiteBytes) ?? null;

  const enviando = etapa !== null;
  const podeCriar = !!capacidades && fotosPermissions.podeCriarLote(capacidades);
  const modeloConfigurado = fotosPermissions.modeloConfigurado(capacidades);

  const podeSubmeter =
    podeCriar &&
    modeloConfigurado &&
    nome.trim().length > 0 &&
    (fonte === "upload"
      ? arquivos.length > 0 && !arquivosExcedeCount && !arquivoExcedeTamanho
      : codigoVista.trim().length > 0) &&
    !enviando;

  function handleArquivosChange(fileList: FileList | null) {
    if (!fileList) return;
    setArquivos((prev) => [...prev, ...Array.from(fileList)]);
  }

  function removerArquivo(index: number) {
    setArquivos((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleCriar() {
    setEtapa("criando");
    try {
      const lote = await criarLote.mutateAsync({ nome: nome.trim(), imovel: null });

      if (fonte === "upload") {
        setEtapa("enviando_fotos");
        await uploadFotos.mutateAsync({ loteId: lote.id, files: arquivos });
      } else {
        setEtapa("puxando_vista");
        await loteVista.mutateAsync({ loteId: lote.id, body: { codigo: codigoVista.trim() } });
      }

      setEtapa("submetendo");
      await submeterLote.mutateAsync(lote.id);

      toast.success("Lote criado e enviado para edição.", {
        description: `"${nome.trim()}" foi submetido — acompanhe o status na lista de lotes.`,
      });
      navigate("/edicao-fotos");
    } catch (err) {
      toast.error("Não foi possível criar o lote.", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setEtapa(null);
    }
  }

  const etapaLabel: Record<NonNullable<typeof etapa>, string> = {
    criando: "Criando lote…",
    enviando_fotos: "Enviando fotos…",
    puxando_vista: "Buscando fotos no Vista…",
    submetendo: "Enviando para edição…",
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Novo Lote</h1>
        <p className="text-sm text-muted-foreground">
          Envie fotos de um imóvel para edição por IA — por upload ou puxando de um Vista.
        </p>
      </div>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <FormSkeleton />
      ) : !podeCriar ? (
        <PermissaoNegadaState />
      ) : !modeloConfigurado ? (
        <ModeloAusenteState />
      ) : (
        <Card>
          <CardContent className="flex flex-col gap-6 p-6">
            <div className="space-y-1.5">
              <Label htmlFor="nome-lote">Nome do lote</Label>
              <Input
                id="nome-lote"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Ex.: Apto 302 — Ed. Alameda"
                disabled={enviando}
              />
            </div>

            <div className="space-y-2">
              <Label>Fonte das fotos</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={fonte === "upload" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFonte("upload")}
                  disabled={enviando}
                >
                  Upload de arquivos
                </Button>
                <Button
                  type="button"
                  variant={fonte === "vista" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFonte("vista")}
                  disabled={enviando}
                >
                  Vista (código do imóvel)
                </Button>
              </div>
            </div>

            {fonte === "upload" ? (
              <div className="space-y-2">
                <Label htmlFor="arquivos-lote">
                  Fotos (até {limiteFotos}, até {formatBytes(limiteBytes)} cada)
                </Label>
                <Input
                  id="arquivos-lote"
                  type="file"
                  accept="image/*"
                  multiple
                  disabled={enviando}
                  onChange={(e) => handleArquivosChange(e.target.files)}
                />
                {arquivos.length > 0 && (
                  <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border p-2 text-sm">
                    {arquivos.map((file, i) => (
                      <li key={`${file.name}-${i}`} className="flex items-center justify-between gap-2">
                        <span className="truncate">
                          {file.name}{" "}
                          <span
                            className={
                              file.size > limiteBytes ? "text-destructive" : "text-muted-foreground"
                            }
                          >
                            ({formatBytes(file.size)})
                          </span>
                        </span>
                        <button
                          type="button"
                          onClick={() => removerArquivo(i)}
                          disabled={enviando}
                          aria-label={`Remover ${file.name}`}
                          className="shrink-0 text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {arquivosExcedeCount && (
                  <p role="alert" className="text-xs text-destructive">
                    Limite de {limiteFotos} fotos por lote excedido ({arquivos.length} selecionadas).
                  </p>
                )}
                {arquivoExcedeTamanho && (
                  <p role="alert" className="text-xs text-destructive">
                    "{arquivoExcedeTamanho.name}" excede o limite de {formatBytes(limiteBytes)} por foto.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="codigo-vista">Código do imóvel no Vista</Label>
                <Input
                  id="codigo-vista"
                  value={codigoVista}
                  onChange={(e) => setCodigoVista(e.target.value)}
                  placeholder="Ex.: 123456"
                  disabled={enviando}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label>Velocidade</Label>
              <div className="flex flex-wrap gap-2">
                <Badge variant="default">Urgente</Badge>
                <span
                  className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground"
                  title={economicoBloqueadoMotivo ?? "Disponível em uma próxima etapa"}
                >
                  <Lock className="h-3 w-3" /> Econômico (bloqueado)
                </span>
              </div>
              {economicoBloqueadoMotivo && (
                <p className="text-xs text-muted-foreground">Motivo: {economicoBloqueadoMotivo}</p>
              )}
            </div>

            <Button onClick={handleCriar} disabled={!podeSubmeter}>
              <Upload className="h-4 w-4" />
              {enviando ? etapaLabel[etapa!] : "Criar lote"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FormSkeleton() {
  return (
    <Card data-testid="novo-lote-loading">
      <CardContent className="flex flex-col gap-4 p-6">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-9 w-32" />
      </CardContent>
    </Card>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar as permissões para criar um lote.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

function PermissaoNegadaState() {
  return (
    <Card data-testid="novo-lote-sem-permissao">
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <Lock className="h-10 w-10 text-muted-foreground" />
        <p className="font-medium">Você não tem permissão para criar lotes.</p>
      </CardContent>
    </Card>
  );
}

function ModeloAusenteState() {
  return (
    <Card data-testid="novo-lote-modelo-ausente">
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-amber-500" />
        <div>
          <p className="font-medium">Nenhum modelo de edição configurado.</p>
          <p className="text-sm text-muted-foreground">
            Peça a um administrador para escolher um modelo em{" "}
            <span className="font-medium">Edição de Fotos → Configurações</span> antes de criar um lote.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
