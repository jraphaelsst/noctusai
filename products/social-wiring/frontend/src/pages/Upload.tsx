/**
 * Upload page — submit a video to YouTube via either:
 *   1. Browser file upload (drag-and-drop or picker)
 *   2. Google Drive shared link
 *
 * Form state is local (no react-hook-form needed for this size). On
 * submit, kicks off the upload, switches to a progress view that polls
 * /status, then shows success + the YouTube link. Below the form, a
 * history table lists recent jobs.
 */
import { useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  Loader2,
  Send,
  UploadCloud,
  Link as LinkIcon,
} from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

import { UploadZone } from "@/components/UploadZone";
import {
  isTerminal,
  useUploadHistory,
  useUploadMutations,
  useUploadStatus,
  type PrivacyStatus,
  type UploadJob,
  type UploadJobStatus,
  type UploadMetadata,
} from "@/hooks/useUpload";
import { useRecipients, type Recipient } from "@/hooks/useSettings";
import { toast } from "sonner";

// ─── Helpers ───────────────────────────────────────────────────────────
const PRIVACY_OPTIONS: { value: PrivacyStatus; label: string; help: string }[] = [
  { value: "private", label: "Privado", help: "So voce pode ver" },
  { value: "unlisted", label: "Nao listado", help: "Acessivel pelo link" },
  { value: "public", label: "Publico", help: "Visivel para todos" },
];

const STATUS_LABELS: Record<UploadJobStatus, string> = {
  queued: "Na fila",
  downloading: "Baixando do Drive",
  uploading: "Enviando para o YouTube",
  processing: "Processando",
  published: "Publicado",
  notified: "Notificado",
  failed: "Falhou",
};

function StatusBadge({ status }: { status: UploadJobStatus }) {
  const variant = status === "failed"
    ? "destructive"
    : isTerminal(status)
      ? "default"
      : "secondary";
  return <Badge variant={variant}>{STATUS_LABELS[status]}</Badge>;
}

function youtubeUrl(videoId: string | null | undefined): string | null {
  if (!videoId) return null;
  return `https://www.youtube.com/watch?v=${videoId}`;
}

