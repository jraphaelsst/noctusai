/**
 * Admin > Notificações — every owner-facing notification the products send (the WhatsApp scripted messages behind
 * "me avise"), grouped by product, each with its on/off switch and how it actually behaved in the last 30 days.
 *
 * Purpose (owner, 2026-11-09): validate created notifications day to day and stop receiving a type without a deploy.
 * Products DECLARE their kinds in code and register them on their own (seed `notification_catalog`), so this page
 * lists what exists — nothing is typed in here. Products cache the switch for up to 60 s; the page says so.
 */
import { useState } from 'react';
import { QueryErrorState } from '@noctusai/lib/components';
import { Badge, Button, EmptyState, Skeleton, Switch } from '@noctusai/lib/design-system';
import {
  type NotificationKindRow,
  type NotificationProduct,
  type SendStatus,
  useNotificationCatalog,
  useNotificationSends,
  useSwitchNotification,
} from '../../lib/notificationCatalog';

const STATUS_LABEL: Record<SendStatus, string> = {
  sent: 'enviada',
  partial: 'parcial',
  failed: 'falhou',
  suppressed: 'desligada',
  no_recipient: 'sem destinatário',
};

const CHANNEL_LABEL: Record<string, string> = { whatsapp: 'WhatsApp', email: 'e-mail', in_app: 'sino' };

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function StatusBadge({ status }: { status: SendStatus | undefined }) {
  if (!status) return <Badge variant="outline">nunca disparou</Badge>;
  const variant = status === 'sent' ? 'default' : status === 'failed' || status === 'no_recipient' ? 'destructive' : 'muted';
  return <Badge variant={variant}>{STATUS_LABEL[status]}</Badge>;
}

function SendHistory({ product, kind }: { product: string; kind: string }) {
  const sends = useNotificationSends(product, kind, true);
  if (sends.isPending && !sends.data) return <Skeleton className="h-16 w-full" />;
  if (sends.isError && !sends.data) return <QueryErrorState query={sends} variant="inline" />;
  const rows = sends.data ?? [];
  if (rows.length === 0) return <p className="text-xs text-muted-foreground">Nenhum disparo registrado ainda.</p>;
  return (
    <ul className="space-y-1 text-xs">
      {rows.map((r) => (
        <li key={r.id} className="flex flex-wrap items-center gap-2">
          <span className="w-24 shrink-0 text-muted-foreground">{formatWhen(r.created_at)}</span>
          <StatusBadge status={r.status} />
          <span className="text-muted-foreground">
            {r.delivered}/{r.recipients} entregue(s)
          </span>
          {r.reason && <span className="min-w-0 break-words text-muted-foreground">· {r.reason}</span>}
        </li>
      ))}
    </ul>
  );
}

function KindRow({ row }: { row: NotificationKindRow }) {
  const [open, setOpen] = useState(false);
  const toggle = useSwitchNotification();
  const c = row.counts_30d;
  const problems = c.failed + c.no_recipient;
  const label = `${row.enabled ? 'Desligar' : 'Ligar'} "${row.titulo}"`;
  return (
    <li className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{row.titulo}</h3>
            <code className="text-xs text-muted-foreground">{row.kind}</code>
            {row.canais.map((ch) => (
              <Badge key={ch} variant="outline">{CHANNEL_LABEL[ch] ?? ch}</Badge>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">{row.descricao}</p>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Quando dispara:</span> {row.gatilho}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{row.enabled ? 'Ligada' : 'Desligada'}</span>
          <Switch
            checked={row.enabled}
            disabled={toggle.isPending}
            aria-label={label}
            onCheckedChange={(enabled) => toggle.mutate({ product: row.product, kind: row.kind, enabled })}
          />
        </div>
      </div>
      {toggle.isError && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          Não foi possível salvar: {toggle.error.message}. O interruptor voltou ao estado anterior.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-2">
          Último disparo: <StatusBadge status={row.last_dispatch?.status} /> {formatWhen(row.last_dispatch?.at)}
        </span>
        <span>Última entrega: {formatWhen(row.last_sent_at)}</span>
        <span>
          30 dias: {c.sent + c.partial} enviada(s)
          {c.suppressed > 0 && ` · ${c.suppressed} desligada(s)`}
          {problems > 0 && <span className="text-destructive"> · {problems} com problema</span>}
        </span>
        <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? 'Ocultar histórico' : 'Histórico'}
        </Button>
      </div>
      {open && (
        <div className="mt-3 rounded-md bg-muted/30 p-3">
          <SendHistory product={row.product} kind={row.kind} />
        </div>
      )}
    </li>
  );
}

function ProductSection({ group }: { group: NotificationProduct }) {
  const toggle = useSwitchNotification();
  const allOn = group.enabled_count === group.total;
  const allOff = group.enabled_count === 0;
  return (
    <section className="space-y-3" aria-labelledby={`notif-${group.product}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`notif-${group.product}`} className="text-lg font-semibold text-foreground">
          {group.product}{' '}
          <span className="text-sm font-normal text-muted-foreground">
            {group.enabled_count} de {group.total} ligada(s)
          </span>
        </h2>
        <div className="flex gap-2">
          <Button
            variant="outline" size="sm" disabled={allOn || toggle.isPending}
            onClick={() => toggle.mutate({ product: group.product, kind: null, enabled: true })}
          >
            Ligar todas
          </Button>
          <Button
            variant="outline" size="sm" disabled={allOff || toggle.isPending}
            onClick={() => toggle.mutate({ product: group.product, kind: null, enabled: false })}
          >
            Desligar todas
          </Button>
        </div>
      </div>
      {toggle.isError && (
        <p role="alert" className="text-xs text-destructive">Não foi possível salvar: {toggle.error.message}.</p>
      )}
      <ul className="space-y-3">
        {group.kinds.map((k) => (
          <KindRow key={k.kind} row={k} />
        ))}
      </ul>
    </section>
  );
}

export function AdminNotificacoes() {
  const query = useNotificationCatalog();
  const { data, isPending, isFetching } = query;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Notificações</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Todos os avisos que os produtos mandam para você (WhatsApp e e-mail), com o que dispara cada um e como se
          comportaram nos últimos 30 dias. Desligue um tipo para parar de recebê-lo — vale em até 1 minuto.
        </p>
      </div>
      {isPending && !data ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : query.isError && !data ? (
        <QueryErrorState query={query} />
      ) : !data || data.products.length === 0 ? (
        <EmptyState message="Nenhuma notificação registrada ainda. Os produtos registram seus avisos sozinhos no primeiro disparo depois do deploy." />
      ) : (
        <div className="space-y-8" aria-busy={isFetching && !!data}>
          {data.sends_truncated && (
            <p role="status" className="text-xs text-muted-foreground">
              Muitos disparos no período: as contagens consideram os 20.000 mais recentes.
            </p>
          )}
          {data.products.map((g) => (
            <ProductSection key={g.product} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}
