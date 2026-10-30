/** Editor for one template version: JSON/markdown/text body with validation, save, activate, archive, history. */
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { QueryErrorState } from '@noctusai/lib';
import { Badge, Button, Field, Input, Select, Skeleton, Textarea } from '@noctusai/lib/design-system';
import { UnsavedChangesNotice, useConfirm, useUnsavedChanges } from '@noctusai/lib/components';

import {
  useActivateTemplate, useArchiveTemplate, useTemplate, useTemplateHistory, useUpdateTemplate,
} from '../../../hooks/useTemplates';
import { STATUS_LABEL, bodyError, type Template, type TemplateFormat } from '../../../lib/templates-contract';

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString('pt-BR') : '—');
const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

interface Draft { title: string; description: string; format: TemplateFormat; body: string }
const toDraft = (t: Template): Draft => ({ title: t.title, description: t.description, format: t.format, body: t.body });

export function TemplateEditor({ id, onOpen }: { id: string; onOpen: (id: string) => void }) {
  const query = useTemplate(id);
  if (query.isPending && !query.data) return <div data-testid="template-loading" className="space-y-2"><Skeleton className="h-10 w-full" /><Skeleton className="h-48 w-full" /></div>;
  if (!query.data) return <QueryErrorState query={query} title="Não foi possível carregar este template" />;
  return <EditorBody key={query.data.id} template={query.data} onOpen={onOpen} />;
}

function EditorBody({ template, onOpen }: { template: Template; onOpen: (id: string) => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(template));
  const update = useUpdateTemplate();
  const activate = useActivateTemplate();
  const archive = useArchiveTemplate();
  const history = useTemplateHistory(template.id);
  const confirm = useConfirm();
  const { dirty } = useUnsavedChanges(draft, toDraft(template));
  const error = useMemo(() => bodyError(draft.format, draft.body), [draft.format, draft.body]);
  const isDraft = template.status === 'draft';

  function save() {
    update.mutate({ id: template.id, ...draft }, {
      onSuccess: (saved) => {
        if (saved.id === template.id) toast.success('Rascunho salvo.');
        else { toast.success(`Nova versão ${saved.version} criada como rascunho.`); onOpen(saved.id); }
      },
      onError: (e) => toast.error(message(e, 'Não foi possível salvar')),
    });
  }

  async function doActivate() {
    const ok = await confirm({
      title: `Ativar a versão ${template.version}?`,
      description: 'Passa a ser a versão em uso deste template. A ativa hoje fica arquivada e pode ser restaurada.',
      confirmLabel: 'Ativar',
    });
    if (!ok) return;
    activate.mutate(template.id, {
      onSuccess: () => toast.success(`Versão ${template.version} ativa.`),
      onError: (e) => toast.error(message(e, 'Não foi possível ativar')),
    });
  }

  async function doArchive() {
    const ok = await confirm({ title: `Arquivar a versão ${template.version}?`, description: 'A versão sai de uso e permanece no histórico.', confirmLabel: 'Arquivar' });
    if (!ok) return;
    archive.mutate(template.id, {
      onSuccess: () => toast.success('Versão arquivada.'),
      onError: (e) => toast.error(message(e, 'Não foi possível arquivar')),
    });
  }

  return (
    <div className="space-y-4" data-testid="template-editor">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-foreground">{template.key}</h3>
        <Badge>{STATUS_LABEL[template.status]}</Badge>
        <span className="text-xs text-muted-foreground">versão {template.version} · {template.product ?? 'plataforma'} · atualizado em {fmtDate(template.updated_at)}</span>
      </div>
      {!isDraft && (
        <p role="note" className="text-xs text-muted-foreground">
          Versão {STATUS_LABEL[template.status].toLowerCase()} não é editada no lugar: salvar cria um novo rascunho (versão seguinte).
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Título"><Input value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} /></Field>
        <Field label="Formato">
          <Select aria-label="Formato" value={draft.format} onChange={(e) => setDraft((d) => ({ ...d, format: e.target.value as TemplateFormat }))}>
            <option value="json">JSON</option><option value="markdown">Markdown</option><option value="text">Texto</option>
          </Select>
        </Field>
      </div>
      <Field label="Descrição"><Textarea rows={2} value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} /></Field>
      <Field label="Conteúdo">
        <Textarea aria-label="Conteúdo" rows={16} spellCheck={false} className="font-mono text-xs" value={draft.body}
          onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))} />
      </Field>
      {error && <p role="alert" data-testid="body-error" className="text-xs text-destructive">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={save} disabled={!dirty || !!error || !draft.title.trim() || update.isPending}>
          {update.isPending ? 'Salvando…' : isDraft ? 'Salvar rascunho' : 'Salvar como nova versão'}
        </Button>
        {template.status !== 'active' && (
          <Button variant="outline" onClick={doActivate} disabled={dirty || !!error || activate.isPending}>{template.status === 'archived' ? 'Restaurar (ativar)' : 'Ativar'}</Button>
        )}
        {template.status !== 'archived' && <Button variant="ghost" onClick={doArchive} disabled={archive.isPending}>Arquivar</Button>}
        <UnsavedChangesNotice dirty={dirty} />
      </div>

      <section aria-label="Histórico de versões" className="space-y-2">
        <h4 className="text-sm font-semibold text-foreground">Histórico</h4>
        {history.isPending && !history.data ? <Skeleton className="h-16 w-full" /> : null}
        <QueryErrorState query={history} title="Não foi possível carregar o histórico" />
        {history.data && (
          <ul className="divide-y divide-border rounded-md border border-border" data-testid="template-history">
            {history.data.map((h) => (
              <li key={h.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="text-foreground">Versão {h.version}</span>
                <Badge>{STATUS_LABEL[h.status]}</Badge>
                <span className="flex-1 text-xs text-muted-foreground">{h.activated_at ? `ativada em ${fmtDate(h.activated_at)}` : `criada em ${fmtDate(h.created_at)}`}</span>
                <Button variant={h.id === template.id ? 'primary' : 'outline'} onClick={() => onOpen(h.id)}>{h.id === template.id ? 'Aberta' : 'Abrir'}</Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
