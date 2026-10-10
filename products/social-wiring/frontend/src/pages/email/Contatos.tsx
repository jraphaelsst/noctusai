/**
 * Email Marketing · Contatos — the own-engine contact base.
 *
 *   GET|POST     /api/email-marketing/contacts
 *   PATCH|DELETE /api/email-marketing/contacts/{id}
 *   POST         /api/email-marketing/contacts/import
 *
 * CRUD is the canonical `<ResourceManager/>` organ; the CSV bulk import is the
 * one thing the organ cannot express, so it lives beside it as a dialog.
 *
 * Route: /email/contatos (`email_contatos_noc` status_pagina, migration 085).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Sparkles, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { ResourceManager } from "@noctusai/lib/components";
import { AIIndicator } from "@noctusai/lib/design-system";
import { api } from "@/lib/api";

import { Button } from "@/components/ui/button";
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
  const { importMany } = useEmContactMutations();

  function submit() {
    const { contacts, rejected } = parseContactsBlock(raw);
    if (contacts.length === 0) {
      toast.error("Nenhum e-mail válido encontrado.");
      return;
    }
    importMany.mutate(contacts, {
      onSuccess: () => {
        toast.success(`${contacts.length} contato(s) importado(s).`, {
          description: rejected.length
            ? `Linhas ignoradas: ${rejected.join(", ")}`
            : undefined,
        });
        setOpen(false);
        setRaw("");
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
        ]}
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
