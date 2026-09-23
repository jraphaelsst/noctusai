/**
 * `<LeadDetail/>` — Website > Leads > detail (`/admin/website/leads/:id`).
 *
 * Contract `15-api-contract.md` §3: `GET .../leads/{id}` (lead + activity
 * timeline), `PATCH .../leads/{id}` (stage / next action / owner / lost
 * reason / score), `POST .../leads/{id}/activities` (note composer).
 * "Abrir WhatsApp" builds `https://wa.me/<digits>` from `phone_e164`
 * (docs `10-conversion-and-leads.md`).
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, MessageCircle, Phone, PhoneCall, Mail as MailIcon, PenLine, ArrowRightLeft, Bot, UserCheck, FileWarning } from 'lucide-react';
import { Badge, Button, EmptyState, ErrorState, Field, Input, Select, Skeleton, Textarea } from '@noctusai/lib/design-system';
import {
  ACTIVITY_LABEL, STAGE_LABEL, formatDate, formatDateTime, usePatchWebsiteLead, useAddLeadActivity,
  useWebsiteLead, whatsAppUrl, type ActivityKind, type ActivityKindWritable, type LeadStage,
} from '../../../lib/website';

const STAGE_OPTIONS: LeadStage[] = ['novo', 'contatado', 'qualificado', 'proposta', 'ganho', 'perdido', 'descartado'];

const ACTIVITY_ICON: Record<ActivityKind, typeof MessageCircle> = {
  created: UserCheck,
  form_submit: PenLine,
  note: PenLine,
  stage_change: ArrowRightLeft,
  whatsapp_out: MessageCircle,
  whatsapp_in: MessageCircle,
  email_out: MailIcon,
  call: PhoneCall,
  agent_action: Bot,
  handoff: ArrowRightLeft,
  fanout_failed: FileWarning,
};

export function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isPending, isFetching, error } = useWebsiteLead(id);
  const patch = usePatchWebsiteLead(id ?? '');
  const addActivity = useAddLeadActivity(id ?? '');
  const [note, setNote] = useState('');
  const [nextAction, setNextAction] = useState('');
  const [nextActionAt, setNextActionAt] = useState('');

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return (
      <div className="space-y-4">
        <Skeleton height={32} announce label="Carregando lead" />
        <Skeleton height={200} announce={false} />
      </div>
    );
  }
  if (error && !data) {
    return <ErrorState message={`Não foi possível carregar o lead: ${error.message}`} />;
  }
  if (!data) {
    return <EmptyState message="Lead não encontrado." />;
  }

  const waUrl = whatsAppUrl(data.phone_e164);

  function saveNextAction() {
    patch.mutate({
      next_action: nextAction || undefined,
      next_action_at: nextActionAt ? new Date(nextActionAt).toISOString() : undefined,
    });
  }

  function submitNote(kind: ActivityKindWritable = 'note') {
    const body = note.trim();
    if (!body) return;
    addActivity.mutate({ kind, body }, { onSuccess: () => setNote('') });
  }

  return (
    <div className="space-y-6" aria-busy={isRefreshing}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Voltar para a lista de leads"
          onClick={() => navigate('/admin/website/leads')}
          className="rounded-md p-1.5 hover:bg-muted"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h1 className="text-2xl font-bold text-foreground">{data.name}</h1>
        <Badge variant={data.consent.marketing ? 'default' : 'muted'}>
          {data.consent.marketing ? `consentiu (v${data.consent.text_version})` : 'sem consentimento de marketing'}
        </Badge>
      </div>

      {(patch.error || addActivity.error) && (
        <p role="alert" className="text-sm text-destructive">
          {(patch.error ?? addActivity.error)?.message}
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <section className="space-y-2 rounded-lg border border-border bg-card p-4">
            <h2 className="font-semibold text-foreground">Contato</h2>
            <dl className="space-y-1 text-sm">
              <div><dt className="inline text-muted-foreground">E-mail: </dt><dd className="inline">{data.email ?? '—'}</dd></div>
              <div><dt className="inline text-muted-foreground">Telefone: </dt><dd className="inline">{data.phone_e164 ?? '—'}</dd></div>
              <div><dt className="inline text-muted-foreground">Empresa: </dt><dd className="inline">{data.company ?? '—'}</dd></div>
              <div><dt className="inline text-muted-foreground">Perfil: </dt><dd className="inline">{data.profile ?? '—'}</dd></div>
              <div><dt className="inline text-muted-foreground">Criado em: </dt><dd className="inline">{formatDateTime(data.created_at)}</dd></div>
            </dl>
            {waUrl ? (
              <a
                href={waUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm hover:bg-muted"
              >
                <Phone className="h-4 w-4" /> Abrir WhatsApp
              </a>
            ) : (
              <p className="text-xs text-muted-foreground">Sem telefone para abrir o WhatsApp.</p>
            )}
          </section>

          <section className="space-y-2 rounded-lg border border-border bg-card p-4">
            <h2 className="font-semibold text-foreground">Estágio</h2>
            <Select
              aria-label="Estágio do lead"
              value={data.stage}
              disabled={patch.isPending}
              onChange={(e) => patch.mutate({ stage: e.target.value as LeadStage })}
            >
              {STAGE_OPTIONS.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
            </Select>
          </section>

          <section className="space-y-2 rounded-lg border border-border bg-card p-4">
            <h2 className="font-semibold text-foreground">Próxima ação</h2>
            <Field label="O que fazer">
              <Input value={nextAction || data.next_action || ''} onChange={(e) => setNextAction(e.target.value)} />
            </Field>
            <Field label="Quando">
              <Input
                type="date"
                value={nextActionAt || (data.next_action_at ? data.next_action_at.slice(0, 10) : '')}
                onChange={(e) => setNextActionAt(e.target.value)}
              />
            </Field>
            <Button size="sm" disabled={patch.isPending} onClick={saveNextAction}>Salvar</Button>
          </section>
        </div>

        <div className="space-y-4">
          <section className="space-y-2 rounded-lg border border-border bg-card p-4">
            <h2 className="font-semibold text-foreground">Nova nota</h2>
            <Textarea
              aria-label="Nova nota"
              placeholder="Escreva uma nota de acompanhamento…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Button size="sm" disabled={!note.trim() || addActivity.isPending} onClick={() => submitNote('note')}>
              {addActivity.isPending ? 'Salvando…' : 'Adicionar nota'}
            </Button>
          </section>

          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="mb-3 font-semibold text-foreground">Histórico</h2>
            {data.activities.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma atividade ainda.</p>
            ) : (
              <ol className="space-y-3">
                {data.activities.map((activity) => {
                  const Icon = ACTIVITY_ICON[activity.kind] ?? PenLine;
                  return (
                    <li key={activity.id} className="flex gap-3 border-b border-border pb-3 last:border-b-0 last:pb-0">
                      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-medium text-foreground">{ACTIVITY_LABEL[activity.kind] ?? activity.kind}</span>
                          <span className="text-xs text-muted-foreground">{activity.actor}</span>
                          <span className="text-xs text-muted-foreground">{formatDateTime(activity.at)}</span>
                        </div>
                        {typeof activity.payload?.body === 'string' && (
                          <p className="mt-1 text-sm text-foreground">{activity.payload.body as string}</p>
                        )}
                        {activity.kind === 'stage_change' && activity.payload?.from && activity.payload?.to && (
                          <p className="mt-1 text-sm text-muted-foreground">
                            {String(activity.payload.from)} → {String(activity.payload.to)}
                          </p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          <p className="text-xs text-muted-foreground">Última atualização: {formatDate(data.updated_at)}</p>
        </div>
      </div>
    </div>
  );
}

export default LeadDetail;
