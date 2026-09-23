/**
 * Extrator de Matrículas — upload a matrícula PDF, get the full text back.
 *
 * Ported verbatim from `products/erp-imobiliario/frontend/src/pages/Matriculas.tsx`
 * (ERP is being retired). Every pt-BR string, every state branch and the
 * layout are unchanged — the user works this page daily and must not have to
 * relearn it. Four adaptations, all forced by this product's surface:
 *
 *   1. `Card` / `Button` / `Badge` / `AlertDialog*` come from the PRODUCT's
 *      own `@/components/ui/*` — the convention here (~450 files; zero import
 *      the seed's copies). The local copies carry decisions the seed's do
 *      not (e.g. `dialog.tsx` pins `overflow-x-hidden` as the social-wiring
 *      modal default), so seed-sourcing would silently opt this page out of
 *      them AND ship a second Radix copy in the bundle.
 *   2. `Table` is the ONE exception: it comes from the SEED
 *      (`@noctusai/seed/components/ui/table`) because this product has no
 *      local table primitive, and adding one is the fork
 *      `check_canonical_organ_consumption` blocks.
 *   3. The history skeleton is the canonical `TableSkeleton` from
 *      `@noctusai/lib/design-system` (ERP used `CardGridSkeleton`, which this
 *      product's `page-skeleton` shim does not re-export). Table-shaped
 *      placeholder for a table — no layout jump.
 *   4. The history query gained an ERROR branch. ERP has none, so a failed
 *      fetch falls through to `extracoes.length === 0` and renders "Nenhuma
 *      extração realizada" — an empty state lying over a fetch failure
 *      (`KB § PATTERNS/frontend/lying-loading-state.md`). Fixed on contact.
 *
 * F2 (contract automation) additions, all behind the SAME "concluída"
 * gate the result pane already uses:
 *   · an optional imóvel código on upload (`?extracao=` deep-links back here
 *     from `ImovelCartorioCard`'s badges, and the ONE selected extraction is
 *     auto-opened);
 *   · the matrícula's ATOS, each with its literal text — expandable, never
 *     trimmed (USER DECISION: the quote is verbatim, typos included);
 *   · the FONTES panel — heuristic título aquisitivo / ônus suggestions,
 *     clearly labelled as suggestions, with confirm / choose-other / clear.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  useMatriculaExtracoes,
  useMatriculaExtracao,
  useUploadMatricula,
  useCriarExtracaoManual,
  useDeleteExtracao,
  useRetranscreverExtracao,
  useArquivoOriginalExtracao,
  useVincularExtracaoImovel,
  readableError,
} from '@/hooks/useMatriculas';
import { ImovelCodigoPicker } from '@/components/card/ImovelCodigoPicker';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  useConfirmarDetalhesAto,
  useDefinirFontes,
  useMatriculaAtos,
  useMatriculaFontes,
} from '@/hooks/useMatriculaEstrutura';
import type { MatriculaAto } from '@/hooks/useMatriculaEstrutura';
import MatriculaAtoDetalhesEditor from '@/components/matricula/MatriculaAtoDetalhesEditor';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@noctusai/seed/components/ui/table';
import {
  Upload,
  FileText,
  FileDown,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Copy,
  Check,
  Trash2,
  Eye,
  FileUp,
  ChevronDown,
  PenLine,
  Sparkles,
  AlertTriangle,
  ExternalLink,
  RefreshCw,
  Link2,
} from 'lucide-react';
import { TableSkeleton } from '@noctusai/lib/design-system';
import { copyRichText } from '@noctusai/lib/clipboard';
import { formatDate } from '@/lib/utils';
import { apiUrl } from '@/lib/apiBase';
import { authenticatedFetch, triggerBlobDownload } from '@/lib/file-download';
import { toast } from 'sonner';

// --------------- Constants ---------------

const STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; icon: typeof Clock }> = {
  pendente: { label: 'Pendente', variant: 'outline', icon: Clock },
  processando: { label: 'Extraindo...', variant: 'secondary', icon: Loader2 },
  concluida: { label: 'Concluída', variant: 'default', icon: CheckCircle },
  erro: { label: 'Erro', variant: 'destructive', icon: XCircle },
};

// --------------- Component ---------------

export default function Matriculas() {
  const [searchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [baixandoPdf, setBaixandoPdf] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [codigoUpload, setCodigoUpload] = useState('');
  // Migration 149 — transcrição manual (typed/pasted text, no PDF, no vision
  // AI). Own state, own mutation, own toggle: additive, never touching the
  // upload flow above.
  const [manualAberto, setManualAberto] = useState(false);
  const [codigoManual, setCodigoManual] = useState('');
  const [textoManual, setTextoManual] = useState('');
  // Bug H — "Vincular a imóvel" row action (migration 149's manual-imóvel
  // paths): which unlinked row's picker dialog is open, if any. A separate
  // dialog rather than an inline field on the row — `ImovelCodigoPicker` is
  // a full search-and-register control, not a single input.
  const [vincularId, setVincularId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const extracoesQuery = useMatriculaExtracoes();
  const { data: extracoes = [] } = extracoesQuery;
  // Two signals off `data` — never `isLoading`, never a bare `isFetching`
  // (this query polls every 3s while an extraction is in flight; an
  // `isFetching` gate would unmount the table on every tick).
  const showExtracoesSkeleton = extracoesQuery.isPending && !extracoesQuery.data;
  const showExtracoesError = extracoesQuery.isError && !extracoesQuery.data;
  const { data: selected } = useMatriculaExtracao(selectedId || undefined);
  const uploadMutation = useUploadMatricula();
  const criarManualMutation = useCriarExtracaoManual();
  const deleteMutation = useDeleteExtracao();
  const retranscreverMutation = useRetranscreverExtracao();
  const arquivoOriginalMutation = useArquivoOriginalExtracao();
  const vincularMutation = useVincularExtracaoImovel();

  // 🔴 DEEP-LINK: `ImovelCartorioCard`'s título-aquisitivo/ônus badges land
  // here as `/matriculas?extracao=<id>` — auto-open that extraction once,
  // never overriding an operator's own later click.
  useEffect(() => {
    const fromQuery = searchParams.get('extracao');
    if (fromQuery && selectedId === null) {
      setSelectedId(fromQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Bug 2: `ImovelContratoCard`'s "Abrir a matrícula" action lands here as
  // `/matriculas?codigo=<codigo>` — prefill the "Imóvel (opcional)" upload
  // field with it once, same one-shot-never-override discipline as the
  // `extracao` deep-link above (never fights an operator who already typed
  // something into the field).
  useEffect(() => {
    const fromQuery = searchParams.get('codigo');
    if (fromQuery && codigoUpload === '') {
      setCodigoUpload(fromQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Auto-select newly created extraction for live status tracking
  const handleUpload = useCallback((file: File) => {
    if (file.type !== 'application/pdf') {
      toast.error('Apenas arquivos PDF são aceitos.');
      return;
    }
    const codigo = codigoUpload.trim() || undefined;
    uploadMutation.mutate(codigo ? { file, codigo } : file, {
      onSuccess: (data) => {
        setSelectedId(data.id);
      },
    });
  }, [uploadMutation, codigoUpload]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    // Reset input so the same file can be re-uploaded
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [handleUpload]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  }, [handleUpload]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleCriarManual = useCallback(() => {
    const codigo = codigoManual.trim();
    const texto = textoManual.trim();
    if (!codigo || !texto) return;
    criarManualMutation.mutate(
      { codigo, texto },
      {
        onSuccess: (data) => {
          setSelectedId(data.id);
          setCodigoManual('');
          setTextoManual('');
          setManualAberto(false);
        },
      },
    );
  }, [codigoManual, textoManual, criarManualMutation]);

  // ABNT formatting project (`projects/abnt-formatting-CONTRACT.md` § 6):
  // the seed's `copyRichText` carries bold/underline into the clipboard via
  // `ClipboardItem`; `texto_html` is `null` for rows transcribed before this
  // feature shipped (§ 4's backfill note), so those copy plain text and say
  // so — never a silent downgrade to an unformatted paste.
  const handleCopy = useCallback(async () => {
    if (!selected?.texto_extraido) return;
    try {
      if (selected.texto_html) {
        const result = await copyRichText(selected.texto_html, selected.texto_extraido);
        toast.success(result.rich ? 'Texto copiado!' : 'Texto copiado (sem formatação).');
      } else {
        await navigator.clipboard.writeText(selected.texto_extraido);
        toast.success('Texto copiado (sem formatação).');
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Não foi possível copiar o texto.');
    }
  }, [selected]);

  // `[Baixar PDF]` — GET .../pdf → blob → save with the server's own
  // filename (`Content-Disposition`), falling back to a client-derived name
  // only when that header is missing/unparseable. Raw fetch, not the JSON
  // `api` client — the response body is a PDF.
  const handleBaixarPdf = useCallback(async () => {
    if (!selected) return;
    setBaixandoPdf(true);
    try {
      const url = apiUrl(`/api/matriculas/extracoes/${selected.id}/pdf`);
      const resp = await authenticatedFetch(url);
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        throw new Error(body?.detail || 'Erro ao baixar PDF');
      }
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = /filename="?([^"]+)"?/.exec(disposition);
      const filename = match?.[1] || `${selected.nome_arquivo}_transcricao.pdf`;
      const blob = await resp.blob();
      triggerBlobDownload(blob, filename);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro ao baixar PDF';
      toast.error(msg);
    } finally {
      setBaixandoPdf(false);
    }
  }, [selected]);

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      if (selectedId === deleteId) setSelectedId(null);
      setDeleteId(null);
    }
  };

  // Re-run transcription of a concluded extraction from its RETAINED source
  // (migration 135) — never rewrites `selected`; the backend supersedes and
  // this selects the NEW row so its progress tracks live, same UX as a
  // fresh upload's `handleUpload` onSuccess.
  const handleRetranscrever = useCallback((id: string) => {
    retranscreverMutation.mutate(id, {
      onSuccess: (data) => setSelectedId(data.id),
    });
  }, [retranscreverMutation]);

  // Open the SOURCE PDF (linked or standalone-retained) in a new tab so a
  // human can audit the transcription against it — the signed URL is
  // short-TTL and minted per click, never stored.
  const handleVerOriginal = useCallback((id: string) => {
    arquivoOriginalMutation.mutate(id, {
      onSuccess: (data) => window.open(data.url, '_blank', 'noopener,noreferrer'),
    });
  }, [arquivoOriginalMutation]);

  // A row can be re-transcribed only when it has a retained source
  // (linked OR standalone, migration 135) AND has not already been
  // superseded by a newer transcription.
  const podeRetranscrever = useCallback(
    (ext: { imovel_documento_id: string | null; arquivo_origem_id: string | null; substituida_por: string | null }) =>
      !ext.substituida_por && (!!ext.imovel_documento_id || !!ext.arquivo_origem_id),
    [],
  );
  const temFonteRetida = useCallback(
    (ext: { imovel_documento_id: string | null; arquivo_origem_id: string | null }) =>
      !!ext.imovel_documento_id || !!ext.arquivo_origem_id,
    [],
  );

  const handleNewExtraction = () => {
    setSelectedId(null);
    setCopied(false);
  };

  // Determine what to show in the result area
  const isProcessing = selected && (selected.status === 'pendente' || selected.status === 'processando');
  const isComplete = selected?.status === 'concluida';
  const isError = selected?.status === 'erro';

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Extrator de Matrículas</h1>
        <p className="text-muted-foreground">
          Envie o PDF da matrícula e extraia o texto completo com IA
        </p>
      </div>

      {/* Upload + Result Area */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left: Upload Zone */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Upload</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="mb-3 space-y-1">
              <label htmlFor="matricula-codigo" className="text-xs font-medium text-muted-foreground">
                Imóvel (opcional)
              </label>
              <Input
                id="matricula-codigo"
                value={codigoUpload}
                onChange={(e) => setCodigoUpload(e.target.value)}
                placeholder="Ex.: ONE9001"
                disabled={uploadMutation.isPending}
                data-testid="matricula-codigo-input"
              />
              <p className="text-xs text-muted-foreground">
                Vincula o PDF a este imóvel — fica salvo como a matrícula dele e
                aparece no card de cartório.
              </p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="hidden"
              data-testid="matricula-file-input"
            />
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              data-testid="matricula-dropzone"
              className={`
                border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
                ${isDragOver
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50'
                }
                ${uploadMutation.isPending ? 'pointer-events-none opacity-50' : ''}
              `}
            >
              {uploadMutation.isPending ? (
                <>
                  <Loader2 className="h-12 w-12 mx-auto mb-4 text-primary animate-spin" />
                  <p className="text-lg font-medium">Enviando...</p>
                </>
              ) : (
                <>
                  <FileUp className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                  <p className="text-lg font-medium">
                    Arraste o PDF aqui ou clique para selecionar
                  </p>
                  <p className="text-sm text-muted-foreground mt-2">
                    Apenas arquivos PDF, até 20MB
                  </p>
                </>
              )}
            </div>

            {/* Processing indicator */}
            {isProcessing && (
              <div className="mt-4 flex items-center gap-3 p-4 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-900">
                <Loader2 className="h-5 w-5 text-blue-500 animate-spin shrink-0" />
                <div>
                  <p className="font-medium text-sm">Extraindo texto...</p>
                  <p className="text-xs text-muted-foreground">
                    {selected.nome_arquivo}
                    {selected.num_paginas ? ` — ${selected.num_paginas} página${selected.num_paginas > 1 ? 's' : ''}` : ''}
                  </p>
                </div>
              </div>
            )}

            {/* Error display */}
            {isError && (
              <div className="mt-4 p-4 bg-red-50 dark:bg-red-950/20 rounded-lg border border-red-200 dark:border-red-900">
                <div className="flex items-center gap-2 mb-1">
                  <XCircle className="h-4 w-4 text-red-500" />
                  <p className="font-medium text-sm text-red-700 dark:text-red-400">Erro na extração</p>
                </div>
                <p className="text-xs text-muted-foreground">{selected.erro_mensagem}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Right: Result Area */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Texto Extraído</CardTitle>
              {isComplete && selected && (
                <div className="flex gap-2">
                  {temFonteRetida(selected) && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleVerOriginal(selected.id)}
                      disabled={arquivoOriginalMutation.isPending}
                      aria-label="Ver PDF original"
                      title="Abre o PDF de origem para conferir o texto contra o documento"
                    >
                      {arquivoOriginalMutation.isPending ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : (
                        <ExternalLink className="h-3 w-3 mr-1" />
                      )}
                      Ver original
                    </Button>
                  )}
                  {podeRetranscrever(selected) && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleRetranscrever(selected.id)}
                      disabled={retranscreverMutation.isPending}
                      aria-label="Retranscrever a partir do PDF original"
                      title="Gera uma nova transcrição a partir do PDF original guardado"
                    >
                      {retranscreverMutation.isPending ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3 mr-1" />
                      )}
                      Retranscrever
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleBaixarPdf}
                    disabled={baixandoPdf || !selected?.texto_extraido}
                    aria-label="Baixar PDF da transcrição"
                  >
                    {baixandoPdf ? (
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    ) : (
                      <FileDown className="h-3 w-3 mr-1" />
                    )}
                    Baixar PDF
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCopy}
                    disabled={!selected?.texto_extraido}
                    aria-label="Copiar transcrição"
                  >
                    {copied ? (
                      <><Check className="h-3 w-3 mr-1" />Copiado</>
                    ) : (
                      <><Copy className="h-3 w-3 mr-1" />Copiar</>
                    )}
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleNewExtraction}>
                    <Upload className="h-3 w-3 mr-1" />Nova Extração
                  </Button>
                </div>
              )}
            </div>
            {isComplete && selected && (
              <p className="text-sm text-muted-foreground">
                {selected.nome_arquivo} — {selected.num_paginas} página{(selected.num_paginas || 0) > 1 ? 's' : ''}
              </p>
            )}
          </CardHeader>
          <CardContent>
            {!selected && (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <FileText className="h-16 w-16 mb-4 opacity-30" />
                <p>Envie um PDF ou selecione uma extração do histórico</p>
              </div>
            )}

            {isProcessing && (
              <div className="flex flex-col items-center justify-center py-16">
                <Loader2 className="h-10 w-10 text-primary animate-spin mb-4" />
                <p className="text-muted-foreground">Processando páginas com IA...</p>
                <p className="text-xs text-muted-foreground mt-1">Isso pode levar alguns segundos por página</p>
              </div>
            )}

            {isError && (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <XCircle className="h-10 w-10 text-red-400 mb-4" />
                <p>Não foi possível extrair o texto</p>
              </div>
            )}

            {isComplete && selected && selected.possui_marcacao_bruta && (
              <div
                data-testid="matricula-marcacao-bruta-aviso"
                className="mb-4 flex items-start gap-2 p-4 bg-amber-50 dark:bg-amber-950/20 rounded-lg border border-amber-200 dark:border-amber-900"
              >
                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500 mt-0.5 shrink-0" />
                <div>
                  <p className="font-medium text-sm text-amber-800 dark:text-amber-400">
                    Este texto contém marcação de formatação bruta
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Trechos aparecem com <code>**</code> ou <code>&lt;u&gt;</code> literais em vez de
                    negrito/sublinhado. Não cite este texto em um contrato — o gerador recusa
                    fazê-lo automaticamente. {temFonteRetida(selected)
                      ? 'Use "Retranscrever" para corrigir.'
                      : 'Esta transcrição não guardou o PDF original; envie o arquivo novamente.'}
                  </p>
                </div>
              </div>
            )}

            {isComplete && selected?.substituida_por && (
              <div
                data-testid="matricula-substituida-aviso"
                className="mb-4 p-3 bg-muted/50 rounded-lg text-sm text-muted-foreground"
              >
                Esta versão foi substituída por uma retranscrição mais recente do mesmo documento.
              </div>
            )}

            {isComplete && selected?.texto_extraido && (
              <div
                data-testid="matricula-texto-extraido"
                className="bg-muted/30 rounded-lg p-4 max-h-[60vh] overflow-y-auto font-mono text-sm leading-relaxed whitespace-pre-wrap select-all"
              >
                {selected.texto_extraido}
              </div>
            )}

            {isComplete && !selected?.texto_extraido && (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <FileText className="h-10 w-10 opacity-30 mb-4" />
                <p>Nenhum texto extraído</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Nova transcrição manual (migration 149) — a matrícula typed/pasted
          straight in, no PDF, no vision AI. Feeds the SAME segmenter an
          uploaded PDF's text goes through, so atos/título/ônus selection
          work identically — the only way today to test the contract
          generator end to end with no AI transcription in the loop. */}
      <Collapsible open={manualAberto} onOpenChange={setManualAberto}>
        <Card>
          <CollapsibleTrigger asChild>
            <CardHeader
              className="cursor-pointer select-none"
              data-testid="matricula-manual-toggle"
            >
              <CardTitle className="flex items-center gap-2 text-base">
                <PenLine className="h-4 w-4" />
                Nova transcrição manual
                <ChevronDown
                  className={`ml-auto h-4 w-4 transition-transform ${manualAberto ? 'rotate-180' : ''}`}
                />
              </CardTitle>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Cole ou digite o texto da matrícula — sem PDF, sem IA. Útil para
                testar a geração do contrato com dados 100% manuais.
              </p>
              <div className="space-y-1">
                <label htmlFor="matricula-manual-codigo" className="text-xs font-medium text-muted-foreground">
                  Imóvel
                </label>
                <Input
                  id="matricula-manual-codigo"
                  value={codigoManual}
                  onChange={(e) => setCodigoManual(e.target.value)}
                  placeholder="Ex.: ONE9001"
                  disabled={criarManualMutation.isPending}
                  data-testid="matricula-manual-codigo-input"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="matricula-manual-texto" className="text-xs font-medium text-muted-foreground">
                  Texto da matrícula
                </label>
                <Textarea
                  id="matricula-manual-texto"
                  rows={10}
                  value={textoManual}
                  onChange={(e) => setTextoManual(e.target.value)}
                  placeholder="Cole aqui o texto completo da matrícula..."
                  disabled={criarManualMutation.isPending}
                  data-testid="matricula-manual-texto-input"
                />
              </div>
              <Button
                onClick={handleCriarManual}
                disabled={
                  criarManualMutation.isPending || !codigoManual.trim() || !textoManual.trim()
                }
                data-testid="matricula-manual-criar"
              >
                {criarManualMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Criar transcrição manual
              </Button>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      {/* Atos + Fontes — only once the transcription is usable for them. */}
      {isComplete && selected && <MatriculaAtosEFontes extracaoId={selected.id} />}

      {/* History Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Histórico de Extrações</CardTitle>
        </CardHeader>
        <CardContent>
          {showExtracoesSkeleton ? (
            <TableSkeleton rows={3} columns={5} />
          ) : showExtracoesError ? (
            <div
              className="py-8 text-center text-muted-foreground"
              data-testid="matriculas-historico-error"
              role="alert"
            >
              <XCircle className="h-10 w-10 mx-auto mb-3 text-red-400" />
              <p>Não foi possível carregar o histórico</p>
              <Button
                size="sm"
                variant="outline"
                className="mt-3"
                onClick={() => extracoesQuery.refetch()}
              >
                Tentar novamente
              </Button>
            </div>
          ) : extracoes.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              <FileText className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p>Nenhuma extração realizada</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Arquivo</TableHead>
                  <TableHead className="w-24">Páginas</TableHead>
                  <TableHead className="w-32">Status</TableHead>
                  <TableHead className="w-36">Data</TableHead>
                  <TableHead className="w-20">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {extracoes.map((ext) => {
                  const status = STATUS_CONFIG[ext.status] || STATUS_CONFIG.pendente;
                  const StatusIcon = status.icon;
                  const isActive = selectedId === ext.id;

                  return (
                    <TableRow
                      key={ext.id}
                      data-testid={`matricula-row-${ext.id}`}
                      className={isActive ? 'bg-primary/5' : 'cursor-pointer hover:bg-muted/50'}
                      onClick={() => setSelectedId(ext.id)}
                    >
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="font-medium truncate max-w-[200px]">{ext.nome_arquivo}</span>
                          {ext.possui_marcacao_bruta && (
                            <AlertTriangle
                              className="h-3.5 w-3.5 text-amber-600 dark:text-amber-500 shrink-0"
                              aria-label="Contém marcação de formatação bruta"
                            />
                          )}
                          {ext.substituida_por && (
                            <Badge variant="outline" className="text-[10px] shrink-0">
                              substituída
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {ext.num_paginas ?? '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={status.variant} className="gap-1">
                          <StatusIcon className={`h-3 w-3 ${ext.status === 'processando' ? 'animate-spin' : ''}`} />
                          {status.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {formatDate(ext.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setSelectedId(ext.id)}
                            title="Visualizar"
                          >
                            <Eye className="h-3 w-3" />
                          </Button>
                          {ext.status === 'erro' && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => fileInputRef.current?.click()}
                              title="Reenviar"
                            >
                              <Upload className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          )}
                          {ext.status === 'concluida' && temFonteRetida(ext) && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleVerOriginal(ext.id)}
                              disabled={arquivoOriginalMutation.isPending}
                              title="Ver PDF original"
                            >
                              <ExternalLink className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          )}
                          {ext.status === 'concluida' && podeRetranscrever(ext) && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleRetranscrever(ext.id)}
                              disabled={retranscreverMutation.isPending}
                              title="Retranscrever a partir do original"
                            >
                              <RefreshCw className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          )}
                          {/* Bug H — the only way, besides the contract
                              panel's own secondary section, to attach an
                              EXISTING unlinked transcription to an imóvel
                              after the fact. Only rows with no codigo at
                              all offer it — a linked row already has its
                              imóvel. */}
                          {!ext.codigo && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setVincularId(ext.id)}
                              title="Vincular a imóvel"
                              data-testid={`matricula-row-${ext.id}-vincular`}
                            >
                              <Link2 className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDeleteId(ext.id)}
                            title="Excluir"
                          >
                            <Trash2 className="h-3 w-3 text-muted-foreground" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Extração</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta extração? O texto extraído será perdido.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bug H — "Vincular a imóvel" row action. `ImovelCodigoPicker`'s value
          is always null here: this dialog exists to CHOOSE a target, not to
          show/clear an already-chosen one. */}
      <Dialog open={!!vincularId} onOpenChange={(open) => !open && setVincularId(null)}>
        <DialogContent data-testid="matricula-vincular-dialog">
          <DialogHeader>
            <DialogTitle>Vincular a um imóvel</DialogTitle>
          </DialogHeader>
          <ImovelCodigoPicker
            value={null}
            disabled={vincularMutation.isPending}
            onChange={(codigo) => {
              if (!vincularId || !codigo) return;
              vincularMutation.mutate(
                { extracaoId: vincularId, codigo },
                { onSuccess: () => setVincularId(null) },
              );
            }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Atos + Fontes (F2 — contract automation) ──────────────────────────────
//
// 🔴 USER DECISION: THE TEXT IS LITERAL, TYPOS INCLUDED. Every act body below
// renders `white-space: pre-wrap` and is never trimmed/normalised — the
// operator SELECTS acts (here) and QUOTES them into a contract
// (`MatriculaAtosSelector`, on the card); nobody edits their wording.

const KIND_LABEL: Record<MatriculaAto['kind'], string> = {
  abertura: 'Abertura',
  R: 'Registro',
  AV: 'Averbação',
};

function rotuloDoAto(ato: Pick<MatriculaAto, 'kind' | 'numero' | 'rotulo'>): string {
  if (ato.kind === 'abertura') return 'Abertura da matrícula';
  const numero = ato.numero != null ? `-${ato.numero}` : '';
  return `${ato.kind}${numero} · ${ato.rotulo || KIND_LABEL[ato.kind]}`;
}

function MatriculaAtosEFontes({ extracaoId }: { extracaoId: string }) {
  const atosQuery = useMatriculaAtos(extracaoId);
  const fontesQuery = useMatriculaFontes(extracaoId);
  const definirFontes = useDefinirFontes(extracaoId);
  // One mutation for every act on the page; `variables.atoId` is what tells
  // the editors WHICH of them is saving, so a confirmation on R-3 does not
  // spin the button on R-1.
  const confirmarDetalhes = useConfirmarDetalhesAto(extracaoId);

  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const [outroTitulo, setOutroTitulo] = useState('');
  const [onusDraft, setOnusDraft] = useState<string[]>([]);

  const atos = atosQuery.data?.atos ?? [];
  // Two signals off `data`, never `isLoading` — same discipline as the
  // history table above.
  const showAtosSkeleton = atosQuery.isPending && !atosQuery.data;
  const showAtosError = atosQuery.isError && !atosQuery.data;

  const fontes = fontesQuery.data;
  const showFontesSkeleton = fontesQuery.isPending && !fontesQuery.data;
  const showFontesError = fontesQuery.isError && !fontesQuery.data;

  // Seed the ônus draft from the CONFIRMED pointer, keyed on the ids
  // themselves (not object identity) — an unrelated refetch must not stomp
  // an edit in progress, same discipline `ImovelCartorioCard.toDraft` uses.
  const onusConfirmadoIds = (fontes?.onus?.atos ?? []).map((a) => a.ato_id).join(',');
  useEffect(() => {
    setOnusDraft(onusConfirmadoIds ? onusConfirmadoIds.split(',') : []);
  }, [onusConfirmadoIds]);

  const atosQuotaveis = useMemo(() => atos.filter((a) => a.kind !== 'abertura'), [atos]);

  function alternarExpandido(atoId: string) {
    setExpandidos((atual) => {
      const copia = new Set(atual);
      if (copia.has(atoId)) copia.delete(atoId);
      else copia.add(atoId);
      return copia;
    });
  }

  function alternarOnusDraft(atoId: string) {
    setOnusDraft((atual) =>
      atual.includes(atoId) ? atual.filter((id) => id !== atoId) : [...atual, atoId],
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Atos e Fontes</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        {/* ─── Atos catalog ────────────────────────────────────────────── */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Atos da matrícula</h3>
          {showAtosSkeleton && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Carregando atos...
            </p>
          )}
          {showAtosError && (
            <p className="text-sm text-destructive" data-testid="matriculas-atos-erro">
              Não foi possível carregar os atos.
            </p>
          )}
          {!showAtosSkeleton && !showAtosError && atos.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum ato segmentado ainda.</p>
          )}
          {atos.length > 0 && (
            <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto" data-testid="matriculas-atos-lista">
              {atos.map((ato) => {
                const expandido = expandidos.has(ato.id);
                return (
                  <li
                    key={ato.id}
                    className="rounded-md border p-2"
                    data-testid={`matriculas-ato-${ato.id}`}
                  >
                    <Collapsible open={expandido} onOpenChange={() => alternarExpandido(ato.id)}>
                      <CollapsibleTrigger asChild>
                        <button
                          type="button"
                          className="flex w-full items-center gap-1.5 text-left text-sm font-medium"
                          data-testid={`matriculas-ato-toggle-${ato.id}`}
                        >
                          <ChevronDown
                            className={`h-3.5 w-3.5 shrink-0 transition-transform ${expandido ? 'rotate-180' : ''}`}
                          />
                          {rotuloDoAto(ato)}
                        </button>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <p
                          className="mt-2 whitespace-pre-wrap rounded bg-muted/30 p-2 font-mono text-xs leading-relaxed"
                          data-testid={`matriculas-ato-texto-${ato.id}`}
                        >
                          {ato.texto}
                        </p>
                        {/* What we READ out of that text, for the operator to
                            confirm or fix (migration 115). Under the literal
                            text on purpose: the reading is a claim ABOUT the
                            text above it, and the two must be comparable
                            without scrolling between screens. */}
                        <div className="mt-2">
                          <MatriculaAtoDetalhesEditor
                            ato={ato}
                            detalhes={ato.detalhes}
                            saving={
                              confirmarDetalhes.isPending &&
                              confirmarDetalhes.variables?.atoId === ato.id
                            }
                            errorMessage={
                              confirmarDetalhes.isError &&
                              confirmarDetalhes.variables?.atoId === ato.id
                                ? readableError(confirmarDetalhes.error as Error)
                                : null
                            }
                            onConfirmar={(patch) =>
                              confirmarDetalhes.mutate({ atoId: ato.id, patch })
                            }
                          />
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* ─── Fontes ──────────────────────────────────────────────────── */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold">Fontes</h3>
          {showFontesSkeleton && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Carregando fontes...
            </p>
          )}
          {showFontesError && (
            <p className="text-sm text-destructive" data-testid="matriculas-fontes-erro">
              Não foi possível carregar as fontes.
            </p>
          )}

          {fontes && (
            <>
              {/* Título aquisitivo */}
              <div className="space-y-1.5 rounded-md border p-3" data-testid="matriculas-fonte-titulo">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Título aquisitivo
                </p>
                {fontes.titulo_aquisitivo ? (
                  <div className="space-y-1 text-sm">
                    <Badge
                      variant={fontes.titulo_aquisitivo.origem === 'sugerido' ? 'secondary' : 'outline'}
                      className="gap-1"
                    >
                      {fontes.titulo_aquisitivo.origem === 'sugerido' && <Sparkles className="h-3 w-3" />}
                      {fontes.titulo_aquisitivo.origem === 'sugerido'
                        ? 'Sugestão confirmada'
                        : 'Escolhido manualmente'}
                    </Badge>
                    <p className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                      {fontes.titulo_aquisitivo.texto}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {fontes.titulo_aquisitivo.confirmado_por?.nome ?? '—'}
                      {fontes.titulo_aquisitivo.confirmado_em
                        ? ` em ${new Date(fontes.titulo_aquisitivo.confirmado_em).toLocaleString('pt-BR')}`
                        : ''}
                    </p>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => definirFontes.mutate({ titulo_aquisitivo_ato_id: null })}
                      disabled={definirFontes.isPending}
                      data-testid="matriculas-titulo-limpar"
                    >
                      Limpar
                    </Button>
                  </div>
                ) : fontes.sugestoes.titulo_aquisitivo ? (
                  <div className="space-y-1.5 text-sm">
                    <p className="flex items-center gap-1.5 text-xs">
                      <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                      Sugestão: {fontes.sugestoes.titulo_aquisitivo.rotulo} (
                      {fontes.sugestoes.titulo_aquisitivo.termo})
                    </p>
                    <Button
                      size="sm"
                      onClick={() =>
                        definirFontes.mutate({
                          titulo_aquisitivo_ato_id: fontes.sugestoes.titulo_aquisitivo!.ato_id,
                        })
                      }
                      disabled={definirFontes.isPending}
                      data-testid="matriculas-titulo-confirmar-sugestao"
                    >
                      Confirmar sugestão
                    </Button>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Nenhuma sugestão encontrada.</p>
                )}

                <div className="space-y-1 pt-1.5">
                  <label className="text-xs text-muted-foreground" htmlFor="titulo-outro-ato">
                    Escolher outro ato
                  </label>
                  <Select
                    value={outroTitulo}
                    onValueChange={(v) => {
                      setOutroTitulo(v);
                      definirFontes.mutate({ titulo_aquisitivo_ato_id: v });
                    }}
                  >
                    <SelectTrigger id="titulo-outro-ato" className="h-8 text-sm" data-testid="matriculas-titulo-outro-ato">
                      <SelectValue placeholder="Selecione um ato..." />
                    </SelectTrigger>
                    <SelectContent>
                      {atosQuotaveis.map((ato) => (
                        <SelectItem key={ato.id} value={ato.id}>
                          {rotuloDoAto(ato)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Ônus */}
              <div className="space-y-1.5 rounded-md border p-3" data-testid="matriculas-fonte-onus">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Ônus</p>

                {fontes.onus ? (
                  <div className="space-y-1 text-sm">
                    <Badge
                      variant={fontes.onus.origem === 'sugerido' ? 'secondary' : 'outline'}
                      className="gap-1"
                    >
                      {fontes.onus.origem === 'sugerido' && <Sparkles className="h-3 w-3" />}
                      {fontes.onus.atos.length} ato{fontes.onus.atos.length > 1 ? 's' : ''}
                      {fontes.onus.origem === 'sugerido' ? ' · sugestão confirmada' : ' · manual'}
                    </Badge>
                    <p className="text-xs text-muted-foreground">
                      {fontes.onus.confirmado_por?.nome ?? '—'}
                      {fontes.onus.confirmado_em
                        ? ` em ${new Date(fontes.onus.confirmado_em).toLocaleString('pt-BR')}`
                        : ''}
                    </p>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => definirFontes.mutate({ onus_ato_ids: [] })}
                      disabled={definirFontes.isPending}
                      data-testid="matriculas-onus-limpar"
                    >
                      Limpar
                    </Button>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Nenhum ônus confirmado.</p>
                )}

                {fontes.sugestoes.onus.length > 0 && (
                  <div className="space-y-1 rounded bg-muted/30 p-2">
                    <p className="flex items-center gap-1.5 text-xs">
                      <Sparkles className="h-3.5 w-3.5 text-amber-500" /> Sugestões
                    </p>
                    <ul className="space-y-0.5 text-xs">
                      {fontes.sugestoes.onus.map((o) => (
                        <li
                          key={o.ato_id}
                          className={o.sugerido ? '' : 'text-muted-foreground line-through'}
                        >
                          {o.rotulo} ({o.tipo})
                          {!o.sugerido && ' · cancelado'}
                        </li>
                      ))}
                    </ul>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        definirFontes.mutate({
                          onus_ato_ids: fontes.sugestoes.onus.filter((o) => o.sugerido).map((o) => o.ato_id),
                        })
                      }
                      disabled={definirFontes.isPending || fontes.sugestoes.onus.every((o) => !o.sugerido)}
                      data-testid="matriculas-onus-usar-sugestoes"
                    >
                      Usar sugestões
                    </Button>
                  </div>
                )}

                <div className="space-y-1 pt-1.5">
                  <p className="text-xs text-muted-foreground">Escolher outros atos</p>
                  <ul className="max-h-40 space-y-1 overflow-y-auto">
                    {atosQuotaveis.map((ato) => (
                      <li key={ato.id} className="flex items-center gap-2 text-xs">
                        <Checkbox
                          checked={onusDraft.includes(ato.id)}
                          onCheckedChange={() => alternarOnusDraft(ato.id)}
                          data-testid={`matriculas-onus-checkbox-${ato.id}`}
                        />
                        {rotuloDoAto(ato)}
                      </li>
                    ))}
                  </ul>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => definirFontes.mutate({ onus_ato_ids: onusDraft })}
                    disabled={definirFontes.isPending}
                    data-testid="matriculas-onus-salvar"
                  >
                    Salvar seleção de ônus
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
