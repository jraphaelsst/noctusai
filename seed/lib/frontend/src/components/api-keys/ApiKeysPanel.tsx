/**
 * `<ApiKeysPanel/>` — the canonical UI for `createApiKeysHooks`.
 *
 * Renders every managed key: masked hint + source badge, a set/replace
 * input (free-text) or a CHOICE selector (`options` non-empty), a "Testar"
 * action when `testable`, and remove. Complete loading / empty / error /
 * success states.
 *
 * Deliberately does NOT gate on role — social-wiring's own Settings page
 * only mounts its "Chaves de API" tab for an owner/admin; do the same at
 * the call site (`<ApiKeysPanel hooks={...} />` behind your own admin
 * check) rather than duplicating that policy here.
 *
 * Usage:
 * ```tsx
 * import { createApiKeysHooks, ApiKeysPanel } from '@noctusai/lib/components';
 * import { api } from '@/lib/api';
 *
 * const apiKeys = createApiKeysHooks(api);
 * <ApiKeysPanel hooks={apiKeys} />
 * ```
 */
import * as React from 'react';
import { AlertCircle, CheckCircle2, Loader2, RefreshCw, Trash2 } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Input } from '../../design-system/ui/Input';
import { Skeleton } from '../../design-system/ui/Skeleton';
import { ApiError } from '../../api';
import type { ApiKeysHooks, ApiKeyStatus } from './createApiKeysHooks';

const SOURCE_LABEL: Record<string, string> = {
  local: 'Definida aqui',
  platform: 'Definida na plataforma',
  env: 'Definida no ambiente',
};

export interface ApiKeysPanelProps {
  hooks: ApiKeysHooks;
  className?: string;
  /** Heading text. Default "Chaves de API". */
  title?: string;
}

function ChoiceField({
  keyStatus,
  onSave,
  saving,
}: {
  keyStatus: ApiKeyStatus;
  onSave: (value: string) => void;
  saving: boolean;
}) {
  const [value, setValue] = React.useState(keyStatus.default ?? '');
  return (
    <div className="flex items-center gap-2">
      <select
        aria-label={keyStatus.label}
        className="h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm disabled:opacity-50"
        value={value}
        disabled={saving}
        onChange={(e) => setValue(e.target.value)}
      >
        {keyStatus.options.map((opt) => (
          <option key={opt.value} value={opt.value} title={opt.description}>
            {opt.label}
          </option>
        ))}
      </select>
      <Button
        type="button"
        size="sm"
        disabled={saving || !value}
        onClick={() => onSave(value)}
      >
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Salvar'}
      </Button>
    </div>
  );
}

function SecretField({
  keyStatus,
  onSave,
  saving,
}: {
  keyStatus: ApiKeyStatus;
  onSave: (value: string) => void;
  saving: boolean;
}) {
  const [value, setValue] = React.useState('');
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!value.trim()) return;
        onSave(value.trim());
        setValue('');
      }}
    >
      <Input
        type={keyStatus.is_secret ? 'password' : keyStatus.input_type || 'text'}
        placeholder={keyStatus.placeholder || 'Novo valor'}
        aria-label={keyStatus.label}
        value={value}
        disabled={saving}
        onChange={(e) => setValue(e.target.value)}
      />
      <Button type="submit" size="sm" disabled={saving || !value.trim()}>
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Salvar'}
      </Button>
    </form>
  );
}

function ApiKeyRow({ keyStatus, hooks }: { keyStatus: ApiKeyStatus; hooks: ApiKeysHooks }) {
  const save = hooks.useSaveApiKey();
  const remove = hooks.useRemoveApiKey();
  const test = hooks.useTestApiKey();
  const [testResult, setTestResult] = React.useState<{ success: boolean; message: string } | null>(null);

  const handleSave = (value: string) => save.mutate({ key: keyStatus.key, value });
  const handleTest = async () => {
    setTestResult(null);
    try {
      const result = await test.mutateAsync(keyStatus.key);
      setTestResult({ success: result.success, message: result.message });
    } catch {
      // useTestApiKey already toasts the failure; nothing further to do here.
    }
  };

  return (
    <li className="grid gap-2 rounded-md border border-border p-3" data-testid={`api-key-row-${keyStatus.key}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{keyStatus.label}</p>
          <p className="text-xs text-muted-foreground">{keyStatus.description}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {keyStatus.configured ? (
            <Badge variant="default" data-testid={`api-key-configured-${keyStatus.key}`}>
              {keyStatus.source ? SOURCE_LABEL[keyStatus.source] ?? keyStatus.source : 'Configurada'}
            </Badge>
          ) : (
            <Badge variant="muted">Não configurada</Badge>
          )}
        </div>
      </div>

      {keyStatus.hint != null && (
        <code className="w-fit rounded bg-muted px-2 py-0.5 text-xs" data-testid={`api-key-hint-${keyStatus.key}`}>
          {keyStatus.hint}
        </code>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {keyStatus.options.length > 0 ? (
          <ChoiceField keyStatus={keyStatus} onSave={handleSave} saving={save.isPending} />
        ) : (
          <SecretField keyStatus={keyStatus} onSave={handleSave} saving={save.isPending} />
        )}

        {keyStatus.testable && (
          <Button type="button" variant="outline" size="sm" onClick={handleTest} disabled={test.isPending}>
            {test.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Testar'}
          </Button>
        )}

        {keyStatus.configured && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={`Remover ${keyStatus.label}`}
            onClick={() => remove.mutate(keyStatus.key)}
            disabled={remove.isPending}
          >
            {remove.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          </Button>
        )}
      </div>

      {testResult && (
        <p
          className={testResult.success ? 'text-xs text-emerald-600' : 'text-xs text-destructive'}
          data-testid={`api-key-test-result-${keyStatus.key}`}
        >
          {testResult.success ? <CheckCircle2 className="mr-1 inline h-3 w-3" /> : <AlertCircle className="mr-1 inline h-3 w-3" />}
          {testResult.message}
        </p>
      )}
    </li>
  );
}

export function ApiKeysPanel({ hooks, className, title = 'Chaves de API' }: ApiKeysPanelProps) {
  const { data, error, showSkeleton, isRefreshing, refetch } = hooks.useApiKeys();

  return (
    <div className={className} data-testid="api-keys-panel">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {isRefreshing && <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground" data-testid="api-keys-refreshing" />}
      </div>

      {showSkeleton && (
        <div aria-busy="true" className="grid gap-2">
          <Skeleton height={72} announce label="Carregando chaves de API" />
          <Skeleton height={72} announce={false} />
          <Skeleton height={72} announce={false} />
        </div>
      )}

      {!showSkeleton && error && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <span className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            {error instanceof ApiError && error.status === 503
              ? 'Servidor sem chave de criptografia configurada (ENCRYPTION_KEY ausente).'
              : error instanceof Error
                ? error.message
                : 'Falha ao carregar as chaves de API.'}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={() => refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}

      {!showSkeleton && !error && data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="api-keys-empty">
          Nenhuma chave gerenciável configurada neste produto.
        </p>
      )}

      {!showSkeleton && !error && data && data.items.length > 0 && (
        <ul className="grid gap-2">
          {data.items.map((item) => (
            <ApiKeyRow key={item.key} keyStatus={item} hooks={hooks} />
          ))}
        </ul>
      )}
    </div>
  );
}
