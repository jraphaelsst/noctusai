/**
 * EmailCampanhas — Mailchimp campaign management.
 *
 * Table: Título/Assunto, Status badge, Destinatários, Enviados/Aberturas/Cliques, Data
 * Create modal: segment select + template select + campaign metadata
 * Status-dependent actions:
 *   draft (save) → Enviar (confirm) / Agendar (quarter-hour UTC picker) /
 *                  Enviar teste / Editar / Excluir
 *   scheduled   → Cancelar agendamento
 *   sent        → read-only + archive_url link
 *
 * All states: loading / empty / error / success.
 * Wrapped in <MailchimpGate>.
 */
import { useState } from "react";
import {
  Send,
  Plus,
  Calendar,
  Clock,
  ExternalLink,
  Pencil,
  Trash2,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  TestTube2,
  X,
} from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import { MailchimpGate } from "@/components/mailchimp/MailchimpGate";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
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
import {
  useMailchimpCampaigns,
  useMailchimpCampaignMutations,
  type CampaignOut,
  type CampaignStatus,
} from "@/hooks/useMailchimpCampaigns";
import { useMailchimpSegments } from "@/hooks/useMailchimpSegments";
import { useMailchimpTemplates } from "@/hooks/useMailchimpTemplates";

const PAGE_SIZE = 25;

const STATUS_LABELS: Record<CampaignStatus, string> = {
  save: "Rascunho",
  paused: "Pausada",
  schedule: "Agendada",
  sending: "Enviando",
  sent: "Enviada",
};

const STATUS_COLORS: Record<CampaignStatus, string> = {
  save: "bg-gray-100 text-gray-800",
  paused: "bg-yellow-100 text-yellow-800",
  schedule: "bg-blue-100 text-blue-800",
  sending: "bg-purple-100 text-purple-800",
  sent: "bg-green-100 text-green-800",
};

interface CreateForm {
  title: string;
  subject_line: string;
  preview_text: string;
  from_name: string;
  reply_to: string;
  segment_id: string;
  template_id: string;
}

const emptyCreateForm = (): CreateForm => ({
  title: "",
  subject_line: "",
  preview_text: "",
  from_name: "",
  reply_to: "",
  segment_id: "",
  template_id: "",
});

