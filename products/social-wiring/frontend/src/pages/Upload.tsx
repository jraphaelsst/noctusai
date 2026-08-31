/**
 * Upload panel — YouTube → Upload. Three sub-tabs:
 *
 *   Chat        (default) the Agente: code + video, agent does the rest.
 *   Computador  simplified browser upload: ONLY the file + the code (ONE0000);
 *               the system resolves metadata from the CRM and runs the rest.
 *   Google Drive  link/folder upload with the full metadata form.
 *
 * Once a job starts, a live STEPPER tracks the pipeline step-by-step
 * (queued → [baixando] → enviando → processando → validado) with a progress
 * bar; 100% = the uploaded video validated (published on YouTube). The flow
 * itself is unchanged — we already had the upload pipeline.
 *
 * Rendered inside the YouTube page (and architected so Upload + Vídeos fuse
 * cleanly later).
 */
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Circle,
  CircleAlert,
  ExternalLink,
  Loader2,
  MessageCircle,
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

import ChatPanel from "@/components/ChatPanel";
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
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
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

function youtubeUrl(videoId: string | null | undefined): string | null {
  if (!videoId) return null;
  return `https://www.youtube.com/watch?v=${videoId}`;
}

function StatusBadge({ status }: { status: UploadJobStatus }) {
  const variant = status === "failed"
    ? "destructive"
    : isTerminal(status)
      ? "default"
      : "secondary";
  return <Badge variant={variant}>{STATUS_LABELS[status]}</Badge>;
}

// ─── Live step tracker ─────────────────────────────────────────────────
// Ordinal position of each status in the pipeline (notified == published == 4,
// i.e. 100% / validated). The stepper marks each step done / active / pending
// from this ordinal.
const STATUS_ORDER: Record<UploadJobStatus, number> = {
  queued: 0,
  downloading: 1,
  uploading: 2,
  processing: 3,
  published: 4,
  notified: 4,
  failed: -1,
};

interface StepDef {
  key: string;
  label: string;
  ord: number;
  driveOnly?: boolean;
}

const STEP_DEFS: StepDef[] = [
  { key: "queued", label: "Na fila", ord: 0 },
  { key: "downloading", label: "Baixando", ord: 1, driveOnly: true },
  { key: "uploading", label: "Enviando", ord: 2 },
  { key: "processing", label: "Processando", ord: 3 },
  { key: "published", label: "Validado", ord: 4 },
];

