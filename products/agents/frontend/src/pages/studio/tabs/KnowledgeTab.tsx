/**
 * Conhecimento tab — Agent Studio CONTRACT.md §D3, §G "Conhecimento".
 *
 * Collections sidebar + documents table (search `q`, tipo filter) + a
 * document viewer/editor (markdown textarea, provenance fields, revision
 * list) + a search playground calling `knowledge/search` — "shows exactly
 * what `kb_buscar` would return" (§G). Page-scoped CRUD: this one tab both
 * lists AND creates collections/documents
 * (`KB § PATTERNS/frontend/product-internal-wiring.md`). Admin-only writes
 * hidden for members (server also enforces via `require_admin`, §H.1).
 */
import { useMemo, useState, type FormEvent } from "react";
import { BookOpen, FilePlus2, FolderPlus, History, Pencil, Save, Search, Upload } from "lucide-react";
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
import { KnowledgeUploadDialog } from "@/components/studio/KnowledgeUploadDialog";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import {
  useCreateDocument,
  useCreateKnowledgeCollection,
  useDocument,
  useDocumentRevisions,
  useDocuments,
  useKnowledgeCollections,
  useKnowledgeSearch,
  useUpdateDocument,
  useUpdateKnowledgeCollection,
} from "@/hooks/studio/useKnowledge";
import type { DocumentTipo, KnowledgeCollection, Provenance } from "@/api/studio/types-ke";
import { DOCUMENT_TIPOS } from "@/api/studio/types-ke";

const PROVENANCE_FIELDS: { key: keyof Provenance; label: string }[] = [
  { key: "autor", label: "Autor" },
  { key: "origem", label: "Origem" },
  { key: "referencia", label: "Referência" },
  { key: "pagina", label: "Página" },
  { key: "licenca", label: "Licença" },
  { key: "notas", label: "Notas" },
];

function emptyProvenance(): Provenance {
  return { autor: "", origem: "", referencia: "", pagina: "", licenca: "", notas: "" };
}

const PAGE_SIZE = 20;

function NewCollectionForm({ agentKey, onDone }: { agentKey: string; onDone: () => void }) {
  const [slug, setSlug] = useState("");
  const [nome, setNome] = useState("");
  const [tag, setTag] = useState("");
  const [descricao, setDescricao] = useState("");
  const [ordem, setOrdem] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const create = useCreateKnowledgeCollection(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({ slug, nome, tag: tag || null, descricao, ordem });
      toast.success("Coleção criada.");
      setSlug("");
      setNome("");
      setTag("");
      setDescricao("");
      setOrdem(0);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border-b border-border pb-3" data-testid="knowledge-new-collection-form">
      <FormError message={error} />
      <Field label="Slug" required>
        <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="audience" required />
      </Field>
      <Field label="Nome" required>
        <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Audiência" required />
      </Field>
      <Field label="Tag (proveniência, ex.: AU)">
        <Input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="AU" maxLength={16} />
      </Field>
      <Field label="Descrição">
        <Textarea rows={2} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
      </Field>
      <Field label="Ordem (posição no “# Base de conhecimento” compilado)">
        <Input type="number" value={ordem} onChange={(e) => setOrdem(Number(e.target.value))} />
      </Field>
      <Button type="submit" size="sm" variant="primary" disabled={create.isPending}>
        <FolderPlus className="mr-1.5 h-3.5 w-3.5" />
        Criar coleção
      </Button>
    </form>
  );
}

