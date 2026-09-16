/**
 * Gateways: mode switch, automation switch, per-gateway keys (write-only),
 * test-connection, and the webhook URLs to paste into Stripe / Asaas.
 *
 * A saved key is NEVER shown again — the backend only says whether it is
 * configured and where it came from ("banco" or "variável de ambiente").
 */
import { useState } from 'react';
import { Badge, Button, Input, TableSkeleton } from '@noctusai/lib/design-system';
import {
  type Gateway,
  type GatewayMode,
  type SecretField,
  type SecretStatus,
  useBillingMutation,
  useBillingSettings,
} from '../../../lib/billing';

const FIELDS: Record<Gateway, Array<{ field: SecretField; label: string; placeholder: string }>> = {
  stripe: [
    { field: 'secret_key', label: 'Secret key', placeholder: 'sk_test_… / sk_live_…' },
    { field: 'webhook_secret', label: 'Webhook signing secret', placeholder: 'whsec_…' },
  ],
  asaas: [
    { field: 'api_key', label: 'Chave de API', placeholder: '$aact_hmlg_… / $aact_prod_…' },
    { field: 'webhook_token', label: 'Token do webhook', placeholder: 'mínimo 16 caracteres' },
  ],
};

const GATEWAY_LABEL: Record<Gateway, string> = { stripe: 'Stripe (cartão)', asaas: 'Asaas (Pix, boleto, cartão)' };
const MODE_LABEL: Record<GatewayMode, string> = { test: 'Teste', live: 'Produção' };

function StatusBadge({ status }: { status?: SecretStatus }) {
  if (!status?.configured) return <Badge variant="muted">não configurado</Badge>;
  return (
    <Badge variant="default">
      configurado{status.source === 'env' ? ' (variável de ambiente)' : ''}
    </Badge>
  );
}

function SecretRow({ gateway, mode, field, label, placeholder, status }: {
  gateway: Gateway; mode: GatewayMode; field: SecretField; label: string; placeholder: string;
  status?: SecretStatus;
}) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const save = useBillingMutation((b, v: string) => b.saveSecret({ gateway, mode, field, value: v }));
  const inputId = `${gateway}-${mode}-${field}`;

  const submit = (next: string) => {
    setError(null);
    save.mutate(next, {
      onSuccess: () => setValue(''),
      onError: (e: Error) => setError(e.message),
    });
  };

  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-[220px_1fr_auto] md:items-center">
      <label htmlFor={inputId} className="text-sm text-foreground">
        {label} <StatusBadge status={status} />
      </label>
      <Input
        id={inputId}
        type="password"
        autoComplete="off"
        spellCheck={false}
        placeholder={status?.configured ? '•••••••• (digite para substituir)' : placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="flex gap-2">
        <Button size="sm" disabled={!value.trim() || save.isPending} onClick={() => submit(value)}>
          {save.isPending ? 'Salvando…' : 'Salvar'}
        </Button>
        {status?.source === 'db' && (
          <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => submit('')}>
            Remover
          </Button>
        )}
      </div>
      {error && <p role="alert" className="text-xs text-destructive md:col-span-3">{error}</p>}
    </div>
  );
}

function TestConnection({ gateway, mode }: { gateway: Gateway; mode: GatewayMode }) {
  const test = useBillingMutation((b, _: void) => b.testConnection({ gateway, mode }));
  return (
    <div className="flex items-center gap-3">
      <Button size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
        {test.isPending ? 'Testando…' : 'Testar conexão'}
      </Button>
      {test.data && (
        <span role="status" className={test.data.ok ? 'text-sm text-success' : 'text-sm text-destructive'}>
          {test.data.message}
        </span>
      )}
      {test.error && <span role="alert" className="text-sm text-destructive">{test.error.message}</span>}
    </div>
  );
}

function CopyUrl({ label, url }: { label: string; url: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-20 text-sm text-muted-foreground">{label}</span>
      <code className="rounded bg-muted px-2 py-1 text-xs">{url}</code>
      <Button
        size="sm"
        variant="ghost"
        onClick={async () => {
          await navigator.clipboard.writeText(url);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? 'Copiado' : 'Copiar'}
      </Button>
    </div>
  );
}

export function GatewaysSection() {
  const { data, isPending, isFetching, error } = useBillingSettings();
  const update = useBillingMutation((b, body: Parameters<typeof b.updateSettings>[0]) => b.updateSettings(body));
  const [price, setPrice] = useState<string | null>(null);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) return <TableSkeleton rows={6} columns={3} />;
  if (error && !data) return <p role="alert" className="text-sm text-destructive">{error.message}</p>;
  if (!data) return null;

  return (
    <div className="space-y-6" aria-busy={isRefreshing}>
      {!data.encryption_configured && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          ENCRYPTION_KEY não está configurada no Core: nenhuma chave pode ser salva até que seja definida.
        </p>
      )}
      {update.error && <p role="alert" className="text-sm text-destructive">{update.error.message}</p>}

      <section className="rounded-lg border border-border bg-card p-4 space-y-3">
        <h2 className="font-semibold text-foreground">Operação</h2>
        <div className="flex flex-wrap items-center gap-4">
          <span className="text-sm">Modo das cobranças:</span>
          {(['test', 'live'] as GatewayMode[]).map((mode) => (
            <label key={mode} className="flex items-center gap-1 text-sm">
              <input
                type="radio"
                name="billing-mode"
                checked={data.mode === mode}
                disabled={update.isPending}
                onChange={() => update.mutate({ mode })}
              />
              {MODE_LABEL[mode]}
            </label>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={data.automations_enabled}
            disabled={update.isPending}
            onChange={(e) => update.mutate({ automations_enabled: e.target.checked })}
          />
          Automações de cobrança ativas (fim de trial, carência, fim de período, conciliação)
        </label>
        <p className="text-xs text-muted-foreground">
          Desligadas, nenhuma assinatura muda de status sozinha. Licenças legadas nunca são alteradas.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="storage-price" className="text-sm">Custo de storage (USD por GB/mês)</label>
          <Input
            id="storage-price"
            className="w-28"
            inputMode="decimal"
            value={price ?? data.storage_price_usd_per_gb_month ?? ''}
            onChange={(e) => setPrice(e.target.value)}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={price === null || !/^\d+(\.\d+)?$/.test(price) || update.isPending}
            onClick={() => update.mutate({ storage_price_usd_per_gb_month: price! }, { onSuccess: () => setPrice(null) })}
          >
            Salvar
          </Button>
        </div>
      </section>

      {(['stripe', 'asaas'] as Gateway[]).map((gateway) => (
        <section key={gateway} className="rounded-lg border border-border bg-card p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-foreground">{GATEWAY_LABEL[gateway]}</h2>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                aria-label={`Oferecer ${gateway}`}
                checked={data.gateways[gateway].enabled}
                disabled={update.isPending}
                onChange={(e) => update.mutate({ [`${gateway}_enabled`]: e.target.checked })}
              />
              Oferecer no checkout
            </label>
          </div>
          <CopyUrl label="Webhook" url={data.webhook_urls[gateway]} />
          {(['test', 'live'] as GatewayMode[]).map((mode) => (
            <div key={mode} className="space-y-2 border-t border-border pt-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">{MODE_LABEL[mode]}</h3>
                <TestConnection gateway={gateway} mode={mode} />
              </div>
              {FIELDS[gateway].map(({ field, label, placeholder }) => (
                <SecretRow
                  key={field}
                  gateway={gateway}
                  mode={mode}
                  field={field}
                  label={label}
                  placeholder={placeholder}
                  status={data.gateways[gateway].modes[mode][field]}
                />
              ))}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
