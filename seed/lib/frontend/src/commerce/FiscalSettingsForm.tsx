/**
 * `<FiscalSettingsForm/>` — the store's fiscal data (CONTRACT P4 §2.5 `GET/PUT /api/commerce/fiscal`): municipal /
 * state registration, IBGE municipality, auto-issue, the regime-aware NFS-e mode, the A1 certificate and the
 * approved NFS-e Nacional cutover / rollback (danger dialogs with a TYPED phrase).
 *
 * Certificate: the `.pfx` and its password are forwarded to the invoice provider and never stored — the password
 * lives in component state only until the request settles (then it is cleared, success or not). Saves are
 * optimistic-locked (`expected_version`). MEI / Simples Nacional are forced to the National issuer (the mode is
 * shown, no rollback offered). Admin-only (UX; the server enforces).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge, type BadgeVariant } from '../design-system/ui/Badge';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { Skeleton } from '../design-system/ui/Skeleton';
import { ErrorState, Field, FormError, Input } from './controls';
import { useCommerceT } from './i18n';
import { formatDateTime, maskCnpj } from './format';
import { apiErrorCode, errorMessage, type CommerceHooks } from './hooks';
import {
  MAX_CERTIFICATE_BYTES,
  MAX_CERTIFICATE_PASSWORD_CHARS,
  NFSE_CUTOVER_PHRASE,
  NFSE_ROLLBACK_PHRASE,
  type CertificateStatus,
  type FiscalView,
} from './fiscalTypes';
import { COMMERCE_ERROR_CODES } from './types';

export interface FiscalSettingsFormProps {
  hooks: CommerceHooks;
  locale?: string;
  /** Org admin or platform admin (UX only). Default `false`: read-only with a hint. */
  isAdmin?: boolean;
}

const CERT_VARIANT: Record<CertificateStatus, BadgeVariant> = { ausente: 'muted', vencido: 'destructive', divergente: 'destructive', valido: 'default' };

