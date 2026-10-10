/**
 * Email Marketing · Contatos — the own-engine contact base.
 *
 *   GET|POST     /api/email-marketing/contacts
 *   PATCH|DELETE /api/email-marketing/contacts/{id}
 *   POST         /api/email-marketing/contacts/import
 *
 *   POST         /api/email-marketing/contacts/{id}/resend-confirmation
 *
 * CRUD is the canonical `<ResourceManager/>` organ; the CSV bulk import is the
 * one thing the organ cannot express, so it lives beside it as a dialog.
 * Double opt-in (P1b(d)): an "Opt-in" column badges contacts awaiting
 * confirmation, with a per-row "Reenviar confirmação" action; the import
 * dialog can require confirmation for every new address.
 *
 * Route: /email/contatos (`email_contatos_noc` status_pagina, migration 085).
 */
import { useState } from "react";
import { toast } from "sonner";
import { MailCheck, Sparkles, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { ResourceManager } from "@noctusai/lib/components";
import { AIIndicator } from "@noctusai/lib/design-system";
import { api } from "@/lib/api";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import {
  useEmAi,
  useEmContactMutations,
  type EmContact,
} from "@/hooks/useEmailMarketing";

const STATUS_LABEL: Record<string, string> = {
  active: "Ativo",
  unsubscribed: "Descadastrado",
  bounced: "Bounce",
  complained: "Reclamou",
};

/** Opt-in state badge. `not_required` shows nothing — no confirmation was asked. */
export function OptinBadge({ optin }: { optin: EmContact["email_optin"] | undefined }) {
  if (optin === "pending") {
    return (
      <Badge variant="outline" className="border-amber-500/50 text-amber-600" data-testid="optin-pending">
        Aguardando confirmação
      </Badge>
    );
  }
  if (optin === "confirmed") {
    return (
      <Badge variant="outline" className="border-green-500/50 text-green-600" data-testid="optin-confirmed">
        Confirmado
      </Badge>
    );
  }
  return <span className="text-muted-foreground">—</span>;
}

/** "Reenviar confirmação" for a contact still awaiting double opt-in. A
 * not-sent outcome (no Resend key, no FRONTEND_BASE_URL…) is shown as an
 * error with the backend's reason — never as success. */
export function ResendConfirmationAction({ contact }: { contact: EmContact }) {
  const { resendConfirmation } = useEmContactMutations();
  if (contact.email_optin !== "pending") return null;
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={resendConfirmation.isPending}
      data-testid="contatos-resend-confirmation"
      onClick={() =>
        resendConfirmation.mutate(contact.id, {
          onSuccess: (res) => {
            const outcome = res?.data?.confirmation;
            if (outcome?.sent) toast.success(`Confirmação reenviada para ${contact.email}.`);
            else
              toast.error("Confirmação não enviada.", {
                description: outcome?.reason ?? undefined,
              });
          },
          onError: (err: unknown) =>
            toast.error("Erro ao reenviar confirmação.", {
              description: err instanceof Error ? err.message : undefined,
            }),
        })
      }
    >
      <MailCheck className="mr-1 h-4 w-4" />
      {resendConfirmation.isPending ? "Reenviando…" : "Reenviar confirmação"}
    </Button>
  );
}

/**
 * Parse a pasted CSV/one-per-line block into contact payloads.
 *
 * Accepts `email`, `email,nome`, or `email,nome,empresa`. Returns the rows it
 * could read AND the line numbers it could not — the caller shows both, so a
 * malformed line is never silently dropped.
 */
export function parseContactsBlock(raw: string): {
  contacts: Array<{ email: string; nome?: string; empresa?: string }>;
  rejected: number[];
} {
  const contacts: Array<{ email: string; nome?: string; empresa?: string }> = [];
  const rejected: number[] = [];
  raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .forEach((line, i) => {
      if (!line) return;
      const [email, nome, empresa] = line.split(",").map((p) => p?.trim());
      if (!email || !email.includes("@")) {
        rejected.push(i + 1);
        return;
      }
      contacts.push({
        email,
        ...(nome ? { nome } : {}),
        ...(empresa ? { empresa } : {}),
      });
    });
  return { contacts, rejected };
}