// Round up to the next quarter-hour in UTC
function nextQuarterHour(): string {
  const d = new Date();
  const ms = 15 * 60 * 1000;
  const rounded = new Date(Math.ceil((d.getTime() + ms) / ms) * ms);
  // format for datetime-local input (local time — user picks, we send as-is with UTC conversion)
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${rounded.getFullYear()}-${pad(rounded.getMonth() + 1)}-${pad(rounded.getDate())}T${pad(rounded.getHours())}:${pad(rounded.getMinutes())}`;
}

function CampanhasContent() {
  const [offset, setOffset] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [sendTarget, setSendTarget] = useState<CampaignOut | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<CampaignOut | null>(null);
  const [unscheduleTarget, setUnscheduleTarget] = useState<CampaignOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CampaignOut | null>(null);
  const [testTarget, setTestTarget] = useState<CampaignOut | null>(null);
  const [scheduleTime, setScheduleTime] = useState(nextQuarterHour);
  const [testEmails, setTestEmails] = useState("");
  const [createForm, setCreateForm] = useState<CreateForm>(emptyCreateForm());

  const { data, isLoading, isError, error } = useMailchimpCampaigns({
    count: PAGE_SIZE,
    offset,
  });
  const { create, remove, send, schedule, unschedule, sendTest } =
    useMailchimpCampaignMutations();

  // For dropdowns in create modal
  const { data: segments } = useMailchimpSegments({ count: 100 });
  const { data: templates } = useMailchimpTemplates({ count: 100 });

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    create.mutate(
      {
        title: createForm.title,
        subject_line: createForm.subject_line,
        preview_text: createForm.preview_text || undefined,
        from_name: createForm.from_name,
        reply_to: createForm.reply_to,
        segment_id: createForm.segment_id
          ? Number(createForm.segment_id)
          : undefined,
        template_id: createForm.template_id
          ? Number(createForm.template_id)
          : undefined,
      },
      {
        onSuccess: () => {
          toast.success("Campanha criada.");
          setCreateOpen(false);
          setCreateForm(emptyCreateForm());
        },
        onError: () => toast.error("Erro ao criar campanha."),
      },
    );
  }

  function handleSend() {
    if (!sendTarget) return;
    send.mutate(sendTarget.id, {
      onSuccess: () => {
        toast.success("Campanha enviada!");
        setSendTarget(null);
      },
      onError: () => toast.error("Erro ao enviar campanha."),
    });
  }

  function handleSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!scheduleTarget) return;
    // Convert local datetime-local to ISO UTC
    const isoUtc = new Date(scheduleTime).toISOString();
    schedule.mutate(
      { id: scheduleTarget.id, body: { schedule_time: isoUtc } },
      {
        onSuccess: () => {
          toast.success("Campanha agendada.");
          setScheduleTarget(null);
        },
        onError: () => toast.error("Erro ao agendar campanha."),
      },
    );
  }

  function handleUnschedule() {
    if (!unscheduleTarget) return;
    unschedule.mutate(unscheduleTarget.id, {
      onSuccess: () => {
        toast.success("Agendamento cancelado.");
        setUnscheduleTarget(null);
      },
      onError: () => toast.error("Erro ao cancelar agendamento."),
    });
  }

  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Campanha removida.");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Erro ao remover campanha."),
    });
  }

  function handleSendTest(e: React.FormEvent) {
    e.preventDefault();
    if (!testTarget) return;
    const emails = testEmails
      .split(",")
      .map((e) => e.trim())
      .filter(Boolean);
    sendTest.mutate(
      { id: testTarget.id, body: { emails } },
      {
        onSuccess: () => {
          toast.success("Email de teste enviado.");
          setTestTarget(null);
          setTestEmails("");
        },
        onError: () => toast.error("Erro ao enviar teste."),
      },
    );
  }

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Send className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold">Campanhas</h1>
            <p className="text-sm text-muted-foreground">
              Gerencie e envie suas campanhas de email
            </p>
          </div>
        </div>
        <Button
          onClick={() => setCreateOpen(true)}
          className="gap-2"
          data-testid="btn-nova-campanha"
        >
          <Plus className="h-4 w-4" />
          Nova campanha
        </Button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2" data-testid="campanhas-loading">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <Card className="border-destructive" data-testid="campanhas-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar campanhas:{" "}
              {((error as Error)?.message ?? "").replace(/^\[\d+\]\s*/, "") || "Tente novamente."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Empty */}
      {!isLoading && !isError && data?.items.length === 0 && (
        <Card data-testid="campanhas-empty">
          <CardHeader>
            <CardTitle className="text-base">Nenhuma campanha encontrada</CardTitle>
            <CardDescription>
              Crie sua primeira campanha de email clicando em Nova campanha.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Table */}
      {!isLoading && !isError && (data?.items.length ?? 0) > 0 && (
        <Card data-testid="campanhas-table">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">
                      Título / Assunto
                    </th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">
                      Enviados
                    </th>
                    <th className="px-4 py-3 text-right font-medium">
                      Aberturas
                    </th>
                    <th className="px-4 py-3 text-right font-medium">
                      Cliques
                    </th>
                    <th className="px-4 py-3 text-left font-medium">Data</th>
                    <th className="px-4 py-3 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.items.map((c) => (
                    <tr
                      key={c.id}
                      className="border-b last:border-0 hover:bg-muted/30"
                      data-testid={`campanha-row-${c.id}`}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium">{c.title}</p>
                        {c.subject_line && (
                          <p className="text-xs text-muted-foreground">
                            {c.subject_line}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            STATUS_COLORS[c.status] ??
                            "bg-gray-100 text-gray-800"
                          }`}
                          data-testid={`status-badge-${c.id}`}
                        >
                          {STATUS_LABELS[c.status] ?? c.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                        {c.emails_sent ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                        {c.opens ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                        {c.clicks ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {c.send_time
                          ? format(new Date(c.send_time), "dd/MM/yyyy HH:mm", {
                              locale: ptBR,
                            })
                          : format(new Date(c.create_time), "dd/MM/yyyy", {
                              locale: ptBR,
                            })}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {/* Sent → read-only + archive link */}
                          {c.status === "sent" && c.archive_url && (
                            <Button
                              asChild
                              variant="ghost"
                              size="icon"
                              data-testid={`archive-url-${c.id}`}
                            >
                              <a
                                href={c.archive_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <ExternalLink className="h-4 w-4" />
                                <span className="sr-only">Ver online</span>
                              </a>
                            </Button>
                          )}

                          {/* Scheduled → Cancelar agendamento */}
                          {c.status === "schedule" && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-xs"
                              onClick={() => setUnscheduleTarget(c)}
                              data-testid={`unschedule-btn-${c.id}`}
                            >
                              <X className="h-3.5 w-3.5 mr-1" />
                              Cancelar
                            </Button>
                          )}

                          {/* Draft → Enviar teste */}
                          {c.status === "save" && (
                            <>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setTestTarget(c)}
                                data-testid={`test-btn-${c.id}`}
                              >
                                <TestTube2 className="h-4 w-4" />
                                <span className="sr-only">Enviar teste</span>
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => {
                                  setScheduleTime(nextQuarterHour());
                                  setScheduleTarget(c);
                                }}
                                data-testid={`schedule-btn-${c.id}`}
                              >
                                <Calendar className="h-4 w-4" />
                                <span className="sr-only">Agendar</span>
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setSendTarget(c)}
                                data-testid={`send-btn-${c.id}`}
                              >
                                <Send className="h-4 w-4" />
                                <span className="sr-only">Enviar</span>
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setDeleteTarget(c)}
                                data-testid={`delete-campanha-${c.id}`}
                              >
                                <Trash2 className="h-4 w-4" />
                                <span className="sr-only">Excluir</span>
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {total > PAGE_SIZE && (
                <div className="flex items-center justify-between px-4 py-3 border-t">
                  <p className="text-sm text-muted-foreground">
                    {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de{" "}
                    {total}
                  </p>
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="icon"
                      disabled={currentPage === 1}
                      onClick={() =>
                        setOffset(Math.max(0, offset - PAGE_SIZE))
                      }
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      disabled={currentPage >= totalPages}
                      onClick={() => setOffset(offset + PAGE_SIZE)}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ─── Create modal ──────────────────────────────────────────────── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg" data-testid="create-campanha-modal">
          <DialogHeader>
            <DialogTitle>Nova campanha</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 pt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="c-title">Título interno *</Label>
                <Input
                  id="c-title"
                  data-testid="campanha-title-input"
                  value={createForm.title}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, title: e.target.value })
                  }
                  disabled={create.isPending}
                  required
                />
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="c-subject">Assunto *</Label>
                <Input
                  id="c-subject"
                  data-testid="campanha-subject-input"
                  value={createForm.subject_line}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, subject_line: e.target.value })
                  }
                  disabled={create.isPending}
                  required
                />
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="c-preview">Pré-visualização</Label>
                <Input
                  id="c-preview"
                  data-testid="campanha-preview-input"
                  value={createForm.preview_text}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, preview_text: e.target.value })
                  }
                  disabled={create.isPending}
                  placeholder="Texto curto exibido nas caixas de entrada"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-from">Nome do remetente *</Label>
                <Input
                  id="c-from"
                  data-testid="campanha-from-input"
                  value={createForm.from_name}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, from_name: e.target.value })
                  }
                  disabled={create.isPending}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-reply">Email de resposta *</Label>
                <Input
                  id="c-reply"
                  type="email"
                  data-testid="campanha-reply-input"
                  value={createForm.reply_to}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, reply_to: e.target.value })
                  }
                  disabled={create.isPending}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label>Lista (opcional)</Label>
                <Select
                  value={createForm.segment_id || "none"}
                  onValueChange={(v) =>
                    setCreateForm({
                      ...createForm,
                      segment_id: v === "none" ? "" : v,
                    })
                  }
                  disabled={create.isPending}
                >
                  <SelectTrigger data-testid="campanha-segment-select">
                    <SelectValue placeholder="Toda a audiência" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Toda a audiência</SelectItem>
                    {segments?.items.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {s.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Template (opcional)</Label>
                <Select
                  value={createForm.template_id || "none"}
                  onValueChange={(v) =>
                    setCreateForm({
                      ...createForm,
                      template_id: v === "none" ? "" : v,
                    })
                  }
                  disabled={create.isPending}
                >
                  <SelectTrigger data-testid="campanha-template-select">
                    <SelectValue placeholder="Sem template" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Sem template</SelectItem>
                    {templates?.items.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setCreateOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={
                  !createForm.title.trim() ||
                  !createForm.subject_line.trim() ||
                  !createForm.from_name.trim() ||
                  !createForm.reply_to.trim() ||
                  create.isPending
                }
                data-testid="create-campanha-submit"
              >
                {create.isPending ? "Criando..." : "Criar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── Send confirm ─────────────────────────────────────────────── */}
      <AlertDialog
        open={!!sendTarget}
        onOpenChange={(open) => !open && setSendTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Enviar campanha?</AlertDialogTitle>
            <AlertDialogDescription>
              A campanha <strong>{sendTarget?.title}</strong> será enviada
              imediatamente para a audiência. Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleSend}
              data-testid="confirm-send-campanha"
            >
              {send.isPending ? "Enviando..." : "Enviar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ─── Schedule dialog ──────────────────────────────────────────── */}
      <Dialog
        open={!!scheduleTarget}
        onOpenChange={(open) => !open && setScheduleTarget(null)}
      >
        <DialogContent data-testid="schedule-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Agendar campanha
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSchedule} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="schedule-time">
                Data e hora (UTC, múltiplos de 15 min)
              </Label>
              <Input
                id="schedule-time"
                data-testid="schedule-time-input"
                type="datetime-local"
                value={scheduleTime}
                onChange={(e) => setScheduleTime(e.target.value)}
                disabled={schedule.isPending}
                step={900}
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setScheduleTarget(null)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={!scheduleTime || schedule.isPending}
                data-testid="schedule-submit"
              >
                {schedule.isPending ? "Agendando..." : "Agendar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── Unschedule confirm ───────────────────────────────────────── */}
      <AlertDialog
        open={!!unscheduleTarget}
        onOpenChange={(open) => !open && setUnscheduleTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancelar agendamento?</AlertDialogTitle>
            <AlertDialogDescription>
              A campanha <strong>{unscheduleTarget?.title}</strong> voltará para
              o status de rascunho.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleUnschedule}
              data-testid="confirm-unschedule"
            >
              {unschedule.isPending ? "Cancelando..." : "Cancelar agendamento"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ─── Delete confirm ───────────────────────────────────────────── */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir campanha?</AlertDialogTitle>
            <AlertDialogDescription>
              A campanha <strong>{deleteTarget?.title}</strong> será excluída
              permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="confirm-delete-campanha"
            >
              {remove.isPending ? "Excluindo..." : "Excluir"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ─── Send test dialog ─────────────────────────────────────────── */}
      <Dialog
        open={!!testTarget}
        onOpenChange={(open) => {
          if (!open) {
            setTestTarget(null);
            setTestEmails("");
          }
        }}
      >
        <DialogContent data-testid="send-test-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TestTube2 className="h-5 w-5" />
              Enviar email de teste
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSendTest} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="test-emails">
                Emails (separados por vírgula, máx. 10)
              </Label>
              <Input
                id="test-emails"
                data-testid="test-emails-input"
                value={testEmails}
                onChange={(e) => setTestEmails(e.target.value)}
                disabled={sendTest.isPending}
                placeholder="email1@ex.com, email2@ex.com"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setTestTarget(null);
                  setTestEmails("");
                }}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={!testEmails.trim() || sendTest.isPending}
                data-testid="send-test-submit"
              >
                {sendTest.isPending ? "Enviando..." : "Enviar teste"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function EmailCampanhas() {
  return (
    <MailchimpGate>
      <CampanhasContent />
    </MailchimpGate>
  );
}
