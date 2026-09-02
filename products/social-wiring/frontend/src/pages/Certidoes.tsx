/**
 * Certidões Negativas — automated certificate issuance with AI analysis.
 *
 * Ported from `erp-imobiliario/frontend/src/pages/Certidoes.tsx` as ERP is
 * retired. The workflow is deliberately identical, down to the pt-BR copy:
 * the same person runs this page every day and the port must not re-teach it.
 *
 * The surface has four live sub-systems, all driven by the polling contract in
 * `@/hooks/useCertidoes`:
 *
 *   1. Per-consulta progress — a two-segment bar (success / error) that fills
 *      as each tribunal scrape lands.
 *   2. TJSP queue + cooldown — TJSP allows one request per 30 minutes, so
 *      certificates queue with a visible position and the cooldown runs a
 *      local 1s countdown between the 15s server polls (a bar that only moved
 *      every 15 seconds reads as frozen).
 *   3. Recovery — cancel an in-flight run, reprocess the failed certificates,
 *      or hand-upload a PDF for one that will never succeed automatically.
 *   4. Retrieval — per-file download through the backend CORS proxy, or the
 *      whole consulta as a ZIP.
 *
 * Import sourcing, which differs from the ERP original in two places:
 *   - `Table` comes from `@noctusai/seed/components/ui/table`. social-wiring
 *     had no local table; the primitive was promoted to the seed for this port
 *     precisely so neither consuming product forks one.
 *   - Every OTHER primitive comes from this product's `@/components/ui/*`,
 *     NOT from the seed. social-wiring's local copies carry product design-
 *     system decisions the seed copies do not — its `dialog.tsx` sets
 *     `overflow-x-hidden` as a deliberate default, for one — so importing the
 *     seed variants here would silently opt this page out of them and leave it
 *     looking subtly unlike every other page in the product.
 */
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertCircle,
  Building2,
  CheckCircle,
  ChevronDown,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileCheck,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Timer,
  Trash2,
  Upload,
  User,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { TableSkeleton } from "@noctusai/lib/design-system";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@noctusai/seed/components/ui/table";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCancelarProcessamento,
  useCertidaoConsulta,
  useCertidaoConsultas,
  useCreateConsulta,
  useDeleteConsulta,
  useReprocessarConsulta,
  useTjspFila,
} from "@/hooks/useCertidoes";
import type { CertidaoConsulta, ConsultaCreateData } from "@/hooks/useCertidoes";
import { api } from "@/lib/api";
import { apiUrl } from "@/lib/apiBase";
import { authenticatedFetch, downloadFile, triggerBlobDownload } from "@/lib/file-download";
import { formatDate } from "@/lib/utils";

// --------------- Constants ---------------

const CONSULTA_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  pendente: { label: "Pendente", variant: "outline" },
  processando: { label: "Processando", variant: "secondary" },
  concluida: { label: "Concluída", variant: "default" },
  erro: { label: "Erro", variant: "destructive" },
};

const RESULTADO_STATUS_ICON: Record<
  string,
  { icon: typeof Clock; color: string; label?: string }
> = {
  pendente: { icon: Clock, color: "text-muted-foreground" },
  processando: { icon: Loader2, color: "text-blue-500" },
  // `na_fila` is the TJSP rate-limit queue, not generic pending — the label
  // says so, otherwise a queued certificate looks indistinguishable from a
  // stalled one.
  na_fila: { icon: Clock, color: "text-muted-foreground", label: "Pendente (TJSP)" },
  sucesso: { icon: CheckCircle, color: "text-green-500" },
  erro: { icon: XCircle, color: "text-red-500" },
};

// --------------- Form Schema ---------------

const consultaSchema = z.object({
  tipo_documento: z.enum(["cpf", "cnpj"]),
  documento: z.string().min(11, "Documento é obrigatório").max(18),
  nome: z.string().min(2, "Nome é obrigatório").max(200),
  data_nascimento: z.string().optional(),
  // `''` is the Select's cleared value — allowed through validation and
  // normalised to `undefined` in `handleCreate`.
  genero: z.enum(["M", "F"]).optional().or(z.literal("")),
  rg: z.string().optional(),
  nome_mae: z.string().optional(),
  nome_pai: z.string().optional(),
});