function EditCollectionForm({ agentKey, collection, onDone }: { agentKey: string; collection: KnowledgeCollection; onDone: () => void }) {
  const [nome, setNome] = useState(collection.nome);
  const [tag, setTag] = useState(collection.tag ?? "");
  const [descricao, setDescricao] = useState(collection.descricao);
  const [ordem, setOrdem] = useState(collection.ordem);
  const [error, setError] = useState<string | null>(null);
  const update = useUpdateKnowledgeCollection(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({ collectionId: collection.id, patch: { nome, tag: tag || null, descricao, ordem } });
      toast.success("Coleção salva.");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-md border border-border p-3" data-testid="knowledge-edit-collection-form">
      <FormError message={error} />
      <Field label="Nome" required>
        <Input value={nome} onChange={(e) => setNome(e.target.value)} required />
      </Field>
      <Field label="Tag (proveniência, ex.: AU)">
        <Input value={tag} onChange={(e) => setTag(e.target.value)} maxLength={16} />
      </Field>
      <Field label="Descrição">
        <Textarea rows={2} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
      </Field>
      <Field label="Ordem (posição no “# Base de conhecimento” compilado)">
        <Input type="number" value={ordem} onChange={(e) => setOrdem(Number(e.target.value))} />
      </Field>
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" size="sm" variant="primary" disabled={update.isPending}>
          Salvar coleção
        </Button>
      </div>
    </form>
  );
}

