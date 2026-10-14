/**
 * `<DreSettingsForm/>` — how this store's income statement is built (CONTRACT §10.3 + §10.5): tax regime,
 * DAS split, and which DRE line each gateway/installment/chargeback money fact lands on. Every choice that
 * has not been confirmed by an accountant is marked "provisório — confirme com seu contador"; confirming is
 * an explicit action (the system never confirms for you). Provisional choices are DATA, so the contador can
 * change them without touching a single money record.
 *
 * Backend: `GET/PUT /api/finance/dre-settings`. Confirming a choice is a `PUT` with `confirmations[name]` (there is no
 * /confirm route); changing a choice's VALUE returns it to provisional server-side; an absent confirmation is provisional.
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { Field, FormError, HelpTip, Input, ListSkeleton, Notice, PageHeader, RefreshingBar, RetryError, Select, Textarea } from './controls';
import {
  DRE_ASSIGNABLE_LINES,
  DRE_LINE_SETTING_KEYS,
  FINANCE_TAX_REGIMES,
  type DreAssignableLine,
  type DreLineSettingKey,
  type DreSettingsInput,
  type FinanceTaxRegime,
} from './dreTypes';
import { formatDateTime } from './format';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';

export interface DreSettingsFormProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
}

function ChoiceBadge({ choice }: { choice: { provisional: boolean; confirmed_at: string | null } }) {
  if (!choice.provisional) {
    return (
      <Badge variant="default">
        {t('dre_settings.confirmed')}
        {choice.confirmed_at ? ` · ${formatDateTime(choice.confirmed_at)}` : ''}
      </Badge>
    );
  }
  return <Badge variant="outline">{t('dre_settings.provisional')}</Badge>;
}

export function DreSettingsForm({ hooks, isAdmin = false }: DreSettingsFormProps) {
  const query = hooks.useDreSettings();
  const m = hooks.useDreSettingsMutations();
  const [draft, setDraft] = React.useState<DreSettingsInput>({});
  const [note, setNote] = React.useState('');
  const [shareError, setShareError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  const settings = query.data;

  if (query.showSkeleton) return <ListSkeleton rows={6} />;
  if (query.isError && !settings) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(query.error)}`} onRetry={() => query.refetch()} retryLabel={t('common.retry')} />;
  }
  if (!settings) return null;

  // Draft over server data: a field the user has not touched shows the stored value.
  const regime: FinanceTaxRegime = draft.tax_regime ?? settings.tax_regime;
  const split = draft.das_split_irpj_csll ?? settings.das_split_irpj_csll;
  const shareBps = draft.das_irpj_csll_share_bps ?? settings.das_irpj_csll_share_bps;
  const lineValue = (k: DreLineSettingKey): DreAssignableLine => draft[k] ?? settings.choices[k].value;
  const dirty = Object.keys(draft).length > 0;
  const mutErr = m.save.error ?? m.confirm.error;

  function set<K extends keyof DreSettingsInput>(k: K, v: DreSettingsInput[K]) {
    setSaved(false);
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setShareError(null);
    if (split && regime === 'simples') {
      if (!shareBps || shareBps <= 0 || shareBps > 10_000) {
        setShareError(t('dre_settings.share_invalid'));
        return;
      }
    }
    try {
      await m.save.mutateAsync(draft);
      setDraft({}); // the saved values now come from the server; confirming other fields never drops unsaved edits
      setSaved(true);
    } catch {
      // Surfaced below.
    }
  }

  async function confirm(field: DreLineSettingKey) {
    try {
      await m.confirm.mutateAsync({ fields: [field], note: note.trim() || null });
    } catch {
      // Surfaced below.
    }
  }

  return (
    <form onSubmit={save} noValidate className="space-y-4" aria-busy={query.isRefreshing} aria-label={t('dre_settings.title')}>
      <PageHeader title={t('dre_settings.title')} subtitle={t('dre_settings.subtitle')} />
      <RefreshingBar active={query.isRefreshing} label={t('common.refreshing')} />
      {regime === 'unknown' ? <Notice tone="warning">{t('dre_settings.regime_unknown')}</Notice> : null}
      <Notice>{t('dre_settings.provisional_explainer')}</Notice>

      <fieldset className="space-y-3 rounded-md border p-3" disabled={!isAdmin}>
        <legend className="px-1 text-sm font-semibold">{t('dre_settings.regime_section')}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('dre_settings.tax_regime')}>
            <Select value={regime} onChange={(e) => set('tax_regime', e.target.value as FinanceTaxRegime)}>
              {FINANCE_TAX_REGIMES.map((r) => <option key={r} value={r}>{t(`finance_regime.${r}`)}</option>)}
            </Select>
          </Field>
          {settings.tax_regime_prefilled && !('tax_regime' in draft) ? (
            <p className="self-end pb-1 text-xs text-muted-foreground">{t('dre_settings.regime_prefilled')}</p>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">{t(`dre_settings.regime_help_${regime}`)}</p>
        {regime === 'simples' ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={split} onChange={(e) => set('das_split_irpj_csll', e.target.checked)} />
              {t('dre_settings.das_split')}
              <HelpTip label={t('dre_settings.das_split_help_label')}>{t('dre_settings.das_split_help')}</HelpTip>
            </label>
            {split ? (
              <Field label={t('dre_settings.das_share')} error={shareError}>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step="0.01"
                  value={shareBps ? String(shareBps / 100) : ''}
                  onChange={(e) => set('das_irpj_csll_share_bps', e.target.value === '' ? 0 : Math.round(Number(e.target.value) * 100))}
                />
              </Field>
            ) : null}
          </div>
        ) : null}
      </fieldset>

      <fieldset className="space-y-3 rounded-md border p-3" disabled={!isAdmin}>
        <legend className="px-1 text-sm font-semibold">{t('dre_settings.lines_section')}</legend>
        {DRE_LINE_SETTING_KEYS.map((key) => (
          <div key={key} className="grid items-end gap-2 sm:grid-cols-[1fr_auto]" data-setting={key}>
            <div className="space-y-1">
              <Field label={t(`dre_settings.${key}`)}>
                <Select value={lineValue(key)} onChange={(e) => set(key, e.target.value as DreAssignableLine)}>
                  {DRE_ASSIGNABLE_LINES.map((l) => <option key={l} value={l}>{t(`dre_line.${l}`)}</option>)}
                </Select>
              </Field>
              <p className="text-xs text-muted-foreground">{t(`dre_settings.${key}_help`)}</p>
            </div>
            <div className="flex items-center gap-2 pb-5 text-sm">
              <ChoiceBadge choice={settings.choices[key]} />
              {isAdmin ? (
                <Button type="button" size="sm" variant="outline" disabled={m.confirm.isPending} onClick={() => confirm(key)}>
                  {t('dre_settings.confirm_action')}
                </Button>
              ) : null}
            </div>
          </div>
        ))}
        {isAdmin ? (
          <Field label={t('dre_settings.confirm_note')}>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('dre_settings.confirm_note_hint')} maxLength={500} />
          </Field>
        ) : null}
      </fieldset>

      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {saved && !dirty ? <p role="status" className="text-sm text-muted-foreground">{t('common.saved')}</p> : null}
      {isAdmin ? (
        <Button type="submit" disabled={!dirty || m.save.isPending}>{m.save.isPending ? t('common.saving') : t('common.save')}</Button>
      ) : (
        <p className="text-xs text-muted-foreground">{t('dre_settings.admin_only')}</p>
      )}
    </form>
  );
}