function ImportDialog() {
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState("");
  const [doubleOptIn, setDoubleOptIn] = useState(false);
  const { importMany } = useEmContactMutations();

  function submit() {
    const { contacts, rejected } = parseContactsBlock(raw);
    if (contacts.length === 0) {
      toast.error("Nenhum e-mail válido encontrado.");
      return;
    }
    importMany.mutate({ contacts, doubleOptIn }, {
      onSuccess: (res) => {
        toast.success(`${contacts.length} contato(s) importado(s).`, {
          description: rejected.length
            ? `Linhas ignoradas: ${rejected.join(", ")}`
            : undefined,
        });
        const confirmation = res?.data?.confirmation;
        if (confirmation && confirmation.failed > 0) {
          toast.error(
            `${confirmation.failed} e-mail(s) de confirmação não enviado(s).`,
            { description: confirmation.reason ?? undefined },
          );
        }
        setOpen(false);
        setRaw("");
        setDoubleOptIn(false);
      },
      onError: (err: unknown) =>
        toast.error("Erro ao importar contatos.", {
          description: err instanceof Error ? err.message : undefined,
        }),
    });
  }

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        data-testid="contatos-import-open"
      >
        <Upload className="mr-2 h-4 w-4" />
        Importar
      </Button>
      <Dialog open={open} onOpenChange={(o: boolean) => !o && setOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Importar contatos</DialogTitle>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="import-raw">
              Um por linha — <code>email</code>, <code>email,nome</code> ou{" "}
              <code>email,nome,empresa</code>
            </Label>
            <Textarea
              id="import-raw"
              rows={10}
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              placeholder={"ana@exemplo.com,Ana Lima,Acme\nbruno@exemplo.com"}
              data-testid="contatos-import-textarea"
            />
          </div>
          <div className="flex items-start gap-2">
            <Checkbox
              id="import-double-optin"
              checked={doubleOptIn}
              onCheckedChange={(v) => setDoubleOptIn(v === true)}
              data-testid="contatos-import-double-optin"
            />
            <div className="space-y-0.5">
              <Label htmlFor="import-double-optin">Exigir confirmação (double opt-in)</Label>
              <p className="text-xs text-muted-foreground">
                Cada novo contato recebe um e-mail de confirmação e só entra nos envios
                depois de confirmar.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={submit}
              disabled={importMany.isPending || raw.trim().length === 0}
              data-testid="contatos-import-submit"
            >
              {importMany.isPending ? "Importando…" : "Importar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

interface SegmentRow {
  ref_id: string;
  label: string;
  chip?: string | null;
}

/** Group persisted per-contact segment rows into `{label → count}` (desc). */
export function summarizeSegments(
  rows: SegmentRow[],
): Array<{ label: string; count: number }> {
  const counts = new Map<string, number>();
  for (const r of rows) counts.set(r.label, (counts.get(r.label) ?? 0) + 1);
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

/** Human message for a failed segmentation call; 403 = consent not granted. */
export function segmentErrorMessage(err: unknown): string {
  const status = (err as { status?: number | null })?.status;
  if (status === 403) {
    return "Segmentação por IA não autorizada: ative o consentimento “email_marketing.segment_contacts” nas configurações de IA.";
  }
  if (status === 429) return "Muitas tentativas — aguarde um minuto.";
  return err instanceof Error ? err.message : "Erro ao segmentar contatos.";
}

function SegmentButton() {
  const qc = useQueryClient();
  const { segmentContacts } = useEmAi();
  const result = segmentContacts.data?.data as
    | { persisted?: SegmentRow[]; segmented?: number }
    | undefined;
  const segments = summarizeSegments(result?.persisted ?? []);

  function run() {
    segmentContacts.mutate(
      {},
      {
        onSuccess: (res) => {
          const n = (res?.data as { segmented?: number } | undefined)?.segmented ?? 0;
          qc.invalidateQueries({ queryKey: ["ai_outputs"] });
          if (n === 0) toast.info("Nenhum contato ativo para segmentar.");
          else toast.success(`Segmentação concluída — ${n} contato(s) classificados.`);
        },
        onError: (err: unknown) =>
          toast.error("Erro ao segmentar contatos.", {
            description: segmentErrorMessage(err),
          }),
      },
    );
  }

  return (
    <div className="flex flex-col items-end gap-2" data-testid="contatos-segment">
      <Button
        variant="outline"
        onClick={run}
        disabled={segmentContacts.isPending}
        data-testid="contatos-segment-run"
      >
        <Sparkles className="mr-2 h-4 w-4" />
        {segmentContacts.isPending ? "Segmentando…" : "Segmentar com IA"}
      </Button>
      {segmentContacts.isError && (
        <p
          role="alert"
          className="max-w-md text-right text-sm text-destructive"
          data-testid="contatos-segment-error"
        >
          {segmentErrorMessage(segmentContacts.error)}
        </p>
      )}
      {segmentContacts.isSuccess && segments.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="contatos-segment-empty">
          Nenhum contato ativo para segmentar.
        </p>
      )}
      {segments.length > 0 && (
        <ul
          className="flex flex-wrap justify-end gap-2"
          data-testid="contatos-segment-summary"
        >
          {segments.map((s) => (
            <li
              key={s.label}
              className="rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-xs"
              data-testid="contatos-segment-chip"
            >
              {s.label} · {s.count}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function EmailContatos() {
  return (
    <div className="flex flex-col gap-4 p-6" data-testid="email-contatos-page">
      <div className="flex items-start justify-end gap-2">
        <SegmentButton />
        <ImportDialog />
      </div>

      <ResourceManager<EmContact>
        title="Contatos"
        description="Base de contatos do motor de envio próprio."
        api={api}
        apiPath="/api/email-marketing/contacts"
        singularName="Contato"
        emptyMessage="Nenhum contato ainda — cadastre um ou importe uma lista."
        columns={[
          { key: "email", header: "E-mail" },
          { key: "nome", header: "Nome", render: (r) => r.nome ?? "—" },
          { key: "empresa", header: "Empresa", render: (r) => r.empresa ?? "—" },
          {
            key: "segmento",
            header: "Segmento (IA)",
            render: (r) => (
              <AIIndicator refType="contact" refId={r.id} hideIcon />
            ),
          },
          {
            key: "status",
            header: "Status",
            render: (r) => STATUS_LABEL[r.status] ?? r.status,
          },
          {
            key: "email_optin",
            header: "Opt-in",
            render: (r) => <OptinBadge optin={r.email_optin} />,
          },
        ]}
        rowActions={(r) => <ResendConfirmationAction contact={r} />}
        fields={[
          { name: "email", label: "E-mail", type: "email", required: true },
          { name: "nome", label: "Nome" },
          { name: "telefone", label: "Telefone" },
          { name: "empresa", label: "Empresa" },
        ]}
      />
    </div>
  );
}
