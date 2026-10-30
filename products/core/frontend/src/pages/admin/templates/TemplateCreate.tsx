/** "Novo template" form: scope (platform or product) + kind + key + format + body. */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button, Field, Input, Select, Textarea } from '@noctusai/lib/design-system';

import { useCreateTemplate } from '../../../hooks/useTemplates';
import {
  KIND_LABEL, KIND_ORDER, PLATFORM_SCOPE, bodyError, type Template, type TemplateFormat, type TemplateKind, type TemplatesMeta,
} from '../../../lib/templates-contract';

const KEY_RE = /^[a-z0-9][a-z0-9_.-]{0,79}$/;

export function TemplateCreate({
  meta, kind, scope, onCreated, onCancel,
}: { meta: TemplatesMeta; kind: TemplateKind | null; scope: string | null; onCreated: (t: Template) => void; onCancel: () => void }) {
  const create = useCreateTemplate();
  const [form, setForm] = useState({
    product: scope ?? PLATFORM_SCOPE, kind: (kind ?? 'message') as TemplateKind, key: '', title: '', description: '',
    format: (kind === 'design_system' ? 'json' : 'markdown') as TemplateFormat, body: kind === 'design_system' ? '{\n  "schema": "noctus.brand-tokens/v1"\n}' : '',
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const keyOk = KEY_RE.test(form.key);
  const error = bodyError(form.format, form.body);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    create.mutate(
      { ...form, product: form.product === PLATFORM_SCOPE ? null : form.product },
      {
        onSuccess: (saved) => { toast.success('Rascunho criado.'); onCreated(saved); },
        onError: (err) => toast.error(err instanceof Error && err.message ? err.message : 'Não foi possível criar'),
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="template-create">
      <h3 className="text-base font-semibold text-foreground">Novo template</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Escopo">
          <Select aria-label="Escopo" value={form.product} onChange={(e) => set('product', e.target.value)}>
            <option value={PLATFORM_SCOPE}>Plataforma (todos)</option>
            {meta.products.map((p) => <option key={p.slug} value={p.slug}>{p.label}</option>)}
          </Select>
        </Field>
        <Field label="Tipo">
          <Select aria-label="Tipo" value={form.kind} onChange={(e) => set('kind', e.target.value as TemplateKind)}>
            {KIND_ORDER.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </Select>
        </Field>
        <Field label="Formato">
          <Select aria-label="Formato" value={form.format} onChange={(e) => set('format', e.target.value as TemplateFormat)}>
            <option value="json">JSON</option><option value="markdown">Markdown</option><option value="text">Texto</option>
          </Select>
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Chave (minúsculas, números, - _ .)"><Input aria-label="Chave" value={form.key} onChange={(e) => set('key', e.target.value)} /></Field>
        <Field label="Título"><Input aria-label="Título" value={form.title} onChange={(e) => set('title', e.target.value)} /></Field>
      </div>
      <Field label="Descrição"><Textarea rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} /></Field>
      <Field label="Conteúdo"><Textarea aria-label="Conteúdo" rows={10} spellCheck={false} className="font-mono text-xs" value={form.body} onChange={(e) => set('body', e.target.value)} /></Field>
      {form.key && !keyOk && <p role="alert" className="text-xs text-destructive">Chave inválida.</p>}
      {error && <p role="alert" data-testid="body-error" className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={!keyOk || !form.title.trim() || !!error || create.isPending}>{create.isPending ? 'Criando…' : 'Criar rascunho'}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancelar</Button>
      </div>
    </form>
  );
}