function Stepper({ job }: { job: UploadJob }) {
  const steps = STEP_DEFS.filter((s) => !s.driveOnly || job.source_type === "gdrive");
  const curr = STATUS_ORDER[job.status];
  const done100 = job.status === "published" || job.status === "notified";
  const failed = job.status === "failed";

  return (
    <ol className="space-y-2">
      {steps.map((step) => {
        const isDone = !failed && (curr > step.ord || (done100 && curr >= step.ord));
        const isActive = !failed && !done100 && curr === step.ord;
        return (
          <li key={step.key} className="flex items-center gap-2 text-sm">
            {isDone ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : isActive ? (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            ) : failed ? (
              <CircleAlert className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Circle className="h-4 w-4 text-muted-foreground" />
            )}
            <span className={isActive ? "font-medium" : isDone ? "" : "text-muted-foreground"}>
              {step.label}
              {step.key === "published" && " (100%)"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// ─── In-flight progress card (stepper + bar) ───────────────────────────
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
        <Stepper job={job} />
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

// ─── Recipient picker (Drive tab) ──────────────────────────────────────
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

// ─── Metadata form (Drive tab) ─────────────────────────────────────────
interface FormState {
  title: string;
  description: string;
  tagsInput: string;
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
    tags: form.tagsInput.split(",").map((t) => t.trim()).filter(Boolean),
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
        <Label htmlFor="upload-description">Descrição</Label>
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

// ─── YouTube account selector ──────────────────────────────────────────
/**
 * Renders a "YouTube account" dropdown.
 *
 * No "conta padrão" concept: with exactly one account (every provider's
 * live state today — accounts are purely scoped by marca) it is
 * auto-selected on first load. With more than one, `SelectValue`'s
 * placeholder already forces an honest explicit choice — never labelled
 * "padrão". When no accounts exist, shows a CTA linking to /marcas.
 */
function YouTubeAccountPicker({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (accountId: string) => void;
  disabled?: boolean;
}) {
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this select on every background refresh.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data: accounts = [], isPending } = useIntegrationAccounts("youtube");

  // Auto-select on first load ONLY when there is exactly one account — with
  // more than one, the user must pick explicitly (the placeholder below).
  const soleAccount = accounts.length === 1 ? accounts[0] : undefined;
  if (!value && soleAccount) {
    onChange(soleAccount.id);
  }

  if (isPending) {
    return (
      <div className="grid gap-1.5">
        <Label>Conta YouTube</Label>
        <div className="flex h-9 items-center text-xs text-muted-foreground">
          <Loader2 className="mr-2 h-3 w-3 animate-spin" />
          Carregando contas...
        </div>
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="grid gap-1.5">
        <Label>Conta YouTube</Label>
        <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          Nenhuma conta YouTube conectada.{" "}
          <a href="/marcas" className="underline underline-offset-2 hover:text-foreground">
            Conecte uma conta primeiro.
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-1.5">
      <Label htmlFor="yt-account">Conta YouTube</Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id="yt-account">
          <SelectValue placeholder="Selecionar conta..." />
        </SelectTrigger>
        <SelectContent>
          {accounts.map((acc) => (
            <SelectItem key={acc.id} value={acc.id}>
              {acc.account_label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// ─── Computador tab — file + code only ─────────────────────────────────
function ComputerUploadTab({ onJobStarted }: { onJobStarted: (jobId: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [productCode, setProductCode] = useState("");
  const [accountId, setAccountId] = useState("");
  const { uploadFromCode, pending } = useUploadMutations();

  const canSubmit = !!file && productCode.trim().length > 0 && !pending;

  const submit = async () => {
    if (!file) return;
    try {
      const created = await uploadFromCode(file, productCode.trim(), accountId || undefined);
      toast.success("Envio iniciado");
      onJobStarted(created.job_id);
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao iniciar o envio");
    }
  };

  return (
    <div className="space-y-4">
      <UploadZone file={file} onFileChange={setFile} disabled={pending} />
      <YouTubeAccountPicker value={accountId} onChange={setAccountId} disabled={pending} />
      <div className="grid gap-2">
        <Label htmlFor="computer-code">Código do Imóvel *</Label>
        <Input
          id="computer-code"
          value={productCode}
          onChange={(e) => setProductCode(e.target.value.toUpperCase())}
          maxLength={20}
          placeholder="ONE0000"
          disabled={pending}
        />
        <p className="text-xs text-muted-foreground">
          Só o arquivo e o código. O sistema busca título, descrição e tags no
          CRM e dispara todo o resto automaticamente.
        </p>
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

// ─── Drive tab — full form ─────────────────────────────────────────────
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
  const [accountId, setAccountId] = useState("");
  const { uploadFromDrive, pending } = useUploadMutations();

  useEffect(() => {
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
      const created = await uploadFromDrive(
        driveUrl.trim(),
        formToMetadata(form, [...selected]),
        accountId || undefined
      );
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
      <YouTubeAccountPicker value={accountId} onChange={setAccountId} disabled={pending} />
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
  const { job: active } = useUploadStatus(activeJobId);
  useEffect(() => {
    if (active && isTerminal(active.status)) {
      void refresh();
    }
  }, [active?.status, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card>
      <CardHeader>
        <CardTitle>Histórico recente</CardTitle>
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

// ─── Panel ─────────────────────────────────────────────────────────────
export default function UploadPanel() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { data: recipients, loading: recipientsLoading } = useRecipients();

  return (
    <div className="space-y-6">
      {activeJobId && (
        <ProgressCard jobId={activeJobId} onClose={() => setActiveJobId(null)} />
      )}

      {!activeJobId && (
        <Card>
          <CardContent className="pt-6">
            <Tabs defaultValue="chat">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="chat">
                  <MessageCircle className="mr-2 h-4 w-4" />
                  Chat
                </TabsTrigger>
                <TabsTrigger value="computer">
                  <UploadCloud className="mr-2 h-4 w-4" />
                  Computador
                </TabsTrigger>
                <TabsTrigger value="drive">
                  <LinkIcon className="mr-2 h-4 w-4" />
                  Google Drive
                </TabsTrigger>
              </TabsList>
              <TabsContent value="chat" className="mt-6">
                <ChatPanel />
              </TabsContent>
              <TabsContent value="computer" className="mt-6">
                <ComputerUploadTab onJobStarted={setActiveJobId} />
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