function DocumentDetail({ agentKey, docId, isAdmin }: { agentKey: string; docId: string; isAdmin: boolean }) {
  const { data: doc, showSkeleton, isError, error } = useDocument(agentKey, docId);
  const { data: revisions } = useDocumentRevisions(agentKey, docId);
  const update = useUpdateDocument(agentKey, docId);
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState<DocumentTipo>("fonte");
  const [ativo, setAtivo] = useState(true);
  const [conteudo, setConteudo] = useState("");
  const [resumo, setResumo] = useState("");
  const [proveniencia, setProveniencia] = useState<Provenance>(emptyProvenance());
  const [motivo, setMotivo] = useState("");
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  if (doc && loadedFor !== doc.id) {
    setTitulo(doc.titulo);
    setTipo(doc.tipo);
    setAtivo(doc.ativo);
    setConteudo(doc.conteudo);
    setResumo(doc.resumo ?? "");
    setProveniencia({ ...emptyProvenance(), ...doc.proveniencia });
    setLoadedFor(doc.id);
  }

  async function handleSave() {
    setSaveError(null);
    const provenienciaPayload = Object.fromEntries(
      Object.entries(proveniencia).filter(([, v]) => !!v),
    ) as Provenance;
    try {
      await update.mutateAsync({
        titulo,
        tipo,
        ativo,
        conteudo,
        resumo,
        proveniencia: provenienciaPayload,
        motivo: motivo || undefined,
      });
      toast.success("Documento salvo.");
      setMotivo("");
    } catch (err) {
      setSaveError(errorMessage(err));
    }
  }

  if (showSkeleton) return <PageSkeleton />;
  if (isError) return <ErrorState message={errorMessage(error)} />;
  if (!doc) return null;

  return (
    <Card className="space-y-3" data-testid="knowledge-document-detail">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-foreground">{doc.titulo}</h3>
          <p className="text-xs text-muted-foreground">
            {doc.slug} · {doc.chars.toLocaleString("pt-BR")} caracteres
          </p>
        </div>
        <Badge variant={doc.ativo ? "default" : "muted"}>{doc.ativo ? "ativo" : "arquivado"}</Badge>
      </div>

      <FormError message={saveError} />

      <div className="grid gap-2 sm:grid-cols-[1fr_160px]">
        <Field label="Título">
          <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} disabled={!isAdmin} data-testid="knowledge-document-titulo" />
        </Field>
        <Field label="Tipo">
          <Select value={tipo} onChange={(e) => setTipo(e.target.value as DocumentTipo)} disabled={!isAdmin} data-testid="knowledge-document-tipo">
            {DOCUMENT_TIPOS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {isAdmin && (
        <label className="flex items-center gap-1.5 text-xs text-foreground">
          <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} data-testid="knowledge-document-ativo" />
          Ativo (desmarque para arquivar — não há exclusão de documentos, apenas arquivamento)
        </label>
      )}

      <div className="grid gap-2 rounded-md border border-border bg-muted/30 p-2 sm:grid-cols-3" data-testid="knowledge-document-provenance">
        {PROVENANCE_FIELDS.map(({ key, label }) => (
          <Field key={key} label={label}>
            <Input
              value={proveniencia[key] ?? ""}
              onChange={(e) => setProveniencia((p) => ({ ...p, [key]: e.target.value }))}
              disabled={!isAdmin}
              data-testid={`knowledge-provenance-${key}`}
            />
          </Field>
        ))}
      </div>

      <Field label="Resumo">
        <Textarea rows={2} value={resumo} onChange={(e) => setResumo(e.target.value)} disabled={!isAdmin} />
      </Field>
      <Field label="Conteúdo (markdown)">
        <Textarea
          rows={16}
          monospace
          value={conteudo}
          onChange={(e) => setConteudo(e.target.value)}
          disabled={!isAdmin}
          data-testid="knowledge-document-content"
        />
      </Field>
      <p className="text-xs text-muted-foreground">{conteudo.length.toLocaleString("pt-BR")} caracteres</p>

      {isAdmin && (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="Motivo da alteração (opcional)">
              <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Corrige dado de fonte" />
            </Field>
          </div>
          <Button variant="primary" onClick={handleSave} disabled={update.isPending} data-testid="knowledge-document-save">
            <Save className="mr-1.5 h-3.5 w-3.5" />
            Salvar
          </Button>
        </div>
      )}

      {revisions && revisions.length > 0 && (
        <div className="space-y-1 border-t border-border pt-2">
          <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
            <History className="h-3.5 w-3.5" /> Revisões
          </p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {revisions.map((r) => (
              <li key={r.id}>
                {new Date(r.created_at).toLocaleString("pt-BR")} — {r.op}
                {r.motivo ? ` — ${r.motivo}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function SearchPlayground({ agentKey }: { agentKey: string }) {
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const { data: results, showSkeleton, isError } = useKnowledgeSearch(agentKey, q);

  return (
    <Card className="space-y-3" data-testid="knowledge-search-playground">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        <Search className="h-4 w-4" /> Testar busca (o que <code>kb_buscar</code> devolveria)
      </p>
      <div className="flex gap-2">
        <Input
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && setQ(qInput.trim())}
          placeholder="Consulta…"
        />
        <Button variant="outline" onClick={() => setQ(qInput.trim())}>
          Buscar
        </Button>
      </div>
      {q && showSkeleton ? (
        <p className="text-xs text-muted-foreground">Buscando…</p>
      ) : q && isError ? (
        <ErrorState message="Erro ao buscar." />
      ) : q && (!results || results.length === 0) ? (
        <EmptyState message="Nenhum resultado." />
      ) : (
        <ul className="space-y-2">
          {(results ?? []).map((r) => (
            <li key={r.doc_id} className="rounded-md border border-border p-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">{r.titulo}</span>
                {r.tag && <Badge variant="outline">{r.tag}</Badge>}
                <span className="text-muted-foreground">{r.colecao}</span>
              </div>
              <p className="mt-1 text-muted-foreground">{r.trecho}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function KnowledgeTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const { data: collections, showSkeleton, isError, error } = useKnowledgeCollections(agentKey);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [editingCollectionId, setEditingCollectionId] = useState<string | null>(null);
  const [qInput, setQInput] = useState("");
  const [filters, setFilters] = useState<{ q?: string; tipo?: DocumentTipo | ""; page: number }>({ page: 1 });
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [showNewDoc, setShowNewDoc] = useState(false);
  const [showUpload, setShowUpload] = useState(false);

  const activeCollectionId = selectedCollection ?? collections?.[0]?.id ?? null;

  const { data: docsPage, showSkeleton: docsLoading, isError: docsError } = useDocuments(agentKey, activeCollectionId, {
    q: filters.q,
    tipo: filters.tipo,
    page: filters.page,
    page_size: PAGE_SIZE,
  });
  const createDoc = useCreateDocument(agentKey, activeCollectionId ?? "");

  const totalPages = useMemo(() => (docsPage ? Math.max(1, Math.ceil(docsPage.total / PAGE_SIZE)) : 1), [docsPage]);

  if (showSkeleton) return <PageSkeleton />;
  if (isError) return <ErrorState message={errorMessage(error)} />;

  return (
    <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
      <div className="space-y-3">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <BookOpen className="h-4 w-4" /> Coleções
        </p>
        {!collections || collections.length === 0 ? (
          <EmptyState message="Nenhuma coleção ainda." />
        ) : (
          <ul className="space-y-1">
            {collections.map((c) =>
              isAdmin && editingCollectionId === c.id ? (
                <li key={c.id}>
                  <EditCollectionForm agentKey={agentKey} collection={c} onDone={() => setEditingCollectionId(null)} />
                </li>
              ) : (
                <li key={c.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCollection(c.id);
                      setSelectedDoc(null);
                      setFilters({ page: 1 });
                    }}
                    data-testid={`knowledge-collection-${c.slug}`}
                    className={`flex-1 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-accent ${
                      activeCollectionId === c.id ? "bg-accent font-medium" : "text-foreground"
                    }`}
                  >
                    {c.nome} <span className="text-xs text-muted-foreground">({c.total_documentos})</span>
                  </button>
                  {isAdmin && (
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Editar coleção ${c.nome}`}
                      onClick={() => setEditingCollectionId(c.id)}
                      data-testid={`knowledge-collection-edit-${c.slug}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </li>
              ),
            )}
          </ul>
        )}
        {isAdmin &&
          (showNewCollection ? (
            <NewCollectionForm agentKey={agentKey} onDone={() => setShowNewCollection(false)} />
          ) : (
            <Button variant="outline" size="sm" onClick={() => setShowNewCollection(true)}>
              <FolderPlus className="mr-1.5 h-3.5 w-3.5" />
              Nova coleção
            </Button>
          ))}
      </div>

      <div className="space-y-4">
        {!activeCollectionId ? (
          <EmptyState message="Crie uma coleção para começar." />
        ) : (
          <>
            <Card className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  value={qInput}
                  onChange={(e) => setQInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && setFilters((f) => ({ ...f, q: qInput.trim(), page: 1 }))}
                  placeholder="Buscar por título ou conteúdo…"
                  className="max-w-xs"
                />
                <Select
                  value={filters.tipo ?? ""}
                  onChange={(e) => setFilters((f) => ({ ...f, tipo: (e.target.value || undefined) as DocumentTipo | undefined, page: 1 }))}
                  className="w-40"
                >
                  <option value="">Todos os tipos</option>
                  {DOCUMENT_TIPOS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
                {isAdmin && (
                  <Button variant="outline" size="sm" onClick={() => setShowNewDoc((v) => !v)} data-testid="knowledge-new-document-toggle">
                    <FilePlus2 className="mr-1.5 h-3.5 w-3.5" />
                    Novo documento
                  </Button>
                )}
                {isAdmin && (
                  <Button variant="outline" size="sm" onClick={() => setShowUpload(true)} data-testid="knowledge-upload-toggle">
                    <Upload className="mr-1.5 h-3.5 w-3.5" />
                    Enviar arquivos
                  </Button>
                )}
              </div>

              {isAdmin && showNewDoc && (
                <NewDocumentForm
                  onCreate={async (payload) => {
                    await createDoc.mutateAsync(payload);
                    setShowNewDoc(false);
                  }}
                />
              )}

              {docsLoading ? (
                <PageSkeleton />
              ) : docsError ? (
                <ErrorState message="Erro ao carregar documentos." />
              ) : !docsPage || docsPage.items.length === 0 ? (
                <EmptyState message="Nenhum documento encontrado." />
              ) : (
                <div className="divide-y divide-border">
                  {docsPage.items.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setSelectedDoc(d.id)}
                      data-testid={`knowledge-document-row-${d.slug}`}
                      className={`flex w-full items-center justify-between gap-2 py-2 text-left text-sm hover:bg-accent/50 ${
                        selectedDoc === d.id ? "bg-accent/40" : ""
                      }`}
                    >
                      <span className="min-w-0 flex-1 truncate">{d.titulo}</span>
                      <Badge variant="outline">{d.tipo}</Badge>
                      {!d.ativo && <Badge variant="muted">arquivado</Badge>}
                    </button>
                  ))}
                </div>
              )}

              {docsPage && totalPages > 1 && (
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    Página {filters.page} de {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={filters.page <= 1} onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}>
                      Anterior
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={filters.page >= totalPages}
                      onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
                    >
                      Próxima
                    </Button>
                  </div>
                </div>
              )}
            </Card>

            {selectedDoc && <DocumentDetail agentKey={agentKey} docId={selectedDoc} isAdmin={isAdmin} />}

            <SearchPlayground agentKey={agentKey} />

            {showUpload && activeCollectionId && (
              <KnowledgeUploadDialog agentKey={agentKey} collectionId={activeCollectionId} onClose={() => setShowUpload(false)} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function NewDocumentForm({
  onCreate,
}: {
  onCreate: (payload: {
    slug: string;
    titulo: string;
    tipo: DocumentTipo;
    conteudo: string;
    resumo?: string;
    proveniencia?: Provenance;
  }) => Promise<void>;
}) {
  const [slug, setSlug] = useState("");
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState<DocumentTipo>("fonte");
  const [resumo, setResumo] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [proveniencia, setProveniencia] = useState<Provenance>(emptyProvenance());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    // `DocumentCreate.conteudo` is required non-empty (§B2 `not null`); HTML
    // `required` alone lets a whitespace-only value through, and does
    // nothing at all in a test's `fireEvent.submit`.
    if (conteudo.trim().length === 0) {
      setError("Informe o conteúdo do documento.");
      return;
    }
    setSaving(true);
    const provenienciaPayload = Object.fromEntries(Object.entries(proveniencia).filter(([, v]) => !!v)) as Provenance;
    try {
      await onCreate({
        slug,
        titulo,
        tipo,
        conteudo,
        resumo: resumo || undefined,
        proveniencia: Object.keys(provenienciaPayload).length > 0 ? provenienciaPayload : undefined,
      });
      setSlug("");
      setTitulo("");
      setResumo("");
      setConteudo("");
      setProveniencia(emptyProvenance());
      toast.success("Documento criado.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-md border border-border p-3" data-testid="knowledge-new-document-form">
      <FormError message={error} />
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Slug" required>
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} required />
        </Field>
        <Field label="Título" required>
          <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
        </Field>
      </div>
      <Field label="Tipo" required>
        <Select value={tipo} onChange={(e) => setTipo(e.target.value as DocumentTipo)}>
          {DOCUMENT_TIPOS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid gap-2 rounded-md border border-border bg-muted/30 p-2 sm:grid-cols-3" data-testid="knowledge-new-document-provenance">
        {PROVENANCE_FIELDS.map(({ key, label }) => (
          <Field key={key} label={label}>
            <Input
              value={proveniencia[key] ?? ""}
              onChange={(e) => setProveniencia((p) => ({ ...p, [key]: e.target.value }))}
              data-testid={`knowledge-new-document-provenance-${key}`}
            />
          </Field>
        ))}
      </div>
      <Field label="Resumo">
        <Textarea rows={2} value={resumo} onChange={(e) => setResumo(e.target.value)} />
      </Field>
      <Field label="Conteúdo (markdown)" required>
        <Textarea rows={8} monospace value={conteudo} onChange={(e) => setConteudo(e.target.value)} required />
      </Field>
      <Button type="submit" variant="primary" size="sm" disabled={saving}>
        Criar documento
      </Button>
    </form>
  );
}
