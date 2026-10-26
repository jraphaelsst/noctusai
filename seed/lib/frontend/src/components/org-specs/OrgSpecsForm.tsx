/**
 * `OrgSpecsForm` — the org edits its own context for an agent (who it is, services, tone...).
 *
 * Renders the fields the agent definition declares (label, help, `texto` vs `texto_longo`, required),
 * a draft that says it is unsaved, honest loading / error / empty states, and the server's refusal on the
 * offending field (422 `spec_conflita_com_regra_fixa` + `conflitos`). Data comes from `createOrgSpecsHooks`.
 * → KB § INTEGRATIONS/agents-org-specs.md
 */
import { useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { Badge, Button, EmptyState, ErrorState, Skeleton, Textarea } from '../../design-system';
import { ApiError } from '../../api';
import { UnsavedChangesNotice, useUnsavedChanges } from '../UnsavedChanges';
import type { OrgSpecsHooks } from './createOrgSpecsHooks';

export interface OrgSpecsFormProps {
  hooks: OrgSpecsHooks;
  agentKey: string;
  /** Admin-gated edit. Default true; the server enforces it anyway. False => read-only, no Save. */
  canEdit?: boolean;
  /** Shown under the intro line, e.g. the platform-locked rules notice. */
  notice?: ReactNode;
  /** Intro line next to the completeness badge. */
  intro?: ReactNode;
  emptyMessage?: string;
  /** Names of the server's locked rules, keyed by the `conflitos` codes (names only). */
  conflictLabels?: Record<string, string>;
  /** Error -> user message (a product's PT-BR mapping). Default: the error's own message. */
  formatError?: (err: unknown) => string;
  savedMessage?: string;
  'data-testid'?: string;
}

interface FieldError {
  chave: string | null;
  mensagem: string;
  conflitos: string[];
}

const INPUT_CLASS =
  'h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50';

function defaultFormatError(err: unknown): string {
  return err instanceof Error ? err.message.replace(/^\[\d+\]\s*/, '') : 'Não foi possível salvar.';
}

function parseError(err: unknown, chaves: string[], format: (e: unknown) => string): FieldError {
  const mensagem = format(err);
  const raw = err instanceof ApiError ? err.field('conflitos') : null;
  const conflitos = Array.isArray(raw) ? (raw as string[]) : [];
  const chave = chaves.find((c) => mensagem.startsWith(`${c}:`)) ?? null;
  return { chave, mensagem, conflitos };
}

export function OrgSpecsForm({
  hooks,
  agentKey,
  canEdit = true,
  notice,
  intro = 'Preencha como o agente deve falar de você.',
  emptyMessage = 'Nenhuma informação foi pedida para a sua organização ainda.',
  conflictLabels = {},
  formatError = defaultFormatError,
  savedMessage = 'Especificações salvas.',
  'data-testid': testId = 'especificacoes-org-tab',
}: OrgSpecsFormProps) {
  const q = hooks.useOrgSpecs(agentKey);
  const save = hooks.useUpdateOrgSpecs(agentKey);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [erro, setErro] = useState<FieldError | null>(null);

  const data = q.data;
  const atual = Object.fromEntries((data?.valores ?? []).map((v) => [v.chave, v.valor]));
  const valorDe = (chave: string) => edits[chave] ?? atual[chave] ?? '';
  const draft = Object.fromEntries((data?.declaradas ?? []).map((d) => [d.chave, valorDe(d.chave)]));
  const saved = data ? Object.fromEntries(data.declaradas.map((d) => [d.chave, atual[d.chave] ?? ''])) : undefined;
  const { dirty } = useUnsavedChanges(draft, saved);

  if (q.showSkeleton) {
    return (
      <div className="space-y-3" data-testid="org-specs-loading">
        <Skeleton height={36} announce />
        <Skeleton height={72} />
        <Skeleton height={72} />
      </div>
    );
  }
  if (q.isError) {
    return (
      <div className="space-y-2 text-center" data-testid="org-specs-error">
        <ErrorState message={formatError(q.error)} />
        <Button size="sm" variant="outline" onClick={q.refetch}>
          Tentar novamente
        </Button>
      </div>
    );
  }
  if (!data) return null;
  if (data.declaradas.length === 0) return <EmptyState message={emptyMessage} />;

  async function handleSave() {
    setErro(null);
    try {
      await save.mutateAsync({ valores: draft });
      setEdits({});
      toast.success(savedMessage);
    } catch (err) {
      setErro(parseError(err, data!.declaradas.map((d) => d.chave), formatError));
    }
  }

  return (
    <div className="space-y-4" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">{intro}</span>
        {data.faltando.length > 0 ? (
          <Badge variant="outline" data-testid="specs-faltando">{data.faltando.length} obrigatória(s) faltando</Badge>
        ) : (
          <Badge variant="default">Tudo preenchido</Badge>
        )}
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {notice}

      {data.declaradas.map((d) => {
        const faltando = data.faltando.includes(d.chave);
        const fieldErr = erro?.chave === d.chave ? erro : null;
        const onChange = (value: string) => setEdits((p) => ({ ...p, [d.chave]: value }));
        return (
          <div key={d.chave} className="space-y-1 rounded-lg border border-border bg-card p-4" data-testid={`spec-org-${d.chave}`}>
            <label htmlFor={`so-${d.chave}`} className="flex items-center gap-2 text-sm font-medium">
              {d.rotulo}
              {d.obrigatoria && <span className="text-xs text-muted-foreground">obrigatória</span>}
              {faltando && <Badge variant="outline">faltando</Badge>}
            </label>
            {d.descricao && <p className="text-xs text-muted-foreground">{d.descricao}</p>}
            {d.tipo === 'texto_longo' ? (
              <Textarea id={`so-${d.chave}`} rows={5} readOnly={!canEdit} value={valorDe(d.chave)} onChange={(e) => onChange(e.target.value)} />
            ) : (
              <input id={`so-${d.chave}`} className={INPUT_CLASS} readOnly={!canEdit} value={valorDe(d.chave)} onChange={(e) => onChange(e.target.value)} />
            )}
            {d.exemplo && <p className="text-[11px] text-muted-foreground">Exemplo: {d.exemplo}</p>}
            {fieldErr && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive" role="alert" data-testid={`spec-org-erro-${d.chave}`}>
                <p>{fieldErr.mensagem}</p>
                {fieldErr.conflitos.length > 0 && (
                  <ul className="ml-4 list-disc">
                    {fieldErr.conflitos.map((c) => (
                      <li key={c}>Bloco fixo da plataforma: {conflictLabels[c] ?? 'regra fixa'}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        );
      })}

      {erro && erro.chave === null && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive" role="alert" data-testid="conteudo-erro">
          {erro.mensagem}
        </p>
      )}
      {canEdit && (
        <div className="flex items-center justify-end gap-3">
          <UnsavedChangesNotice dirty={dirty} />
          <Button variant="primary" disabled={!dirty || save.isPending} onClick={handleSave} data-testid="specs-org-salvar">
            {save.isPending ? 'Salvando...' : 'Salvar especificações'}
          </Button>
        </div>
      )}
    </div>
  );
}
