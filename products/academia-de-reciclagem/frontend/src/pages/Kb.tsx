/**
 * Base de conhecimento — `/kb`.
 *
 * Search (`consulta`) + filters (`categoria`, `subcategoria`, `tag`) +
 * pagination (`limite`/`offset`) over `GET /api/kb`, plus "Nova entrada"
 * create form (contract §B.1). Page-scoped CRUD: this page both lists AND
 * creates KB entries (`KB § PATTERNS/frontend/product-internal-wiring.md`);
 * edit/archive live on the detail page (`KbDetail.tsx`) since they act on
 * one already-loaded entry.
 *
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching
 * && !!data` (`KB § PATTERNS/frontend/lying-loading-state.md`). `placeholderData:
 * keepPreviousData` (set in `useKbList`) keeps the previous page's rows on
 * screen while a new page/filter combination loads instead of flashing
 * empty.
 */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Loader2, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  PageSkeleton,
  Select,
  Textarea,
} from "@noctusai/lib/design-system";
import { errorMessage } from "@/lib/errors";
import { KB_CATEGORIAS, useCreateKb, useKbList, type KbCreateInput } from "@/hooks/useKb";

const LIMITE = 20;

export default function Kb() {
  const [consultaInput, setConsultaInput] = useState("");
  const [consulta, setConsulta] = useState("");
  const [categoria, setCategoria] = useState("");
  const [subcategoria, setSubcategoria] = useState("");
  const [tag, setTag] = useState("");
  const [offset, setOffset] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);

  const { data, isPending, isFetching, error } = useKbList({
    consulta: consulta || undefined,
    categoria: categoria || undefined,
    subcategoria: subcategoria || undefined,
    tag: tag || undefined,
    limite: LIMITE,
    offset,
  });

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  function applySearch() {
    setOffset(0);
    setConsulta(consultaInput.trim());
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Base de conhecimento</h1>
          <p className="text-sm text-muted-foreground">
            Entradas do projeto, com histórico de revisões.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Nova entrada
        </Button>
      </div>

      <Card className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="sm:col-span-2 flex gap-2">
            <Input
              placeholder="Buscar por título, resumo ou conteúdo…"
              value={consultaInput}
              onChange={(e) => setConsultaInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applySearch()}
            />
            <Button variant="outline" onClick={applySearch} aria-label="Buscar">
              <Search className="h-4 w-4" />
            </Button>
          </div>
          <Select
            value={categoria}
            onChange={(e) => {
              setOffset(0);
              setCategoria(e.target.value);
            }}
          >
            <option value="">Todas as categorias</option>
            {KB_CATEGORIAS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          <Input
            placeholder="Subcategoria"
            value={subcategoria}
            onChange={(e) => {
              setOffset(0);
              setSubcategoria(e.target.value);
            }}
          />
        </div>
        <Input
          placeholder="Filtrar por tag"
          value={tag}
          onChange={(e) => {
            setOffset(0);
            setTag(e.target.value);
          }}
          className="sm:max-w-xs"
        />
      </Card>

      {showSkeleton ? (
        <PageSkeleton />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhuma entrada encontrada." />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((entry) => (
              <Link key={entry.slug} to={`/kb/${entry.slug}`}>
                <Card className="h-full space-y-2 transition-colors hover:border-primary">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-semibold text-foreground">{entry.titulo}</h3>
                    <Badge variant="muted">{entry.categoria}</Badge>
                  </div>
                  {entry.subcategoria ? (
                    <p className="text-xs text-muted-foreground">{entry.subcategoria}</p>
                  ) : null}
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {entry.resumo || "Sem resumo."}
                  </p>
                  {entry.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {entry.tags.map((t) => (
                        <Badge key={t} variant="outline">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </Card>
              </Link>
            ))}
          </div>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {offset + 1}–{Math.min(offset + LIMITE, data.total)} de {data.total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - LIMITE))}
              >
                Anterior
              </Button>
              <Button
                variant="outline"
                disabled={offset + LIMITE >= data.total}
                onClick={() => setOffset(offset + LIMITE)}
              >
                Próxima
              </Button>
            </div>
          </div>
        </>
      )}

      {createOpen ? <CreateKbDialog onClose={() => setCreateOpen(false)} /> : null}
    </div>
  );
}

function CreateKbDialog({ onClose }: { onClose: () => void }) {
  const [slug, setSlug] = useState("");
  const [categoria, setCategoria] = useState<string>(KB_CATEGORIAS[0]);
  const [subcategoria, setSubcategoria] = useState("");
  const [titulo, setTitulo] = useState("");
  const [resumo, setResumo] = useState("");
  const [tags, setTags] = useState("");
  const [corpoMd, setCorpoMd] = useState("");
  const [motivo, setMotivo] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const createKb = useCreateKb();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const payload: KbCreateInput = {
      categoria,
      titulo,
      corpo_md: corpoMd,
      motivo,
      slug: slug || undefined,
      subcategoria: subcategoria || undefined,
      resumo: resumo || undefined,
      tags: tags
        ? tags.split(",").map((t) => t.trim()).filter(Boolean)
        : undefined,
    };
    createKb.mutate(payload, {
      onSuccess: () => {
        toast.success("Entrada criada.");
        onClose();
      },
      onError: (err) => setFormError(errorMessage(err)),
    });
  }

  return (
    <Dialog open onClose={onClose} title="Nova entrada" className="max-w-2xl">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Nova entrada</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Título" required>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
          </Field>
          <Field label="Slug (opcional — derivado do título se vazio)">
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="ex: dominio-regulatorio-pnrs" />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Categoria" required>
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
              placeholder="Por que esta entrada está sendo criada?"
              required
            />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={createKb.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={createKb.isPending}>
            {createKb.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Criar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