type ConsultaFormData = z.infer<typeof consultaSchema>;

// --------------- Component ---------------

export default function Certidoes() {
  const [busca, setBusca] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("todos");
  const [dialogAberto, setDialogAberto] = useState(false);
  const [detalheId, setDetalheId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [expandedAnalise, setExpandedAnalise] = useState<string | null>(null);

  const consultasQuery = useCertidaoConsultas({
    busca: busca || undefined,
    status: filtroStatus !== "todos" ? filtroStatus : undefined,
  });
  // Memoised, not a bare `?? []`: the fallback allocates a new array on every
  // render, which would make the `summary` memo below recompute every render
  // (it is keyed on this) — ERP carries that bug and eslint flags it.
  const consultas = useMemo(() => consultasQuery.data ?? [], [consultasQuery.data]);

  // Two loading signals off `data`, never `isLoading` and never a bare
  // `isFetching` — KB § PATTERNS/frontend/lying-loading-state.md. The skeleton
  // shows only when there is genuinely nothing to show; a refetch (the 3s
  // progress poll, or a filter change) shows the existing table plus a
  // discreet spinner. Gating the table on `isFetching` would unmount it every
  // three seconds while a consulta processes.
  const showConsultasSkeleton = consultasQuery.isPending && !consultasQuery.data;
  const isRefreshingConsultas = consultasQuery.isFetching && !!consultasQuery.data;

  const detalheQuery = useCertidaoConsulta(detalheId || undefined);
  const detalhe = detalheQuery.data;
  const showDetalheSkeleton = !!detalheId && detalheQuery.isPending && !detalheQuery.data;

  const { data: tjspFila } = useTjspFila();
  const createMutation = useCreateConsulta();
  const reprocessarMutation = useReprocessarConsulta();
  const deleteMutation = useDeleteConsulta();
  const cancelarMutation = useCancelarProcessamento();

  // Live countdown for TJSP cooldown. The server is polled every 15s; without
  // a local 1s tick between polls the bar sits still long enough to read as
  // broken. Re-seeded (not accumulated) from each server value, so the local
  // clock can never drift away from the truth.
  const [cooldownSegs, setCooldownSegs] = useState(0);
  useEffect(() => {
    if (!tjspFila?.cooldown?.ativo || !tjspFila.cooldown.segundos_restantes) {
      setCooldownSegs(0);
      return;
    }
    setCooldownSegs(tjspFila.cooldown.segundos_restantes);
    const interval = setInterval(() => {
      setCooldownSegs((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [tjspFila?.cooldown?.ativo, tjspFila?.cooldown?.segundos_restantes]);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<ConsultaFormData>({
    resolver: zodResolver(consultaSchema),
    defaultValues: {
      tipo_documento: "cpf",
      documento: "",
      nome: "",
      data_nascimento: "",
      genero: "",
      rg: "",
      nome_mae: "",
      nome_pai: "",
    },
  });

  const tipoDocumento = watch("tipo_documento");

  const summary = useMemo(() => {
    const pendentes = consultas.filter(
      (c) => c.status === "pendente" || c.status === "processando",
    ).length;
    const concluidas = consultas.filter((c) => c.status === "concluida").length;
    const erros = consultas.filter((c) => c.status === "erro").length;
    return { pendentes, concluidas, erros, total: consultas.length };
  }, [consultas]);

  const handleCreate = (data: ConsultaFormData) => {
    // Built field-by-field rather than `{...data, overrides}` (ERP's shape) for
    // two reasons: a spread ships every form-only field to the API forever
    // after, and the explicit annotation is what makes the compiler check the
    // form type against the wire type at all. `genero` is a plain truthiness
    // test — `""` is falsy, so the extra `!== ""` ERP carries is dead code the
    // compiler rejects, and truthiness stays correct whether zod infers the
    // cleared value as `""` or `undefined`.
    const payload: ConsultaCreateData = {
      tipo_documento: data.tipo_documento,
      documento: data.documento,
      nome: data.nome,
      genero: data.genero || undefined,
      data_nascimento: data.data_nascimento || undefined,
      rg: data.rg || undefined,
      nome_mae: data.nome_mae || undefined,
      nome_pai: data.nome_pai || undefined,
    };
    createMutation.mutate(payload, {
      onSuccess: () => {
        setDialogAberto(false);
        reset();
      },
    });
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteMutation.mutate(deleteId);
      setDeleteId(null);
    }
  };

  const handleReprocessar = (id: string) => {
    reprocessarMutation.mutate(id);
  };

  const [downloadingZip, setDownloadingZip] = useState<string | null>(null);

  const handleDownloadAll = async (consulta: CertidaoConsulta) => {
    setDownloadingZip(consulta.id);
    try {
      // Raw fetch, not the `api` client: the response is a ZIP, and the client
      // parses every response as JSON.
      const url = apiUrl(`/api/certidoes/consultas/${consulta.id}/download-zip`);
      const resp = await authenticatedFetch(url);
      if (!resp.ok) {
        const err = await resp.json().catch(() => null);
        throw new Error(err?.detail || "Erro ao baixar certidões");
      }
      const blob = await resp.blob();
      const zipName = `certidoes_${consulta.nome.replace(/\s+/g, "_").slice(0, 50)}_${consulta.documento}.zip`;
      triggerBlobDownload(blob, zipName);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erro ao baixar certidões";
      toast.error(msg);
    } finally {
      setDownloadingZip(null);
    }
  };

  const handleDownload = (url: string, filename: string) => downloadFile(url, filename);

  const uploadInputRef = useRef<HTMLInputElement>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const handleUploadClick = (resultadoId: string) => {
    setUploadingId(resultadoId);
    uploadInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset immediately so re-picking the SAME file still fires `change`.
    e.target.value = "";
    if (!file || !uploadingId) return;

    if (file.type !== "application/pdf") {
      toast.error("Apenas arquivos PDF são aceitos.");
      setUploadingId(null);
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", file);
      // `api.upload`, not a hand-rolled multipart fetch: `api.post` would
      // JSON.stringify the FormData into `"{}"` and the endpoint would 422.
      // ERP hand-rolled this because it predates the seed's `upload` method.
      await api.upload(`/api/certidoes/resultados/${uploadingId}/upload`, formData);

      toast.success("Certidão enviada com sucesso!");
      queryClient.invalidateQueries({ queryKey: ["certidao-consulta"] });
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Erro ao enviar certidão";
      toast.error(msg);
    } finally {
      setUploadingId(null);
    }
  };

  const closeDetalhe = () => {
    setDetalheId(null);
    setExpandedAnalise(null);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Hidden file input for manual certificate upload */}
      <input
        ref={uploadInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        data-testid="upload-input"
        onChange={handleFileSelected}
      />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Certidoes Negativas</h1>
          <p className="text-muted-foreground">
            Emissao automatizada de certidoes com analise por IA
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Indicator only — never an early return. */}
          {isRefreshingConsultas && (
            <span
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
              data-testid="consultas-refreshing"
            >
              <Loader2 className="h-3 w-3 animate-spin" />
              Atualizando...
            </span>
          )}
          <Button
            onClick={() => {
              reset();
              setDialogAberto(true);
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Nova Consulta
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Processamento</CardTitle>
            <Loader2 className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.pendentes}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluidas</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.concluidas}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Com Erros</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.erros}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <FileCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.total}</div>
          </CardContent>
        </Card>
      </div>

      {/* TJSP Queue Status */}
      {tjspFila && (tjspFila.total_na_fila > 0 || tjspFila.cooldown.ativo) && (
        <Card
          className="border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20"
          data-testid="tjsp-fila"
        >
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Timer className="h-4 w-4 text-amber-500" />
              Fila TJSP
              <Badge variant="outline" className="ml-auto text-amber-600 border-amber-300">
                {tjspFila.total_na_fila} na fila
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Cooldown bar */}
            {tjspFila.cooldown.ativo && cooldownSegs > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Cooldown TJSP (limite: 1 request / 30 min)</span>
                  <span
                    className="font-mono font-medium text-amber-600"
                    data-testid="tjsp-cooldown-countdown"
                  >
                    {Math.floor(cooldownSegs / 60)}:{String(cooldownSegs % 60).padStart(2, "0")}
                  </span>
                </div>
                <Progress
                  value={
                    ((tjspFila.cooldown.segundos_restantes! - cooldownSegs) /
                      tjspFila.cooldown.segundos_restantes!) *
                    100
                  }
                  className="h-1.5"
                />
              </div>
            )}

            {/* Queue items */}
            {tjspFila.items.length > 0 && (
              <div className="space-y-1.5">
                {tjspFila.items.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center gap-3 text-sm rounded-md bg-white dark:bg-background px-3 py-2 border"
                  >
                    <span className="font-mono text-xs text-muted-foreground w-5 text-center">
                      #{item.posicao}
                    </span>
                    <span className="font-medium truncate flex-1">{item.nome}</span>
                    <span className="text-xs text-muted-foreground">
                      {item.tipo_documento.toUpperCase()}: {item.documento}
                    </span>
                    <Clock className="h-3 w-3 text-muted-foreground shrink-0" />
                  </div>
                ))}
              </div>
            )}

            {!tjspFila.cooldown.ativo && tjspFila.total_na_fila > 0 && (
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" />
                Processando proximo item da fila...
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nome ou documento..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="pl-10"
                data-testid="busca-input"
              />
            </div>
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os status</SelectItem>
                <SelectItem value="pendente">Pendente</SelectItem>
                <SelectItem value="processando">Processando</SelectItem>
                <SelectItem value="concluida">Concluída</SelectItem>
                <SelectItem value="erro">Erro</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* A refresh that fails while we still hold data: keep showing the data,
          say so inline. Blanking a populated table on a transient poll error
          would be the lying-loading-state failure in its other direction. */}
      {consultasQuery.isError && !!consultasQuery.data && (
        <div
          className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          data-testid="consultas-stale-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Nao foi possivel atualizar a lista. Exibindo os dados anteriores.
        </div>
      )}

      {/* Consultas List */}
      {showConsultasSkeleton ? (
        <Card>
          <CardContent className="pt-6">
            <TableSkeleton rows={4} columns={4} />
          </CardContent>
        </Card>
      ) : consultasQuery.isError && !consultasQuery.data ? (
        <Card data-testid="consultas-error">
          <CardContent className="py-12 text-center text-muted-foreground">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-destructive opacity-70" />
            <p className="text-lg">Erro ao carregar consultas</p>
            <p className="text-sm mt-1">
              {consultasQuery.error instanceof Error
                ? consultasQuery.error.message
                : "Tente novamente em instantes."}
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => consultasQuery.refetch()}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Tentar novamente
            </Button>
          </CardContent>
        </Card>
      ) : consultas.length === 0 ? (
        <Card data-testid="consultas-empty">
          <CardContent className="py-12 text-center text-muted-foreground">
            <ShieldCheck className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">Nenhuma consulta encontrada</p>
            <p className="text-sm mt-1">Crie uma nova consulta para emitir certidoes</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="consultas-list">
          {consultas.map((consulta) => {
            const statusConfig =
              CONSULTA_STATUS_CONFIG[consulta.status] || CONSULTA_STATUS_CONFIG.pendente;
            const total = consulta.total_certidoes || 1;
            const successPct = (consulta.concluidas / total) * 100;
            const errorPct = ((consulta.erros || 0) / total) * 100;
            const isProcessing =
              consulta.status === "pendente" || consulta.status === "processando";

            return (
              <Card key={consulta.id} className="hover:shadow-md transition-shadow">
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        {consulta.tipo_documento === "cpf" ? (
                          <User className="h-5 w-5 text-muted-foreground shrink-0" />
                        ) : (
                          <Building2 className="h-5 w-5 text-muted-foreground shrink-0" />
                        )}
                        <h3 className="font-semibold text-lg truncate">{consulta.nome}</h3>
                        <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
                      </div>

                      <div className="flex items-center gap-4 text-sm text-muted-foreground mb-3">
                        <span>
                          {consulta.tipo_documento.toUpperCase()}: {consulta.documento}
                        </span>
                        <span>{formatDate(consulta.created_at)}</span>
                      </div>

                      <div className="flex items-center gap-3">
                        {/* Two-segment bar: success fills from the left, errors
                            stack immediately after it, so "6 of 8 done, 1 of
                            those failed" is one glance rather than two. */}
                        <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-secondary/20">
                          <div
                            className="absolute inset-y-0 left-0 bg-primary transition-all duration-500"
                            style={{ width: `${successPct}%` }}
                          />
                          <div
                            className="absolute inset-y-0 bg-destructive transition-all duration-500"
                            style={{ left: `${successPct}%`, width: `${errorPct}%` }}
                          />
                        </div>
                        <span className="text-sm text-muted-foreground whitespace-nowrap">
                          {consulta.concluidas}/{consulta.total_certidoes}
                        </span>
                        {isProcessing && (
                          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        )}
                      </div>
                    </div>

                    <div className="flex gap-2 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDetalheId(consulta.id)}
                      >
                        <Eye className="h-3 w-3 mr-1" />
                        Detalhes
                      </Button>
                      {consulta.concluidas > 0 && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDownloadAll(consulta)}
                          disabled={downloadingZip === consulta.id}
                        >
                          {downloadingZip === consulta.id ? (
                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          ) : (
                            <Download className="h-3 w-3 mr-1" />
                          )}
                          Baixar Tudo
                        </Button>
                      )}
                      {isProcessing && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => cancelarMutation.mutate(consulta.id)}
                          disabled={cancelarMutation.isPending}
                        >
                          {cancelarMutation.isPending ? (
                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          ) : (
                            <XCircle className="h-3 w-3 mr-1" />
                          )}
                          Cancelar
                        </Button>
                      )}
                      {consulta.status === "erro" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleReprocessar(consulta.id)}
                          disabled={reprocessarMutation.isPending}
                        >
                          <RefreshCw className="h-3 w-3 mr-1" />
                          Reprocessar
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Excluir consulta ${consulta.nome}`}
                        onClick={() => setDeleteId(consulta.id)}
                      >
                        <Trash2 className="h-3 w-3 text-muted-foreground" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Consulta Dialog */}
      <Dialog open={dialogAberto} onOpenChange={setDialogAberto}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Nova Consulta de Certidoes</DialogTitle>
            <DialogDescription>
              Preencha os dados para emitir as certidoes negativas automaticamente.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit(handleCreate)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Tipo de Documento</Label>
                <Select
                  value={tipoDocumento}
                  onValueChange={(v) => setValue("tipo_documento", v as "cpf" | "cnpj")}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cpf">CPF - Pessoa Fisica</SelectItem>
                    <SelectItem value="cnpj">CNPJ - Pessoa Juridica</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Documento</Label>
                <Input {...register("documento")} placeholder="Apenas numeros" />
                {errors.documento && (
                  <p className="text-sm text-destructive mt-1">{errors.documento.message}</p>
                )}
              </div>
            </div>

            <div>
              <Label>Nome Completo / Razao Social</Label>
              <Input {...register("nome")} placeholder="Nome completo ou razao social" />
              {errors.nome && (
                <p className="text-sm text-destructive mt-1">{errors.nome.message}</p>
              )}
            </div>

            {tipoDocumento === "cpf" && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Data de Nascimento</Label>
                    <Input type="date" {...register("data_nascimento")} />
                  </div>
                  <div>
                    <Label>Genero</Label>
                    <Select
                      value={watch("genero") || ""}
                      onValueChange={(v) => setValue("genero", v as "M" | "F" | "")}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Selecione" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="M">Masculino</SelectItem>
                        <SelectItem value="F">Feminino</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <Label>RG (opcional - melhora resultados TJSP)</Label>
                  <Input {...register("rg")} placeholder="Numero do RG" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Nome da Mae</Label>
                    <Input {...register("nome_mae")} />
                  </div>
                  <div>
                    <Label>Nome do Pai</Label>
                    <Input {...register("nome_pai")} />
                  </div>
                </div>
              </>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogAberto(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Iniciando...
                  </>
                ) : (
                  <>
                    <FileCheck className="h-4 w-4 mr-2" />
                    Emitir Certidoes
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!detalheId} onOpenChange={closeDetalhe}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes da Consulta</DialogTitle>
            {detalhe && (
              <DialogDescription>
                {detalhe.nome} - {detalhe.tipo_documento.toUpperCase()}: {detalhe.documento}
              </DialogDescription>
            )}
          </DialogHeader>

          {showDetalheSkeleton && (
            <div data-testid="detalhe-skeleton">
              <TableSkeleton rows={5} columns={4} />
            </div>
          )}

          {!showDetalheSkeleton && detalheQuery.isError && !detalhe && (
            <div
              className="py-8 text-center text-muted-foreground"
              data-testid="detalhe-error"
            >
              <AlertCircle className="h-10 w-10 mx-auto mb-3 text-destructive opacity-70" />
              <p>Erro ao carregar os detalhes da consulta</p>
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => detalheQuery.refetch()}
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Tentar novamente
              </Button>
            </div>
          )}

          {detalhe && (
            <div className="space-y-4">
              {/* Progress */}
              {(() => {
                const total = detalhe.total_certidoes || 1;
                const sPct = (detalhe.concluidas / total) * 100;
                const ePct = ((detalhe.erros || 0) / total) * 100;
                return (
                  <div className="flex items-center gap-3">
                    <div className="relative flex-1 h-3 overflow-hidden rounded-full bg-secondary/20">
                      <div
                        className="absolute inset-y-0 left-0 bg-primary transition-all duration-500"
                        style={{ width: `${sPct}%` }}
                      />
                      <div
                        className="absolute inset-y-0 bg-destructive transition-all duration-500"
                        style={{ left: `${sPct}%`, width: `${ePct}%` }}
                      />
                    </div>
                    <Badge variant={CONSULTA_STATUS_CONFIG[detalhe.status]?.variant || "outline"}>
                      {CONSULTA_STATUS_CONFIG[detalhe.status]?.label || detalhe.status}
                    </Badge>
                  </div>
                );
              })()}

              {/* Results Table */}
              {(detalhe.resultados || []).length === 0 ? (
                <p
                  className="py-8 text-center text-sm text-muted-foreground"
                  data-testid="detalhe-empty"
                >
                  Nenhuma certidao nesta consulta ainda.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8">#</TableHead>
                      <TableHead>Certidao</TableHead>
                      <TableHead className="w-24">Status</TableHead>
                      <TableHead className="w-24">Acoes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(detalhe.resultados || []).map((resultado) => {
                      const statusIcon =
                        RESULTADO_STATUS_ICON[resultado.status] || RESULTADO_STATUS_ICON.pendente;
                      const StatusIcon = statusIcon.icon;
                      const isExpanded = expandedAnalise === resultado.id;

                      return (
                        <Fragment key={resultado.id}>
                          <TableRow>
                            <TableCell className="font-mono text-sm">{resultado.ordem}</TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                                <span className="font-medium">{resultado.nome_display}</span>
                              </div>
                              {resultado.erro_mensagem && (
                                <p className="text-xs text-destructive mt-1">
                                  {resultado.erro_mensagem}
                                </p>
                              )}
                            </TableCell>
                            <TableCell>
                              <div className={`flex items-center gap-1.5 ${statusIcon.color}`}>
                                <StatusIcon
                                  className={`h-4 w-4 ${resultado.status === "processando" ? "animate-spin" : ""}`}
                                />
                                <span className="text-sm capitalize">
                                  {statusIcon.label || resultado.status}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className="flex gap-1">
                                {resultado.analise_ia && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    aria-label={`Analise IA ${resultado.nome_display}`}
                                    onClick={() =>
                                      setExpandedAnalise(isExpanded ? null : resultado.id)
                                    }
                                  >
                                    <ChevronDown
                                      className={`h-3 w-3 transition-transform duration-300 ${isExpanded ? "rotate-180" : ""}`}
                                    />
                                  </Button>
                                )}
                                {resultado.arquivo_url && (
                                  <>
                                    <Button size="sm" variant="ghost" asChild title="Abrir em nova guia">
                                      <a
                                        href={resultado.arquivo_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                      >
                                        <ExternalLink className="h-3 w-3" />
                                      </a>
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      title="Download"
                                      aria-label={`Download ${resultado.nome_display}`}
                                      onClick={() =>
                                        handleDownload(
                                          resultado.arquivo_url!,
                                          resultado.arquivo_nome || "certidao.pdf",
                                        )
                                      }
                                    >
                                      <Download className="h-3 w-3" />
                                    </Button>
                                  </>
                                )}
                                {resultado.status !== "sucesso" &&
                                  resultado.status !== "processando" && (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      title="Upload manual"
                                      aria-label={`Upload manual ${resultado.nome_display}`}
                                      onClick={() => handleUploadClick(resultado.id)}
                                      disabled={uploadingId === resultado.id}
                                    >
                                      {uploadingId === resultado.id ? (
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                      ) : (
                                        <Upload className="h-3 w-3" />
                                      )}
                                    </Button>
                                  )}
                              </div>
                            </TableCell>
                          </TableRow>
                          {resultado.analise_ia && (
                            <TableRow>
                              <TableCell colSpan={4} className="p-0">
                                {/* grid-template-rows 0fr→1fr: animates to the
                                    content's natural height without measuring it. */}
                                <div
                                  className="grid transition-[grid-template-rows] duration-300 ease-in-out"
                                  style={{ gridTemplateRows: isExpanded ? "1fr" : "0fr" }}
                                >
                                  <div className="overflow-hidden">
                                    <div className="bg-muted/50 rounded-lg p-4 m-2 text-sm whitespace-pre-wrap">
                                      <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-muted-foreground uppercase">
                                        <ShieldCheck className="h-3 w-3" />
                                        Analise IA
                                      </div>
                                      {resultado.analise_ia}
                                    </div>
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              )}

              {/* Action buttons */}
              <div className="flex justify-end gap-2">
                {detalhe.concluidas > 0 && (
                  <Button
                    variant="outline"
                    onClick={() => handleDownloadAll(detalhe)}
                    disabled={downloadingZip === detalhe.id}
                  >
                    {downloadingZip === detalhe.id ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4 mr-2" />
                    )}
                    Baixar Tudo (.zip)
                  </Button>
                )}
                {(detalhe.status === "pendente" || detalhe.status === "processando") && (
                  <Button
                    variant="outline"
                    onClick={() => cancelarMutation.mutate(detalhe.id)}
                    disabled={cancelarMutation.isPending}
                  >
                    {cancelarMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <XCircle className="h-4 w-4 mr-2" />
                    )}
                    Cancelar Processamento
                  </Button>
                )}
                {detalhe.resultados?.some((r) => r.status === "erro") && (
                  <Button
                    variant="outline"
                    onClick={() => handleReprocessar(detalhe.id)}
                    disabled={reprocessarMutation.isPending}
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Reprocessar Certidoes com Erro
                  </Button>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={closeDetalhe}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Consulta</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir esta consulta e todas as certidoes associadas? Esta
              acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive hover:bg-destructive/90"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
