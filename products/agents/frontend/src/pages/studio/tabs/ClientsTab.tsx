/**
 * Clientes tab — Agent Studio CONTRACT.md §D2, §G "Clientes".
 *
 * Client ("client brain") list/editor: `resumo` markdown + typed entries
 * CRUD (`marca`/`publico`/`posicionamento`/`trava`/`decisao`/`aprendizado`/
 * `evidencia`/`nota`). Page-scoped CRUD: list, create, edit and entry CRUD
 * all live on this one tab. Admin-only writes hidden for members (server
 * enforces via `require_admin`, §H.1); any member can read clients
 * (needed for the Conversar tab's client selector).
 */
import { useState, type FormEvent } from "react";
import { Plus, Users } from "lucide-react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  PageSkeleton,
  Select,
  Textarea,
} from "@noctusai/lib/design-system";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import {
  useClient,
  useClients,
  useCreateClient,
  useCreateClientEntry,
  useDeleteClientEntry,
  useUpdateClient,
  useUpdateClientEntry,
} from "@/hooks/studio/useClients";
import type { ClientEntryTipo } from "@/api/studio/types";

const ENTRY_TIPOS: ClientEntryTipo[] = [
  "marca",
  "publico",
  "posicionamento",
  "trava",
  "decisao",
  "aprendizado",
  "evidencia",
  "nota",
];

const ENTRY_LABEL: Record<ClientEntryTipo, string> = {
  marca: "Marca",
  publico: "Público",
  posicionamento: "Posicionamento",
  trava: "Trava",
  decisao: "Decisão",
  aprendizado: "Aprendizado",
  evidencia: "Evidência",
  nota: "Nota",
};

