/**
 * Admin "Tokens de API" — machine-to-machine access for our own automation (platform admins; `CoreLayout`
 * gates `/admin/*`, the server enforces every call).
 *
 * 1. "Autenticação de tokens": the platform switch "MFA para gerar tokens" (default OFF — we do not use MFA yet).
 *    Changing it asks for confirmation. When ON, minting/rotating without a verified second factor is refused
 *    by name (`mfa_required`) and the panel below says so.
 * 2. The shared token card (`ApiTokensPanel` from @noctusai/lib): list, mint, rotate, revoke. Scopes come from
 *    the server allow-list.
 */
import { useMemo } from 'react';
import { ApiTokensPanel, createApiTokensHooks, tokenRefusalMessage, useConfirm } from '@noctusai/lib/components';
import { Badge, Button, Skeleton, Switch } from '@noctusai/lib/design-system';
import type { ApiClient } from '@noctusai/lib/api';
import { api } from '../../lib/api';
import { createTokenSettingsHooks } from '../../lib/token-settings';

type Http = Pick<ApiClient, 'get' | 'post' | 'put' | 'delete' | 'patch'>;

export function AdminTokens({ http = api as unknown as Http }: { http?: Http }) {
  const { tokens, settings } = useMemo(
    () => ({
      tokens: createApiTokensHooks(http as ApiClient),
      settings: createTokenSettingsHooks(http),
    }),
    [http],
  );
  const confirm = useConfirm();
  const current = settings.useTokenSettings();
  const setMfa = settings.useSetMfaRequired();
  const accounts = settings.useServiceAccounts();
  const on = current.data?.mfa_required ?? false;

  async function toggle(next: boolean) {
    const ok = await confirm({
      title: next ? 'Exigir MFA para gerar tokens?' : 'Parar de exigir MFA para gerar tokens?',
      description: next
        ? 'Gerar e rotacionar tokens passa a exigir uma sessão com verificação em duas etapas (MFA). Sem ela, a operação é recusada.'
        : 'Gerar e rotacionar tokens deixa de exigir MFA. Qualquer administrador da plataforma poderá gerar tokens só com a sessão normal.',
      confirmLabel: next ? 'Exigir MFA' : 'Não exigir',
      tone: next ? 'default' : 'danger',
    });
    if (ok) setMfa.mutate(next);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Tokens de API</h1>
        <p className="mt-1 text-muted-foreground">
          Acesso programático (máquina a máquina) à plataforma. O token é mostrado uma única vez, ao gerar.
        </p>
      </div>

      <section aria-labelledby="auth-tokens-title" className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <h2 id="auth-tokens-title" className="text-sm font-semibold text-foreground">
          Autenticação de tokens
        </h2>

        {current.showSkeleton ? (
          <div aria-busy="true" className="mt-3">
            <Skeleton height={40} announce label="Carregando configuração de tokens" />
          </div>
        ) : current.error && !current.data ? (
          <div role="alert" className="mt-3 flex items-center justify-between gap-3 text-sm text-destructive">
            <span>{tokenRefusalMessage(current.error, 'Não foi possível carregar a configuração.')}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => current.refetch()}>
              Tentar de novo
            </Button>
          </div>
        ) : (
          <div className="mt-3 flex items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 text-sm font-medium text-foreground" id="mfa-tokens-label">
                MFA para gerar tokens
                <Badge variant={on ? 'default' : 'muted'} data-testid="mfa-tokens-state">
                  {on ? 'Ligado' : 'Desligado'}
                </Badge>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {on
                  ? 'Gerar e rotacionar tokens exige verificação em duas etapas (MFA).'
                  : 'Ainda não usamos MFA: gerar e rotacionar tokens não exige verificação em duas etapas.'}
              </p>
            </div>
            <Switch
              aria-labelledby="mfa-tokens-label"
              checked={on}
              disabled={setMfa.isPending}
              onCheckedChange={(next) => void toggle(next)}
            />
          </div>
        )}

        {setMfa.error && (
          <p role="alert" className="mt-2 text-xs text-destructive">
            {tokenRefusalMessage(setMfa.error, 'Não foi possível salvar a configuração.')}
          </p>
        )}
      </section>

      {accounts.error && (
        <p role="alert" className="text-xs text-destructive">
          Não foi possível carregar as contas de serviço — o token será gerado sem conta de serviço.
        </p>
      )}
      <ApiTokensPanel hooks={tokens} serviceAccounts={accounts.data ?? []} />
    </div>
  );
}
