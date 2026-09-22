/**
 * Base de conhecimento — detail `/kb/:slug` (contract §B.1).
 *
 * Owns the entry's edit + rename (`novo_slug`) + archive actions — the
 * page-scoped-CRUD half that `Kb.tsx` (list + create) doesn't. Markdown is
 * rendered via the plain-text `MarkdownBlock` convention (no HTML
 * injection, no markdown lib dependency — see
 * `products/knowledge-extractor/frontend/src/pages/LessonViewer.tsx`).
 * Revisions panel shows `author_kind`, `motivo`, date and `approval_id`
 * per contract §A.10.
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  ErrorState,
  Field,
  FormError,
  Input,
  PageSkeleton,
  Select,
  Textarea,
} from "@noctusai/lib/design-system";
import { MarkdownBlock } from "@/components/MarkdownBlock";
import { errorMessage } from "@/lib/errors";
import {
  KB_CATEGORIAS,
  useArchiveKb,
  useKbEntry,
  useKbRevisions,
  useUpdateKb,
  type KbUpdateInput,
} from "@/hooks/useKb";

function formatDate(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("pt-BR");
}

export default function KbDetail() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [archiving, setArchiving] = useState(false);

  const { data: entry, isPending, isFetching, error } = useKbEntry(slug);
  const revisions = useKbRevisions(slug);

  const showSkeleton = isPending && !entry;
  const isRefreshing = isFetching && !!entry;

  if (showSkeleton) return <PageSkeleton />;
  if (error) return <ErrorState message={errorMessage(error)} />;
  if (!entry) return <ErrorState message="Não encontrado." />;

  return (
    <div className="space-y-6">
      <Link to="/kb" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Voltar
      </Link>

      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-foreground">{entry.titulo}</h1>
            {entry.arquivado ? <Badge variant="muted">Arquivado</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            {entry.slug} · {entry.categoria}
            {entry.subcategoria ? ` / ${entry.subcategoria}` : ""}
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " · atualizando…" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setEditing(true)}>
            Editar
          </Button>
          {!entry.arquivado ? (
            <Button variant="destructive" onClick={() => setArchiving(true)}>
              Arquivar
            </Button>
          ) : null}
        </div>
      </div>

      <Card>
        {entry.tags.length > 0 ? (
          <div className="mb-3 flex flex-wrap gap-1">
            {entry.tags.map((t) => (
              <Badge key={t} variant="outline">
                {t}
              </Badge>
            ))}
          </div>
        ) : null}
        <MarkdownBlock value={entry.corpo_md} />
      </Card>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-foreground">Revisões</h2>
        {revisions.isPending && !revisions.data ? (
          <p className="text-sm text-muted-foreground">Carregando revisões…</p>
        ) : revisions.error ? (
          <ErrorState message={errorMessage(revisions.error)} />
        ) : !revisions.data || revisions.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma revisão.</p>
        ) : (
          <ul className="space-y-2">
            {revisions.data.items.map((rev) => (
              <li key={rev.rev_no} className="rounded-md border border-border px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="muted">rev {rev.rev_no}</Badge>
                  <Badge variant="outline">{rev.author_kind}</Badge>
                  <span className="text-muted-foreground">{rev.op}</span>
                  <span className="text-muted-foreground">{formatDate(rev.created_at)}</span>
                  {rev.approval_id ? (
                    <span className="text-xs text-muted-foreground">aprovação: {rev.approval_id}</span>
                  ) : null}
                </div>
                {rev.motivo ? <p className="mt-1 text-foreground">{rev.motivo}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {editing ? (
        <EditKbDialog
          slug={entry.slug}
          entry={entry}
          onClose={() => setEditing(false)}
          onRenamed={(newSlug) => navigate(`/kb/${newSlug}`, { replace: true })}
        />
      ) : null}
      {archiving ? <ArchiveKbDialog slug={entry.slug} onClose={() => setArchiving(false)} /> : null}
    </div>
  );
}

function EditKbDialog({
  slug,
  entry,
  onClose,
  onRenamed,
}: {
  slug: string;
  entry: { titulo: string; resumo: string | null; tags: string[]; corpo_md: string; categoria: string; subcategoria: string | null };
  onClose: () => void;
  onRenamed: (newSlug: string) => void;
}) {
  const [titulo, setTitulo] = useState(entry.titulo);
  const [resumo, setResumo] = useState(entry.resumo ?? "");
  const [tags, setTags] = useState(entry.tags.join(", "));
  const [corpoMd, setCorpoMd] = useState(entry.corpo_md);
  const [categoria, setCategoria] = useState(entry.categoria);
  const [subcategoria, setSubcategoria] = useState(entry.subcategoria ?? "");
  const [novoSlug, setNovoSlug] = useState("");
  const [motivo, setMotivo] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const updateKb = useUpdateKb(slug);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const payload: KbUpdateInput = {
      titulo,
      resumo: resumo || undefined,
      tags: tags ? tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
      corpo_md: corpoMd,
      categoria,
      subcategoria: subcategoria || undefined,
      novo_slug: novoSlug || undefined,
      motivo,
    };
    updateKb.mutate(payload, {
      onSuccess: (updated) => {
        toast.success("Entrada atualizada.");
        onClose();
        if (updated.slug !== slug) onRenamed(updated.slug);
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  return (
    <Dialog open onClose={onClose} title="Editar entrada" className="max-w-2xl">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Editar entrada</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Título" required>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
          </Field>
          <Field label="Renomear slug (novo_slug, opcional)">
            <Input value={novoSlug} onChange={(e) => setNovoSlug(e.target.value)} placeholder={slug} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Categoria">
              <Select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
                {KB_CATEGORIAS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Subcategoria">
              <Input value={subcategoria} onChange={(e) => setSubcategoria(e.target.value)} />
            </Field>
          </div>
          <Field label="Resumo">
            <Textarea rows={2} value={resumo} onChange={(e) => setResumo(e.target.value)} />
          </Field>
          <Field label="Tags (separadas por vírgula)">
            <Input value={tags} onChange={(e) => setTags(e.target.value)} />
          </Field>
          <Field label="Conteúdo (markdown)" required>
            <Textarea rows={8} value={corpoMd} onChange={(e) => setCorpoMd(e.target.value)} required />
          </Field>
          <Field label="Motivo" required>
            <Textarea
              rows={2}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Por que esta alteração está sendo feita?"
              required
            />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={updateKb.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={updateKb.isPending}>
            {updateKb.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Salvar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function ArchiveKbDialog({ slug, onClose }: { slug: string; onClose: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const archiveKb = useArchiveKb(slug);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    archiveKb.mutate(motivo, {
      onSuccess: () => {
        toast.success("Entrada arquivada.");
        onClose();
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  return (
    <Dialog open onClose={onClose} title="Arquivar entrada">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Arquivar entrada</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-muted-foreground">
            A entrada não é excluída, apenas marcada como arquivada.
          </p>
          <Field label="Motivo" required>
            <Textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} required />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={archiveKb.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="destructive" disabled={archiveKb.isPending}>
            {archiveKb.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Arquivar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
