/**
 * `<ApiTokensPanel/>` — the canonical UI for `createApiTokensHooks`: list, mint, rotate, revoke.
 *
 * - Each row: label, the stored prefix MASKED (first 4 + last 4 — the server keeps nothing more than the
 *   12-character prefix, never the secret), status, scopes, expiry and last use.
 * - Mint: scopes are checkboxes over the SERVER allow-list (never free text); expiry is 30 / 90 days or an
 *   explicit "sem expiração"; an optional service account.
 * - The raw secret is shown once in a dialog that only closes through its own button (a stray Esc or
 *   backdrop click must not lose the only copy).
 * - Rotate and revoke ask for confirmation. Every state is rendered: skeleton, error + retry, empty,
 *   list, refreshing, mint/rotate refusal (e.g. `mfa_required`) inline.
 *
 * The panel does not gate on role — mount it behind the caller's own admin check; the server enforces.
 */
import * as React from 'react';
import { AlertCircle, Copy, KeyRound, Loader2, RefreshCw, RotateCw, Trash2 } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import { Field, FormError } from '../../design-system/ui/FormControls';
import { Input } from '../../design-system/ui/Input';
import { Skeleton } from '../../design-system/ui/Skeleton';
import { useConfirm } from '../confirm';
import {
  maskTokenPrefix,
  tokenRefusalMessage,
  type ApiTokenItem,
  type ApiTokensHooks,
  type MintedApiToken,
} from './createApiTokensHooks';

export interface ApiTokenServiceAccount {
  id: string;
  name: string;
}

export interface ApiTokensPanelProps {
  hooks: ApiTokensHooks;
  /** Offer these as the token's owning service account (optional select). */
  serviceAccounts?: ApiTokenServiceAccount[];
  className?: string;
  /** Heading text. Default "Tokens de API". */
  title?: string;
}

const dateTime = (iso: string | null) => (iso ? new Date(iso).toLocaleString('pt-BR') : null);

function statusOf(t: ApiTokenItem, now = Date.now()): { label: string; variant: 'default' | 'muted' } {
  if (t.revoked_at) return { label: 'Revogado', variant: 'muted' };
  if (t.expires_at && new Date(t.expires_at).getTime() <= now) return { label: 'Expirado', variant: 'muted' };
  return { label: 'Ativo', variant: 'default' };
}

const EXPIRY_OPTIONS: Array<{ value: string; label: string; days: number | null }> = [
  { value: '90', label: '90 dias', days: 90 },
  { value: '30', label: '30 dias', days: 30 },
  { value: 'never', label: 'Sem expiração', days: null },
];

