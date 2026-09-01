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
import { Upload } from "lucide-react";

import { ResourceManager } from "@noctusai/lib/components";
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

export default function EmailContatos() {
  return (
    <div className="flex flex-col gap-4 p-6" data-testid="email-contatos-page">
      <div className="flex items-center justify-end">
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