// ─── Recipient picker (shared between tabs) ────────────────────────────
function RecipientPicker({
  recipients,
  selected,
  onChange,
  loading,
}: {
  recipients: Recipient[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  loading: boolean;
}) {
  const active = recipients.filter((r) => r.is_active);

  if (loading) {
    return (
      <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
        Carregando destinatarios...
      </div>
    );
  }

  if (active.length === 0) {
    return (
      <div className="rounded-md border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
        Nenhum destinatario ativo. Adicione destinatarios em Configuracoes.
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border bg-muted/10 p-3">
      {active.map((r) => {
        const isOn = selected.has(r.id);
        return (
          <div
            key={r.id}
            className="flex items-center justify-between gap-3 rounded px-2 py-1 hover:bg-muted/40"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{r.name}</div>
              <div className="truncate text-xs text-muted-foreground">
                {r.email && <span>{r.email}</span>}
                {r.email && r.whatsapp_number && <span> · </span>}
                {r.whatsapp_number && <span>{r.whatsapp_number}</span>}
              </div>
            </div>
            <Switch
              checked={isOn}
              onCheckedChange={(checked) => {
                const next = new Set(selected);
                if (checked) next.add(r.id);
                else next.delete(r.id);
                onChange(next);
              }}
              aria-label={`Notificar ${r.name}`}
            />
          </div>
        );
      })}
    </div>
  );
}

// ─── Metadata form (shared between tabs) ───────────────────────────────
interface FormState {
  title: string;
  description: string;
  tagsInput: string; // comma-separated for the input
  privacy: PrivacyStatus;
  productCode: string;
}

function emptyForm(): FormState {
  return { title: "", description: "", tagsInput: "", privacy: "private", productCode: "" };
}

function formToMetadata(form: FormState, recipientIds: string[]): UploadMetadata {
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    tags: form.tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    privacy_status: form.privacy,
    category_id: "22",
    notify_recipients: recipientIds,
    product_code: form.productCode.trim() || undefined,
  };
}

function MetadataFields({
  form,
  setForm,
  disabled,
}: {
  form: FormState;
  setForm: (f: FormState) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label htmlFor="upload-title">Titulo *</Label>
          <Input
            id="upload-title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            maxLength={100}
            placeholder="Ex: Meu video novo"
            disabled={disabled}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="upload-product-code">Código do Imóvel</Label>
          <Input
            id="upload-product-code"
            value={form.productCode}
            onChange={(e) => setForm({ ...form, productCode: e.target.value.toUpperCase() })}
            maxLength={20}
            placeholder="ONE0000"
            disabled={disabled}
          />
          <p className="text-xs text-muted-foreground">
            Código do imóvel no CRM (ex: ONE5555). Quando preenchido, título e descrição podem ser preenchidos automaticamente.
          </p>
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="upload-description">Descricao</Label>
        <Textarea
          id="upload-description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          maxLength={5000}
          rows={4}
          placeholder="Descricao opcional"
          disabled={disabled}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label htmlFor="upload-tags">Tags (separadas por virgula)</Label>
          <Input
            id="upload-tags"
            value={form.tagsInput}
            onChange={(e) => setForm({ ...form, tagsInput: e.target.value })}
            placeholder="tutorial, demo, lancamento"
            disabled={disabled}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="upload-privacy">Privacidade</Label>
          <Select
            value={form.privacy}
            onValueChange={(v) => setForm({ ...form, privacy: v as PrivacyStatus })}
            disabled={disabled}
          >
            <SelectTrigger id="upload-privacy">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRIVACY_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  <div className="flex flex-col">
                    <span>{opt.label}</span>
                    <span className="text-xs text-muted-foreground">{opt.help}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

// ─── In-flight progress card ───────────────────────────────────────────
function ProgressCard({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { job } = useUploadStatus(jobId);

  if (!job) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 p-6">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Iniciando envio...</span>
        </CardContent>
      </Card>
    );
  }

  const url = youtubeUrl(job.youtube_video_id);
  const failed = job.status === "failed";
  const done = isTerminal(job.status);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            {failed ? (
              <CircleAlert className="h-5 w-5 text-destructive" />
            ) : done ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            ) : (
              <Loader2 className="h-5 w-5 animate-spin" />
            )}
            {job.title}
          </CardTitle>
          <StatusBadge status={job.status} />
        </div>
        <CardDescription>{job.file_name}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Progress value={job.progress_percent} />
        <div className="text-xs text-muted-foreground">
          {job.progress_percent}% — {STATUS_LABELS[job.status]}
        </div>
        {failed && job.error_message && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            {job.error_message}
          </div>
        )}
        {url && (
          <div className="flex items-center gap-2">
            <Button asChild variant="default" size="sm">
              <a href={url} target="_blank" rel="noreferrer">
                Ver no YouTube
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </Button>
          </div>
        )}
        {done && (
          <Button variant="outline" size="sm" onClick={onClose}>
            Novo envio
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Browser tab ───────────────────────────────────────────────────────
function BrowserUploadTab({
  recipients,
  recipientsLoading,
  onJobStarted,
}: {
  recipients: Recipient[];
  recipientsLoading: boolean;
  onJobStarted: (jobId: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { uploadFile, pending } = useUploadMutations();

  // Pre-select all active recipients on first load.
  useMemo(() => {
    if (recipients.length === 0) return;
    setSelected((prev) => {
      if (prev.size > 0) return prev;
      return new Set(recipients.filter((r) => r.is_active).map((r) => r.id));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recipients]);

  const canSubmit = !!file && form.title.trim().length > 0 && !pending;

  const submit = async () => {
    if (!file) return;
    try {
      const created = await uploadFile(file, formToMetadata(form, [...selected]));
      toast.success("Envio iniciado");
      onJobStarted(created.job_id);
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao iniciar o envio");
    }
  };

  return (
    <div className="space-y-4">
      <UploadZone file={file} onFileChange={setFile} disabled={pending} />
      <Separator />
      <MetadataFields form={form} setForm={setForm} disabled={pending} />
      <div className="grid gap-2">
        <Label>Notificar destinatarios</Label>
        <RecipientPicker
          recipients={recipients}
          selected={selected}
          onChange={setSelected}
          loading={recipientsLoading}
        />
      </div>
      <div className="flex justify-end">
        <Button onClick={submit} disabled={!canSubmit}>
          {pending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          Enviar
        </Button>
      </div>
    </div>
  );
}

// ─── Drive tab ─────────────────────────────────────────────────────────
function DriveUploadTab({
  recipients,
  recipientsLoading,
  onJobStarted,
}: {
  recipients: Recipient[];
  recipientsLoading: boolean;
  onJobStarted: (jobId: string) => void;
}) {
  const [driveUrl, setDriveUrl] = useState("");
  const [form, setForm] = useState<FormState>(emptyForm());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { uploadFromDrive, pending } = useUploadMutations();

  useMemo(() => {
    if (recipients.length === 0) return;
    setSelected((prev) => {
      if (prev.size > 0) return prev;
      return new Set(recipients.filter((r) => r.is_active).map((r) => r.id));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recipients]);

  const isLikelyDrive = driveUrl.includes("drive.google.com") || driveUrl.includes("docs.google.com");
  const canSubmit = isLikelyDrive && form.title.trim().length > 0 && !pending;

  const submit = async () => {
    try {
      const created = await uploadFromDrive(driveUrl.trim(), formToMetadata(form, [...selected]));
      toast.success("Envio iniciado");
      onJobStarted(created.job_id);
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao iniciar o envio");
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-2">
        <Label htmlFor="drive-url">Link do Google Drive</Label>
        <div className="relative">
          <LinkIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="drive-url"
            className="pl-10"
            value={driveUrl}
            onChange={(e) => setDriveUrl(e.target.value)}
            placeholder="https://drive.google.com/file/d/... ou .../drive/folders/..."
            disabled={pending}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          O link pode ser de um arquivo ou de uma pasta. Se for pasta, o sistema
          identifica automaticamente o vídeo para YouTube (16:9) e ignora REELS.
          O arquivo precisa estar com permissao de acesso por link.
        </p>
      </div>
      <Separator />
      <MetadataFields form={form} setForm={setForm} disabled={pending} />
      <div className="grid gap-2">
        <Label>Notificar destinatarios</Label>
        <RecipientPicker
          recipients={recipients}
          selected={selected}
          onChange={setSelected}
          loading={recipientsLoading}
        />
      </div>
      <div className="flex justify-end">
        <Button onClick={submit} disabled={!canSubmit}>
          {pending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          Baixar e Enviar
        </Button>
      </div>
    </div>
  );
}

// ─── History card ──────────────────────────────────────────────────────
function HistoryRow({ job }: { job: UploadJob }) {
  const url = youtubeUrl(job.youtube_video_id);
  return (
    <div className="flex items-center justify-between gap-4 border-b py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 truncate text-sm font-medium">
          {job.product_code && (
            <Badge variant="outline" className="shrink-0 text-[10px] font-mono">
              {job.product_code}
            </Badge>
          )}
          {job.title}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {job.file_name} · {new Date(job.created_at).toLocaleString("pt-BR")}
        </div>
        {job.error_message && (
          <div className="truncate text-xs text-destructive">{job.error_message}</div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={job.status} />
        {url && (
          <Button asChild variant="ghost" size="icon">
            <a href={url} target="_blank" rel="noreferrer" aria-label="Abrir no YouTube">
              <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}

function HistoryCard({ activeJobId }: { activeJobId: string | null }) {
  const { data, loading, refresh } = useUploadHistory(25);

  // Refresh when an in-flight job terminates so the row appears "fresh".
  // Cheap correctness over WS-based push (which would require backend changes).
  const { job: active } = useUploadStatus(activeJobId);
  useMemo(() => {
    if (active && isTerminal(active.status)) {
      void refresh();
    }
  }, [active?.status, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card>
      <CardHeader>
        <CardTitle>Historico recente</CardTitle>
        <CardDescription>Os 25 envios mais recentes desta organizacao</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center p-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-6 text-center text-sm text-muted-foreground">
            <UploadCloud className="h-8 w-8" />
            Nenhum envio ainda
          </div>
        ) : (
          <div>
            {data.map((job) => (
              <HistoryRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Page shell ────────────────────────────────────────────────────────
export default function UploadPage() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { data: recipients, loading: recipientsLoading } = useRecipients();

  return (
    <div className="container max-w-5xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Enviar video</h1>
        <p className="text-sm text-muted-foreground">
          Envie um arquivo do seu computador ou um link do Google Drive.
        </p>
      </div>

      {activeJobId && (
        <ProgressCard jobId={activeJobId} onClose={() => setActiveJobId(null)} />
      )}

      {!activeJobId && (
        <Card>
          <CardContent className="pt-6">
            <Tabs defaultValue="browser">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="browser">
                  <UploadCloud className="mr-2 h-4 w-4" />
                  Computador
                </TabsTrigger>
                <TabsTrigger value="drive">
                  <LinkIcon className="mr-2 h-4 w-4" />
                  Google Drive
                </TabsTrigger>
              </TabsList>
              <TabsContent value="browser" className="mt-6">
                <BrowserUploadTab
                  recipients={recipients}
                  recipientsLoading={recipientsLoading}
                  onJobStarted={setActiveJobId}
                />
              </TabsContent>
              <TabsContent value="drive" className="mt-6">
                <DriveUploadTab
                  recipients={recipients}
                  recipientsLoading={recipientsLoading}
                  onJobStarted={setActiveJobId}
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      <HistoryCard activeJobId={activeJobId} />
    </div>
  );
}
