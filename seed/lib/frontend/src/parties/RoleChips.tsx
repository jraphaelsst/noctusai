/**
 * `<RoleChips/>` (read-only chips) and `<RolePicker/>` (toggle chips) for a party's roles.
 * A party can hold any combination of customer / supplier / employee / carrier.
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { t } from './i18n';
import { PARTY_ROLES, type PartyRole } from './types';

export function RoleChips({ roles }: { roles: readonly PartyRole[] }) {
  if (roles.length === 0) return <span className="text-xs text-muted-foreground">{t('role.none')}</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {roles.map((r) => (
        <Badge key={r} variant="outline" data-role={r}>
          {t(`role.${r}`)}
        </Badge>
      ))}
    </span>
  );
}

export interface RolePickerProps {
  value: readonly PartyRole[];
  onChange: (roles: PartyRole[]) => void;
  disabled?: boolean;
}

export function RolePicker({ value, onChange, disabled }: RolePickerProps) {
  const toggle = (role: PartyRole) =>
    onChange(value.includes(role) ? value.filter((r) => r !== role) : PARTY_ROLES.filter((r) => r === role || value.includes(r)));
  return (
    <div role="group" aria-label={t('role.group')} className="flex flex-wrap gap-2">
      {PARTY_ROLES.map((role) => {
        const on = value.includes(role);
        return (
          <button
            key={role}
            type="button"
            role="checkbox"
            aria-checked={on}
            disabled={disabled}
            onClick={() => toggle(role)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors disabled:opacity-60 ${
              on ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background hover:bg-accent'
            }`}
          >
            {t(`role.${role}`)}
          </button>
        );
      })}
    </div>
  );
}