function MintDialog({
  hooks,
  serviceAccounts,
  onClose,
  onMinted,
}: {
  hooks: ApiTokensHooks;
  serviceAccounts: ApiTokenServiceAccount[];
  onClose: () => void;
  onMinted: (token: MintedApiToken) => void;
}) {
  const mint = hooks.useMintToken();
  const scopes = hooks.useTokenScopes();
  const [label, setLabel] = React.useState('');
  const [picked, setPicked] = React.useState<string[]>([]);
  const [expiry, setExpiry] = React.useState('90');
  const [serviceAccountId, setServiceAccountId] = React.useState('');
  const days = EXPIRY_OPTIONS.find((o) => o.value === expiry)?.days ?? null;
  const valid = label.trim().length > 0 && picked.length > 0;

  return (
    <Dialog open onClose={onClose} title="Gerar token">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mint.mutate(
            { label: label.trim(), scopes: picked, expiresInDays: days, serviceAccountId: serviceAccountId || null },
            { onSuccess: onMinted },
          );
        }}
      >
        <DialogHeader>
          <h3 className="font-semibold text-foreground">Gerar token</h3>
        </DialogHeader>
        <DialogBody>
          <div className="space-y-3">
            <Field label="Nome" required>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} aria-label="Nome do token" />
            </Field>

            <fieldset className="space-y-1">
              <legend className="text-xs font-medium text-foreground">
                Escopos <span className="text-destructive">*</span>
              </legend>
              {scopes.isPending ? (
                <Skeleton height={20} announce label="Carregando escopos" />
              ) : scopes.error ? (
                <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
                  Não foi possível carregar os escopos permitidos.
                  <Button type="button" variant="outline" size="sm" onClick={() => scopes.refetch()}>
                    Tentar de novo
                  </Button>
                </div>
              ) : scopes.data && scopes.data.scopes.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum escopo está registrado neste produto.</p>
              ) : (
                scopes.data?.scopes.map((s) => (
                  <label key={s} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={picked.includes(s)}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, s] : picked.filter((x) => x !== s))}
                    />
                    <code className="text-xs">{s}</code>
                  </label>
                ))
              )}
            </fieldset>

            <Field label="Validade">
              <select
                aria-label="Validade"
                className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              >
                {EXPIRY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            {days === null && (
              <p className="text-xs text-muted-foreground">
                Um token sem expiração continua válido até ser revogado. O uso fica registrado (último uso e auditoria).
              </p>
            )}

            {serviceAccounts.length > 0 && (
              <Field label="Conta de serviço">
                <select
                  aria-label="Conta de serviço"
                  className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm"
                  value={serviceAccountId}
                  onChange={(e) => setServiceAccountId(e.target.value)}
                >
                  <option value="">Nenhuma</option>
                  {serviceAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            <FormError message={mint.error ? tokenRefusalMessage(mint.error, 'Não foi possível gerar o token.') : null} />
          </div>
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={!valid || mint.isPending}>
            {mint.isPending ? 'Gerando…' : 'Gerar token'}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function SecretDialog({ token, onDone }: { token: MintedApiToken; onDone: () => void }) {
  const [copy, setCopy] = React.useState<'idle' | 'ok' | 'failed'>('idle');
  return (
    // No-op onClose on purpose: Esc / backdrop must not discard the only copy of the secret.
    <Dialog open onClose={() => undefined} title="Token gerado">
      <DialogHeader>
        <h3 className="font-semibold text-foreground">Token gerado</h3>
      </DialogHeader>
      <DialogBody>
        <div className="space-y-3">
          <p className="text-sm text-foreground">
            Copie o token agora. Por segurança ele <strong>não será mostrado de novo</strong> — se perder, gere outro.
          </p>
          <code className="block break-all rounded bg-muted px-3 py-2 text-xs" data-testid="api-token-secret">
            {token.token}
          </code>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(token.token);
                  setCopy('ok');
                } catch {
                  setCopy('failed');
                }
              }}
            >
              <Copy className="mr-1.5 h-3.5 w-3.5" />
              Copiar
            </Button>
            {copy === 'ok' && <span className="text-xs text-emerald-600">Copiado.</span>}
            {copy === 'failed' && (
              <span role="alert" className="text-xs text-destructive">
                Não foi possível copiar — selecione o texto acima e copie manualmente.
              </span>
            )}
          </div>
        </div>
      </DialogBody>
      <DialogFooter>
        <Button type="button" onClick={onDone}>
          Já copiei
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

function TokenRow({
  token,
  hooks,
  serviceAccountName,
  onMinted,
}: {
  token: ApiTokenItem;
  hooks: ApiTokensHooks;
  serviceAccountName: string | null;
  onMinted: (t: MintedApiToken) => void;
}) {
  const confirm = useConfirm();
  const rotate = hooks.useRotateToken();
  const revoke = hooks.useRevokeToken();
  const status = statusOf(token);
  const live = status.label === 'Ativo';
  const busy = rotate.isPending || revoke.isPending;
  const failure = rotate.error ?? revoke.error;

  return (
    <li className="grid gap-2 rounded-md border border-border p-3" data-testid={`api-token-row-${token.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{token.label}</p>
          <code className="text-xs text-muted-foreground" data-testid={`api-token-mask-${token.id}`}>
            {maskTokenPrefix(token.prefix)}
          </code>
        </div>
        <Badge variant={status.variant}>{status.label}</Badge>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {token.scopes.length === 0 ? (
          <span className="text-xs text-muted-foreground">Sem escopos</span>
        ) : (
          token.scopes.map((s) => (
            <Badge key={s} variant="muted">
              {s}
            </Badge>
          ))
        )}
      </div>

      <dl className="grid grid-cols-1 gap-1 text-xs text-muted-foreground sm:grid-cols-3">
        <div>
          <dt className="inline">Expira: </dt>
          <dd className="inline">{token.expires_at ? dateTime(token.expires_at) : 'Sem expiração'}</dd>
        </div>
        <div>
          <dt className="inline">Último uso: </dt>
          <dd className="inline">{token.last_used_at ? dateTime(token.last_used_at) : 'Nunca usado'}</dd>
        </div>
        {serviceAccountName && (
          <div>
            <dt className="inline">Conta de serviço: </dt>
            <dd className="inline">{serviceAccountName}</dd>
          </div>
        )}
      </dl>

      {live && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            aria-label={`Rotacionar ${token.label}`}
            onClick={async () => {
              if (
                !(await confirm({
                  title: `Rotacionar "${token.label}"?`,
                  description: 'Um novo token é gerado e este deixa de funcionar imediatamente. Atualize quem o usa.',
                  confirmLabel: 'Rotacionar',
                }))
              )
                return;
              rotate.mutate(token.id, { onSuccess: onMinted });
            }}
          >
            {rotate.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="mr-1.5 h-3.5 w-3.5" />}
            Rotacionar
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy}
            aria-label={`Revogar ${token.label}`}
            onClick={async () => {
              if (
                !(await confirm({
                  title: `Revogar "${token.label}"?`,
                  description: 'Quem usa este token passa a receber 401 na hora. Não dá para desfazer.',
                  confirmLabel: 'Revogar',
                  tone: 'danger',
                }))
              )
                return;
              revoke.mutate(token.id);
            }}
          >
            {revoke.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1.5 h-3.5 w-3.5" />}
            Revogar
          </Button>
        </div>
      )}

      {failure && (
        <p role="alert" className="text-xs text-destructive">
          {tokenRefusalMessage(failure)}
        </p>
      )}
    </li>
  );
}

export function ApiTokensPanel({ hooks, serviceAccounts = [], className, title = 'Tokens de API' }: ApiTokensPanelProps) {
  const { data, error, showSkeleton, isRefreshing, refetch } = hooks.useApiTokens();
  const [minting, setMinting] = React.useState(false);
  const [secret, setSecret] = React.useState<MintedApiToken | null>(null);
  const accountName = (id: string | null) => serviceAccounts.find((a) => a.id === id)?.name ?? null;

  const onMinted = (t: MintedApiToken) => {
    setMinting(false);
    setSecret(t);
  };

  return (
    <div className={className} data-testid="api-tokens-panel">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">{title}</h2>
          {isRefreshing && <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground" data-testid="api-tokens-refreshing" />}
        </div>
        <Button type="button" size="sm" onClick={() => setMinting(true)}>
          Gerar token
        </Button>
      </div>

      {showSkeleton && (
        <div aria-busy="true" className="grid gap-2">
          <Skeleton height={96} announce label="Carregando tokens" />
          <Skeleton height={96} announce={false} />
        </div>
      )}

      {!showSkeleton && error && !data && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <span className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            {tokenRefusalMessage(error, 'Falha ao carregar os tokens.')}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={() => refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}

      {!showSkeleton && data && data.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="api-tokens-empty">
          Nenhum token ainda. Use “Gerar token” para criar o primeiro.
        </p>
      )}

      {data && data.length > 0 && (
        <ul className="grid gap-2">
          {data.map((t) => (
            <TokenRow key={t.id} token={t} hooks={hooks} serviceAccountName={accountName(t.service_account_id)} onMinted={setSecret} />
          ))}
        </ul>
      )}

      {minting && <MintDialog hooks={hooks} serviceAccounts={serviceAccounts} onClose={() => setMinting(false)} onMinted={onMinted} />}
      {secret && <SecretDialog token={secret} onDone={() => setSecret(null)} />}
    </div>
  );
}