function PhraseDialog({
  open, onClose, title, body, phrase, pending, error, onConfirm, locale,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  body: string;
  phrase: string;
  pending: boolean;
  error: string | null;
  onConfirm: (typed: string) => void;
  locale?: string;
}) {
  const { t } = useCommerceT(locale);
  const [typed, setTyped] = React.useState('');
  React.useEffect(() => { if (open) setTyped(''); }, [open]);
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <form onSubmit={(ev) => { ev.preventDefault(); if (typed === phrase) onConfirm(typed); }}>
        <DialogHeader><h3 className="text-sm font-semibold text-destructive">{title}</h3></DialogHeader>
        <DialogBody className="space-y-3">
          <p className="text-sm">{body}</p>
          <p className="text-sm">{t('fiscal.type_phrase', { phrase })}</p>
          <Field label={t('fiscal.confirm_phrase')}>
            <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" autoFocus />
          </Field>
          <FormError message={error} />
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" onClick={onClose} disabled={pending}>{t('common.back')}</Button>
          <Button type="submit" variant="destructive" disabled={pending || typed !== phrase}>{t('fiscal.confirm')}</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

export function FiscalSettingsForm({ hooks, locale, isAdmin = false }: FiscalSettingsFormProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const fiscal = hooks.useFiscal();
  const m = hooks.useFiscalMutations();
  const [im, setIm] = React.useState('');
  const [ie, setIe] = React.useState('');
  const [ibge, setIbge] = React.useState('');
  const [auto, setAuto] = React.useState(false);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saved, setSaved] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [password, setPassword] = React.useState('');
  const [certMsg, setCertMsg] = React.useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [danger, setDanger] = React.useState<'cutover' | 'rollback' | null>(null);
  const loadedVersion = React.useRef<number | null>(null);

  React.useEffect(() => {
    const f = fiscal.data;
    if (!f || loadedVersion.current === f.version) return;
    loadedVersion.current = f.version;
    setIm(f.inscricao_municipal ?? '');
    setIe(f.inscricao_estadual ?? '');
    setIbge(f.municipio_ibge ?? '');
    setAuto(f.auto_issue_invoices);
  }, [fiscal.data]);

  if (fiscal.showSkeleton) {
    return (
      <div className="space-y-3" data-testid="fiscal-loading">
        <Skeleton height={32} width="100%" />
        <Skeleton height={32} width="100%" announce={false} />
      </div>
    );
  }
  if (fiscal.isError && !fiscal.data) {
    return (
      <div className="space-y-2">
        <ErrorState message={`${t('common.error_loading')}: ${errorMessage(fiscal.error)}`} />
        <Button variant="outline" onClick={() => fiscal.refetch()}>{t('common.retry')}</Button>
      </div>
    );
  }
  const f: FiscalView | undefined = fiscal.data;
  if (!f) return null;
  const readOnly = !isAdmin;

  async function onSave(ev: React.FormEvent) {
    ev.preventDefault();
    const e: Record<string, string> = {};
    if (ibge.trim() && !/^\d{7}$/.test(ibge.trim())) e.ibge = t('fiscal.ibge_invalid');
    setErrors(e);
    if (Object.keys(e).length) return;
    try {
      await m.save.mutateAsync({
        expected_version: f!.version,
        inscricao_municipal: im.trim() || null,
        inscricao_estadual: ie.trim() || null,
        municipio_ibge: ibge.trim() || null,
        auto_issue_invoices: auto,
      });
      setSaved(true);
    } catch {
      // Surfaced below via `m.save.error` — not swallowed.
    }
  }

  async function onUpload(ev: React.FormEvent) {
    ev.preventDefault();
    setCertMsg(null);
    if (!file) return setCertMsg({ kind: 'err', text: t('fiscal.cert_missing_file') });
    if (file.size > MAX_CERTIFICATE_BYTES) return setCertMsg({ kind: 'err', text: t('fiscal.cert_too_big') });
    if (!password || password.length > MAX_CERTIFICATE_PASSWORD_CHARS) return setCertMsg({ kind: 'err', text: t('fiscal.cert_missing_password') });
    try {
      await m.uploadCertificate.mutateAsync({ file, password });
      setCertMsg({ kind: 'ok', text: t('fiscal.cert_uploaded') });
      setFile(null);
    } catch (err) {
      setCertMsg({ kind: 'err', text: errorMessage(err) });
    } finally {
      setPassword(''); // never kept past the request
    }
  }

  const conflict = apiErrorCode(m.save.error) === COMMERCE_ERROR_CODES.versaoConflitante;
  const dangerMutation = danger === 'cutover' ? m.cutover : m.rollback;
  const edit = <T,>(set: (v: T) => void) => (v: T) => { setSaved(false); set(v); };

  return (
    <div className="space-y-6" aria-busy={fiscal.isRefreshing}>
      <form onSubmit={onSave} className="space-y-4" noValidate aria-label={t('fiscal.title')}>
        <div>
          <h2 className="text-base font-semibold">{t('fiscal.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('fiscal.intro')}</p>
        </div>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-muted-foreground">{t('fiscal.cnpj')}</dt><dd className="font-mono">{maskCnpj(f.cnpj)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">{t('fiscal.regime')}</dt><dd>{t(`tax_regime.${f.tax_regime}`)}</dd></div>
        </dl>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t('fiscal.im')}><Input value={im} disabled={readOnly} onChange={(e) => edit(setIm)(e.target.value)} /></Field>
          <Field label={t('fiscal.ie')}><Input value={ie} disabled={readOnly} onChange={(e) => edit(setIe)(e.target.value)} /></Field>
          <Field label={t('fiscal.ibge')} error={errors.ibge}><Input inputMode="numeric" value={ibge} disabled={readOnly} onChange={(e) => edit(setIbge)(e.target.value)} /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={auto} disabled={readOnly} onChange={(e) => edit(setAuto)(e.target.checked)} />
          {t('fiscal.auto_issue')}
        </label>
        <p className="text-sm">
          <span className="text-xs text-muted-foreground">{t('fiscal.nfse_mode')}: </span>
          <Badge variant="outline" data-testid="nfse-mode">{t(`nfse_mode.${f.nfse_mode}`)}</Badge>
          {f.nfse_nacional_forced ? <span className="ml-2 text-xs text-muted-foreground">{t('fiscal.nfse_forced')}</span> : null}
          {f.nfse_cutover.validation_until ? <span className="ml-2 text-xs text-muted-foreground">{t('fiscal.validation_until', { date: formatDateTime(f.nfse_cutover.validation_until, loc) })}</span> : null}
        </p>
        {conflict ? <FormError message={t('profile.conflict')} /> : m.save.isError ? <FormError message={errorMessage(m.save.error)} /> : null}
        {saved ? <p role="status" className="text-sm text-green-600">{t('common.saved')}</p> : null}
        {readOnly ? <p className="text-xs text-muted-foreground">{t('fiscal.admin_only')}</p> : (
          <Button type="submit" variant="primary" disabled={m.save.isPending}>{m.save.isPending ? t('common.saving') : t('fiscal.save')}</Button>
        )}
      </form>

      <section className="space-y-3" aria-label={t('fiscal.certificate')}>
        <h3 className="text-sm font-semibold">{t('fiscal.certificate')}</h3>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant={CERT_VARIANT[f.certificate_status]} data-status={f.certificate_status}>{t(`cert_status.${f.certificate_status}`)}</Badge>
          {f.certificate_valid_until ? <span className="text-xs text-muted-foreground">{t('fiscal.cert_valid_until', { date: formatDateTime(f.certificate_valid_until, loc) })}</span> : null}
        </p>
        {readOnly ? null : (
          <form onSubmit={onUpload} className="grid gap-3 sm:grid-cols-2" noValidate>
            <Field label={t('fiscal.cert_file')}>
              <input type="file" accept=".pfx,.p12,application/x-pkcs12" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
            </Field>
            <Field label={t('fiscal.cert_password')}>
              <Input type="password" autoComplete="off" value={password} maxLength={MAX_CERTIFICATE_PASSWORD_CHARS} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <p className="text-xs text-muted-foreground sm:col-span-2">{t('fiscal.cert_note')}</p>
            {certMsg ? (certMsg.kind === 'ok' ? <p role="status" className="text-sm text-green-600 sm:col-span-2">{certMsg.text}</p> : <div className="sm:col-span-2"><FormError message={certMsg.text} /></div>) : null}
            <div className="sm:col-span-2">
              <Button type="submit" variant="outline" disabled={m.uploadCertificate.isPending}>{m.uploadCertificate.isPending ? t('fiscal.cert_uploading') : t('fiscal.cert_upload')}</Button>
            </div>
          </form>
        )}
      </section>

      {readOnly ? null : (
        <section className="space-y-2 rounded-md border border-destructive/40 p-3" aria-label={t('fiscal.cutover_title')}>
          {f.can_cutover ? (
            <div className="space-y-1">
              <h3 className="text-sm font-semibold">{t('fiscal.cutover_title')}</h3>
              <p className="text-xs text-muted-foreground">{t('fiscal.cutover_body')}</p>
              <Button variant="destructive" onClick={() => setDanger('cutover')}>{t('fiscal.cutover_open')}</Button>
            </div>
          ) : null}
          {f.can_rollback ? (
            <div className="space-y-1">
              <h3 className="text-sm font-semibold">{t('fiscal.rollback_title')}</h3>
              <p className="text-xs text-muted-foreground">{t('fiscal.rollback_body')}</p>
              <Button variant="destructive" onClick={() => setDanger('rollback')}>{t('fiscal.rollback_open')}</Button>
            </div>
          ) : null}
          {!f.can_cutover && !f.can_rollback ? <p className="text-xs text-muted-foreground">{t(`nfse_mode.${f.nfse_mode}`)}</p> : null}
        </section>
      )}

      <PhraseDialog
        open={danger !== null}
        onClose={() => setDanger(null)}
        title={danger === 'rollback' ? t('fiscal.rollback_title') : t('fiscal.cutover_title')}
        body={danger === 'rollback' ? t('fiscal.rollback_body') : t('fiscal.cutover_body')}
        phrase={danger === 'rollback' ? NFSE_ROLLBACK_PHRASE : NFSE_CUTOVER_PHRASE}
        pending={dangerMutation.isPending}
        error={dangerMutation.error ? errorMessage(dangerMutation.error) : null}
        locale={locale}
        onConfirm={async (typed) => {
          try {
            await dangerMutation.mutateAsync(typed);
            setDanger(null);
          } catch {
            // Surfaced in the dialog via `error`.
          }
        }}
      />
    </div>
  );
}
