/**
 * Clientes — page listing all clients as cards.
 *
 * Each card opens the ClienteModal (tabbed: Contas | Chat).
 *
 * Create flow: "Novo cliente" button → inline form in an AlertDialog-style panel.
 *
 * States: loading skeleton / empty with CTA / error / success (cards grid).
 *
 * Route: /clientes (registered in App.tsx lazy routes + status_pagina via migration 018).
 */
import { useState } from "react";
import {
  AlertCircle,
  Building2,
  Loader2,
  MessageSquare,
  Plus,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import { ClienteModal } from "@/components/ClienteModal";
import {
  useClients,
  useCreateClient,
  type Client,
  type CreateClientInput,
} from "@/hooks/useClients";

// ─── Create dialog ────────────────────────────────────────────────────────────

function CreateClientDialog({ onCreated }: { onCreated?: (c: Client) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [kind, setKind] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);

  const createClient = useCreateClient();

  function deriveSlug(n: string): string {
    return n
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64);
  }

  function handleNameChange(v: string) {
    setName(v);
    if (!slugTouched) setSlug(deriveSlug(v));
  }

  function resetForm() {
    setName("");
    setSlug("");
    setKind("");
    setNotes("");
    setError(null);
    setSlugTouched(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const trimmedName = name.trim();
    const trimmedSlug = slug.trim();
    if (!trimmedName) { setError("Nome é obrigatório."); return; }
    if (!trimmedSlug) { setError("Slug é obrigatório."); return; }

    const payload: CreateClientInput = {
      name: trimmedName,
      slug: trimmedSlug,
    };
    if (kind) payload.kind = kind;
    if (notes.trim()) payload.notes = notes.trim();

    try {
      const client = await createClient.mutateAsync(payload);
      resetForm();
      setOpen(false);
      onCreated?.(client);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao criar cliente.");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) resetForm();
        setOpen(o);
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" data-testid="create-client-btn">
          <Plus className="mr-1.5 h-4 w-4" /> Novo cliente
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Novo cliente</DialogTitle>
          <DialogDescription>
            Crie um cliente para agrupar suas contas de integração.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          <div className="space-y-1.5">
            <Label htmlFor="new-clt-name">Nome *</Label>
            <Input
              id="new-clt-name"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="Ex: Empresa ABC"
              autoFocus
              data-testid="new-client-name"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-clt-slug">Slug *</Label>
            <Input
              id="new-clt-slug"
              value={slug}
              onChange={(e) => { setSlugTouched(true); setSlug(e.target.value); }}
              placeholder="empresa-abc"
              data-testid="new-client-slug"
            />
            <p className="text-[10px] text-muted-foreground">
              Identificador único. Derivado do nome, editável.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-clt-kind">Tipo</Label>
            <Select value={kind || "__none__"} onValueChange={(v) => setKind(v === "__none__" ? "" : v)}>
              <SelectTrigger id="new-clt-kind">
                <SelectValue placeholder="Tipo..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Nenhum</SelectItem>
                <SelectItem value="empresa">Empresa</SelectItem>
                <SelectItem value="pessoa_fisica">Pessoa física</SelectItem>
                <SelectItem value="parceiro">Parceiro</SelectItem>
                <SelectItem value="outro">Outro</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-clt-notes">Notas</Label>
            <Textarea
              id="new-clt-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Observações opcionais..."
              className="resize-none h-16"
            />
          </div>
          {error && (
            <p className="text-xs text-destructive flex items-center gap-1" data-testid="create-error">
              <AlertCircle className="h-3 w-3" /> {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => { resetForm(); setOpen(false); }}
              disabled={createClient.isPending}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={createClient.isPending}>
              {createClient.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              Criar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Client card ──────────────────────────────────────────────────────────────

function ClientCard({
  client,
  onOpen,
}: {
  client: Client;
  onOpen: (c: Client, tab: "contas" | "chat") => void;
}) {
  return (
    <Card
      className="group hover:shadow-md transition-shadow cursor-pointer"
      onClick={() => onOpen(client, "contas")}
      data-testid="client-card"
      role="button"
      aria-label={`Abrir cliente ${client.name}`}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
            <CardTitle className="text-sm font-semibold truncate">{client.name}</CardTitle>
          </div>
          {client.kind && (
            <span className="text-[10px] bg-secondary text-secondary-foreground rounded px-1.5 py-0.5 flex-shrink-0">
              {client.kind}
            </span>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground truncate pl-6">
          {client.slug}
        </p>
      </CardHeader>
      {client.notes && (
        <CardContent className="pt-0 pb-3">
          <p className="text-xs text-muted-foreground line-clamp-2 pl-6">{client.notes}</p>
        </CardContent>
      )}
      {/* Quick-action footer */}
      <div className="flex border-t divide-x">
        <button
          type="button"
          className="flex-1 py-1.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors flex items-center justify-center gap-1"
          onClick={(e) => { e.stopPropagation(); onOpen(client, "contas"); }}
          aria-label="Abrir contas"
        >
          <Users className="h-3.5 w-3.5" /> Contas
        </button>
        <button
          type="button"
          className="flex-1 py-1.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors flex items-center justify-center gap-1"
          onClick={(e) => { e.stopPropagation(); onOpen(client, "chat"); }}
          aria-label="Abrir chat"
          data-testid="client-chat-btn"
        >
          <MessageSquare className="h-3.5 w-3.5" /> Chat
        </button>
      </div>
    </Card>
  );
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function ClientsSkeleton() {
  return (
    <div
      className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
      data-testid="clients-skeleton"
    >
      {[1, 2, 3].map((i) => (
        <div key={i} className="border rounded-lg p-4 space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 w-48" />
        </div>
      ))}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ClientesPage() {
  const { data: clients = [], isLoading, isError, error } = useClients();

  const [modalClient, setModalClient] = useState<Client | null>(null);
  const [modalTab, setModalTab] = useState<"contas" | "chat">("contas");

  function handleOpen(client: Client, tab: "contas" | "chat") {
    setModalClient(client);
    setModalTab(tab);
  }

  return (
    <div className="flex flex-col gap-6 p-6" data-testid="clientes-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Clientes</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Gerencie clientes e suas contas de integração.
          </p>
        </div>
        <CreateClientDialog
          onCreated={(client) => handleOpen(client, "contas")}
        />
      </div>

      {/* Content */}
      {isLoading ? (
        <ClientsSkeleton />
      ) : isError ? (
        <div
          className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground"
          data-testid="clientes-error"
        >
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm font-medium">Erro ao carregar clientes</p>
          <p className="text-xs">
            {error instanceof Error ? error.message : "Tente novamente mais tarde."}
          </p>
        </div>
      ) : clients.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground"
          data-testid="clientes-empty"
        >
          <Users className="h-10 w-10 opacity-20" />
          <p className="text-sm font-medium">Nenhum cliente cadastrado</p>
          <p className="text-xs text-center max-w-xs">
            Crie um cliente para agrupar suas conexões e integrações por conta.
          </p>
          <CreateClientDialog />
        </div>
      ) : (
        <div
          className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="clients-grid"
        >
          {clients.map((client) => (
            <ClientCard key={client.id} client={client} onOpen={handleOpen} />
          ))}
        </div>
      )}

      {/* ClienteModal */}
      {modalClient && (
        <ClienteModal
          client={modalClient}
          open={!!modalClient}
          onClose={() => setModalClient(null)}
          defaultTab={modalTab}
        />
      )}
    </div>
  );
}
