/** `<LeadsFilterBar/>` -- search (name / phone / e-mail), origin, first-contact range, and (list only) stage. */
import * as React from 'react';

import { Button } from '../design-system/ui/Button';
import { Input, Select } from './controls';
import { hasActiveFilters } from './format';
import { t } from './i18n';
import type { LeadFiltersState, LeadsConfigData } from './types';
import { useDebounced } from './useLeadFilters';

export interface LeadsFilterBarProps {
  value: LeadFiltersState;
  onChange: (next: LeadFiltersState) => void;
  config: LeadsConfigData | undefined;
  /** The list filters by stage; the board has a column per stage instead. */
  showStage?: boolean;
}

export function LeadsFilterBar({ value, onChange, config, showStage = false }: LeadsFilterBarProps) {
  const [text, setText] = React.useState(value.q ?? '');
  const debounced = useDebounced(text);
  const latest = React.useRef(value);
  latest.current = value;

  // Push the typed search up once the typing pauses; never echo back a value the parent already holds.
  React.useEffect(() => {
    if ((latest.current.q ?? '') !== debounced) onChange({ ...latest.current, q: debounced || undefined });
  }, [debounced, onChange]);
  // A parent-driven clear ("Limpar filtros" elsewhere) empties the box.
  React.useEffect(() => {
    if (!value.q) setText('');
  }, [value.q]);

  const set = (patch: Partial<LeadFiltersState>) => onChange({ ...value, ...patch });

  return (
    <div className="flex flex-wrap items-end gap-2" data-testid="leads-filters">
      <div className="min-w-[14rem] flex-1">
        <Input
          type="search"
          aria-label={t('filters.search')}
          placeholder={t('filters.search')}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <div className="w-44">
        <Select aria-label={t('filters.origin')} value={value.origin ?? ''} onChange={(e) => set({ origin: e.target.value || undefined })}>
          <option value="">{t('filters.all_origins')}</option>
          {config?.origins.map((o) => (
            <option key={o.slug} value={o.slug}>
              {o.label}
            </option>
          ))}
        </Select>
      </div>
      {showStage && (
        <div className="w-44">
          <Select aria-label={t('filters.stage')} value={value.stage ?? ''} onChange={(e) => set({ stage: e.target.value || undefined })}>
            <option value="">{t('filters.all_stages')}</option>
            {config?.stages.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.label}
              </option>
            ))}
          </Select>
        </div>
      )}
      <label className="flex items-center gap-1 text-xs text-muted-foreground">
        {t('filters.from')}
        <Input type="date" aria-label={t('filters.from')} className="w-36" value={value.from ?? ''} max={value.to || undefined} onChange={(e) => set({ from: e.target.value || undefined })} />
      </label>
      <label className="flex items-center gap-1 text-xs text-muted-foreground">
        {t('filters.to')}
        <Input type="date" aria-label={t('filters.to')} className="w-36" value={value.to ?? ''} min={value.from || undefined} onChange={(e) => set({ to: e.target.value || undefined })} />
      </label>
      {hasActiveFilters(value) && (
        <Button
          variant="ghost"
          onClick={() => {
            setText('');
            onChange({});
          }}
        >
          {t('filters.clear')}
        </Button>
      )}
    </div>
  );
}
