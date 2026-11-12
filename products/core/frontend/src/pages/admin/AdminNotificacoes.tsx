/**
 * Admin > Notificações — every owner-facing notification the products send (the WhatsApp scripted messages behind
 * "me avise"), grouped by product, each with its on/off switch and how it actually behaved in the last 30 days.
 *
 * Purpose (owner, 2026-11-09): validate created notifications day to day and stop receiving a type without a deploy.
 * Products DECLARE their kinds in code and register them on their own (seed `notification_catalog`), so this page
 * lists what exists — nothing is typed in here. Products cache the switch for up to 60 s; the page says so.
 */
import { useId, useState, type FormEvent } from 'react';
import { QueryErrorState, useConfirm } from '@noctusai/lib/components';
import { Badge, Button, EmptyState, Input, Skeleton, Switch } from '@noctusai/lib/design-system';
import {
  type NotificationKindRow,
  type NotificationProduct,
  type SendStatus,
  useNotificationCatalog,
  useNotificationSends,
  useSwitchNotification,
} from '../../lib/notificationCatalog';
import {
  type AddFormErrors,
  type OwnerRecipient,
  serverAddError,
  useAddOwnerRecipient,
  useOwnerLineStatus,
  useOwnerRecipients,
  usePatchOwnerRecipient,
  useRemoveOwnerRecipient,
  validateAddRecipient,
} from '../../lib/ownerLine';

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
  const empty = group.total === 0;
  const allOn = empty || group.enabled_count === group.total;
  const allOff = empty || group.enabled_count === 0;
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
      {empty ? (
        <p className="text-sm text-muted-foreground">
          Este produto está no ar, mas não declara nenhum aviso para o dono — nada dele chega por WhatsApp.
        </p>
      ) : (
        <ul className="space-y-3">
          {group.kinds.map((k) => (
            <KindRow key={k.kind} row={k} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** "+5511999999999" -> "+55 11 99999-9999" (BR mobile/landline); anything else is shown as stored. */
// NOC-REMEDIATE[br-phone-display]: 2nd hand-rolled BR display formatter (1st: social-wiring useJuliaEquipeWhatsapp.ts). The 3rd moves both into seed phone.ts as formatPhoneDisplay.
export function displayNumero(e164: string): string {
  const m = /^\+55(\d{2})(\d{4,5})(\d{4})$/.exec(e164);
  return m ? `+55 ${m[1]} ${m[2]}-${m[3]}` : e164;
}

function LineStatus() {
  const line = useOwnerLineStatus();
  if (line.isPending && !line.data) return <Skeleton className="h-5 w-72" />;
  if (line.isError && !line.data) return <QueryErrorState query={line} variant="inline" />;
  const d = line.data;
  if (!d) return null;
  return d.configurada ? (
    <p role="status" className="text-sm text-foreground">
      Linha NoctusAI: conectada{d.instancia ? ` (${d.instancia})` : ''}
    </p>
  ) : (
    <p role="status" className="text-sm text-destructive">
      Linha NoctusAI: não configurada — os avisos por WhatsApp ficam registrados como falha até a linha ser conectada.
    </p>
  );
}

function RecipientRow({ row }: { row: OwnerRecipient }) {
  const patch = usePatchOwnerRecipient();
  const remove = useRemoveOwnerRecipient();
  const confirm = useConfirm();
  const label = displayNumero(row.numero);
  async function onRemove() {
    const ok = await confirm({
      title: 'Remover destinatário?',
      description: `${row.nome ? `${row.nome} (${label})` : label} deixa de receber os avisos por WhatsApp.`,
      confirmLabel: 'Remover',
      tone: 'danger',
    });
    if (ok) remove.mutate({ id: row.id });
  }
  return (
    <li className="rounded-lg border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{row.nome || 'Sem nome'}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">{row.ativo ? 'Recebendo' : 'Pausado'}</span>
          <Switch
            checked={row.ativo}
            disabled={patch.isPending}
            aria-label={`${row.ativo ? 'Pausar' : 'Ativar'} avisos para ${row.nome || label}`}
            onCheckedChange={(ativo) => patch.mutate({ id: row.id, ativo })}
          />
          <Button
            variant="outline" size="sm" disabled={remove.isPending}
            aria-label={`Remover ${row.nome || label}`}
            onClick={onRemove}
          >
            Remover
          </Button>
        </div>
      </div>
      {patch.isError && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          Não foi possível salvar: {patch.error.message}. O interruptor voltou ao estado anterior.
        </p>
      )}
      {remove.isError && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          Não foi possível remover: {remove.error.message}. Tente de novo.
        </p>
      )}
    </li>
  );
}

function AddRecipientForm() {
  const add = useAddOwnerRecipient();
  const uid = useId();
  const [numero, setNumero] = useState('');
  const [nome, setNome] = useState('');
  const [errors, setErrors] = useState<AddFormErrors>({});
  const [general, setGeneral] = useState<string | null>(null);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setGeneral(null);
    const found = validateAddRecipient(numero, nome);
    setErrors(found);
    if (found.numero || found.nome) return;
    add.mutate(
      { numero: numero.trim(), ...(nome.trim() ? { nome: nome.trim() } : {}) },
      {
        onSuccess: () => {
          setNumero('');
          setNome('');
          setErrors({});
        },
        onError: (err) => {
          const field = serverAddError(err);
          if (field) setErrors(field);
          else setGeneral(`Não foi possível adicionar: ${err.message}. Tente de novo.`);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-wrap items-start gap-3" aria-label="Adicionar destinatário">
      <div className="space-y-1">
        <label htmlFor={`${uid}-numero`} className="text-xs font-medium text-foreground">Número (WhatsApp)</label>
        <Input
          id={`${uid}-numero`} inputMode="tel" autoComplete="off" placeholder="(11) 99999-9999"
          value={numero} onChange={(e) => setNumero(e.target.value)}
          aria-invalid={!!errors.numero} aria-describedby={errors.numero ? `${uid}-numero-err` : undefined}
        />
        {errors.numero && <p id={`${uid}-numero-err`} role="alert" className="text-xs text-destructive">{errors.numero}</p>}
      </div>
      <div className="space-y-1">
        <label htmlFor={`${uid}-nome`} className="text-xs font-medium text-foreground">Nome (opcional)</label>
        <Input
          id={`${uid}-nome`} autoComplete="off" placeholder="Ex.: Raphael"
          value={nome} onChange={(e) => setNome(e.target.value)}
          aria-invalid={!!errors.nome} aria-describedby={errors.nome ? `${uid}-nome-err` : undefined}
        />
        {errors.nome && <p id={`${uid}-nome-err`} role="alert" className="text-xs text-destructive">{errors.nome}</p>}
      </div>
      <div className="pt-5">
        <Button type="submit" disabled={add.isPending}>{add.isPending ? 'Adicionando…' : 'Adicionar'}</Button>
      </div>
      {general && <p role="alert" className="w-full text-xs text-destructive">{general}</p>}
    </form>
  );
}

function OwnerRecipientsSection() {
  const query = useOwnerRecipients();
  const { data, isPending, isFetching } = query;
  const items = data?.items ?? [];
  return (
    <section className="space-y-3" aria-labelledby="notif-destinatarios">
      <div>
        <h2 id="notif-destinatarios" className="text-lg font-semibold text-foreground">Quem recebe os avisos</h2>
        <p className="max-w-prose text-sm text-muted-foreground">
          Os avisos por WhatsApp saem da linha da NoctusAI para estes números, para todos os produtos. Este é o
          único cadastro de números do dono: os produtos (por exemplo, o número de passagem para uma pessoa nos
          agentes) leem daqui — não há outro lugar para digitar o número.
        </p>
      </div>
      <LineStatus />
      {isPending && !data ? (
        <div className="space-y-2">
          {[0, 1].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
        </div>
      ) : query.isError && !data ? (
        <QueryErrorState query={query} />
      ) : items.length === 0 ? (
        <EmptyState message="Ninguém cadastrado para receber os avisos. Adicione um número abaixo — sem destinatário, os avisos por WhatsApp não são enviados." />
      ) : (
        <ul className="space-y-2" aria-busy={isFetching && !!data}>
          {items.map((r) => <RecipientRow key={r.id} row={r} />)}
        </ul>
      )}
      <AddRecipientForm />
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
      <OwnerRecipientsSection />
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
