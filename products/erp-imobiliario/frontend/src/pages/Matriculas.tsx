import { useState, useCallback, useRef } from 'react';
import {
  useMatriculaExtracoes,
  useMatriculaExtracao,
  useUploadMatricula,
  useDeleteExtracao,
} from '@/hooks/useMatriculas';
import type { MatriculaExtracao } from '@/hooks/useMatriculas';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Upload,
  FileText,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Copy,
  Check,
  Trash2,
  Eye,
  FileUp,
} from 'lucide-react';
import { CardGridSkeleton } from '@/components/ui/page-skeleton';
import { formatDate } from '@/lib/utils';
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const extracoesQuery = useMatriculaExtracoes();
  const { data: extracoes = [] } = extracoesQuery;
  const showExtracoesSkeleton = extracoesQuery.isPending && !extracoesQuery.data;
  const { data: selected } = useMatriculaExtracao(selectedId || undefined);
  const uploadMutation = useUploadMatricula();
  const deleteMutation = useDeleteExtracao();

  // Auto-select newly created extraction for live status tracking
  const handleUpload = useCallback((file: File) => {
    if (file.type !== 'application/pdf') {
      toast.error('Apenas arquivos PDF são aceitos.');
      return;
    }
    uploadMutation.mutate(file, {
      onSuccess: (data) => {
        setSelectedId(data.id);
      },
    });
  }, [uploadMutation]);

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

  const handleCopy = useCallback(async () => {
    if (!selected?.texto_extraido) return;
    await navigator.clipboard.writeText(selected.texto_extraido);
    setCopied(true);
    toast.success('Texto copiado!');
    setTimeout(() => setCopied(false), 2000);
  }, [selected]);

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      if (selectedId === deleteId) setSelectedId(null);
      setDeleteId(null);
    }
  };

  const handleNewExtraction = () => {
    setSelectedId(null);
    setCopied(false);
  };

  // Determine what to show in the result area
  const isProcessing = selected && (selected.status === 'pendente' || selected.status === 'processando');
  const isComplete = selected?.status === 'concluida';
  const isError = selected?.status === 'erro';
  const showResult = selected && (isComplete || isError);

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
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="hidden"
            />
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
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
              {isComplete && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={handleCopy}>
                    {copied ? (
                      <><Check className="h-3 w-3 mr-1" />Copiado</>
                    ) : (
                      <><Copy className="h-3 w-3 mr-1" />Copiar Texto</>
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

            {isComplete && selected?.texto_extraido && (
              <div
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

      {/* History Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Histórico de Extrações</CardTitle>
        </CardHeader>
        <CardContent>
          {showExtracoesSkeleton ? (
            <CardGridSkeleton count={3} />
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
                      className={isActive ? 'bg-primary/5' : 'cursor-pointer hover:bg-muted/50'}
                      onClick={() => setSelectedId(ext.id)}
                    >
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="font-medium truncate max-w-[200px]">{ext.nome_arquivo}</span>
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
    </div>
  );
}