function NewClientForm({ agentKey, onDone }: { agentKey: string; onDone: (id: string) => void }) {
  const [slug, setSlug] = useState("");
  const [nome, setNome] = useState("");
  const [resumo, setResumo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useCreateClient(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const client = await create.mutateAsync({ slug, nome, resumo: resumo || undefined });
      toast.success("Cliente criado.");
      onDone(client.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-md border border-border p-3" data-testid="clients-new-form">
      <FormError message={error} />
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Slug" required>
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} required />
        </Field>
        <Field label="Nome" required>
          <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
        </Field>
      </div>
      <Field label="Resumo (marca, público, posicionamento, oferta)">
        <Textarea rows={3} value={resumo} onChange={(e) => setResumo(e.target.value)} />
      </Field>
      <Button type="submit" variant="primary" size="sm" disabled={create.isPending}>
        Criar cliente
      </Button>
    </form>
  );
}

function EntryForm({ agentKey, clientId, onDone }: { agentKey: string; clientId: string; onDone: () => void }) {
  const [tipo, setTipo] = useState<ClientEntryTipo>("marca");
  const [titulo, setTitulo] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useCreateClientEntry(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({ clientId, entry: { tipo, titulo, conteudo } });
      setTitulo("");
      setConteudo("");
      toast.success("Entrada adicionada.");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-md border border-border p-2" data-testid="client-entry-form">
      <FormError message={error} />
      <div className="grid gap-2 sm:grid-cols-[140px_1fr]">
        <Select value={tipo} onChange={(e) => setTipo(e.target.value as ClientEntryTipo)}>
          {ENTRY_TIPOS.map((t) => (
            <option key={t} value={t}>
              {ENTRY_LABEL[t]}
            </option>
          ))}
        </Select>
        <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Título" required />
      </div>
      <Textarea rows={2} value={conteudo} onChange={(e) => setConteudo(e.target.value)} placeholder="Conteúdo" required />
      <Button type="submit" size="sm" variant="outline" disabled={create.isPending}>
        <Plus className="mr-1.5 h-3.5 w-3.5" />
        Adicionar entrada
      </Button>
    </form>
  );
}

function ClientDetail({ agentKey, clientId, isAdmin }: { agentKey: string; clientId: string; isAdmin: boolean }) {
  const { data: client, showSkeleton, isError } = useClient(agentKey, clientId);
  const updateClient = useUpdateClient(agentKey);
  const updateEntry = useUpdateClientEntry(agentKey);
  const deleteEntry = useDeleteClientEntry(agentKey);
  const [resumo, setResumo] = useState("");
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  if (client && loadedFor !== client.id) {
    setResumo(client.resumo);
    setLoadedFor(client.id);
  }

  if (showSkeleton) return <PageSkeleton />;
  if (isError || !client) return <ErrorState message="Erro ao carregar cliente." />;

  const grouped = ENTRY_TIPOS.map((tipo) => ({
    tipo,
    entries: client.entradas.filter((e) => e.tipo === tipo && e.status === "ativo"),
  })).filter((g) => g.entries.length > 0);

  return (
    <Card className="space-y-3" data-testid="client-detail">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-foreground">{client.nome}</h3>
        <Badge variant={client.ativo ? "default" : "muted"}>{client.ativo ? "ativo" : "inativo"}</Badge>
      </div>
      <Field label="Resumo">
        <Textarea rows={4} value={resumo} onChange={(e) => setResumo(e.target.value)} disabled={!isAdmin} />
      </Field>
      {isAdmin && (
        <Button
          size="sm"
          variant="primary"
          disabled={updateClient.isPending}
          onClick={async () => {
            try {
              await updateClient.mutateAsync({ clientId: client.id, patch: { resumo } });
              toast.success("Cliente salvo.");
            } catch (err) {
              toast.error(errorMessage(err));
            }
          }}
        >
          Salvar resumo
        </Button>
      )}

      <div className="space-y-3 border-t border-border pt-3">
        {grouped.length === 0 ? (
          <EmptyState message="Nenhuma entrada ainda." />
        ) : (
          grouped.map((g) => (
            <div key={g.tipo} className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{ENTRY_LABEL[g.tipo]}</p>
              <ul className="space-y-1">
                {g.entries.map((entry) => (
                  <li key={entry.id} className="flex items-start justify-between gap-2 rounded-md border border-border p-2 text-xs">
                    <div>
                      <p className="font-medium text-foreground">{entry.titulo}</p>
                      <p className="text-muted-foreground">{entry.conteudo}</p>
                    </div>
                    {isAdmin && (
                      <div className="flex flex-shrink-0 gap-2">
                        <button
                          type="button"
                          className="text-muted-foreground hover:underline"
                          onClick={() => updateEntry.mutate({ clientId, entryId: entry.id, patch: { status: "arquivado" } })}
                        >
                          Arquivar
                        </button>
                        <button
                          type="button"
                          className="text-destructive hover:underline"
                          onClick={() => deleteEntry.mutate({ clientId, entryId: entry.id })}
                        >
                          Excluir
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
        {isAdmin && <EntryForm agentKey={agentKey} clientId={clientId} onDone={() => undefined} />}
      </div>
    </Card>
  );
}

export default function ClientsTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const { data: clients, showSkeleton, isError, error } = useClients(agentKey);
  const [selected, setSelected] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  if (showSkeleton) return <PageSkeleton />;
  if (isError) return <ErrorState message={errorMessage(error)} />;

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Users className="h-4 w-4" /> Clientes
          </p>
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={() => setShowNew((v) => !v)} data-testid="clients-new-toggle">
              <Plus className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>

        {isAdmin && showNew && (
          <NewClientForm
            agentKey={agentKey}
            onDone={(id) => {
              setSelected(id);
              setShowNew(false);
            }}
          />
        )}

        {!clients || clients.length === 0 ? (
          <EmptyState message="Nenhum cliente ainda." />
        ) : (
          <ul className="space-y-1">
            {clients.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelected(c.id)}
                  data-testid={`clients-row-${c.slug}`}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-accent ${
                    selected === c.id ? "bg-accent font-medium" : "text-foreground"
                  }`}
                >
                  <span className="truncate">{c.nome}</span>
                  <span className="text-xs text-muted-foreground">{c.total_entradas}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        {selected ? (
          <ClientDetail agentKey={agentKey} clientId={selected} isAdmin={isAdmin} />
        ) : (
          <EmptyState message="Selecione um cliente." />
        )}
      </div>
    </div>
  );
}
