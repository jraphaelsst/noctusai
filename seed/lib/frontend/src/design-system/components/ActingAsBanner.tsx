/**
 * `<ActingAsBanner/>` — persistent bar for platform staff inside a product
 * (org-picker contract):
 *
 *   "Você está atuando em <org> (NoctusAI)"  [Trocar org]
 *
 * Full banner when `available && acting`; a slim "Trocar org" bar when
 * `available && !acting`; NOTHING for non-staff (`!available`). Role/label
 * come from `/api/me/access`, never from user_metadata.
 */
import { useOrgSelection } from '../../org-selection';

export interface ActingAsBannerViewProps {
  orgNome: string;
  onSwitch: () => void;
}

export function ActingAsBannerView({ orgNome, onSwitch }: ActingAsBannerViewProps) {
  return (
    <div
      role="status"
      data-testid="acting-as-banner"
      className="sticky top-0 z-40 flex items-center justify-center gap-3 border-b border-amber-500/40 bg-amber-500/15 px-4 py-2 text-sm text-amber-900 dark:text-amber-200"
    >
      <span>
        Você está atuando em <strong>{orgNome}</strong> (NoctusAI)
      </span>
      <button
        type="button"
        onClick={onSwitch}
        className="inline-flex items-center rounded-md border border-amber-600/50 bg-background px-3 py-1 text-xs font-medium text-foreground hover:bg-accent"
      >
        Trocar org
      </button>
    </div>
  );
}

/** Slim variant for staff in their own (home) org: just the swap control. */
export function OrgSwitchBarView({ orgNome, onSwitch }: ActingAsBannerViewProps) {
  return (
    <div
      data-testid="org-switch-bar"
      className="flex items-center justify-end gap-2 border-b border-border bg-muted/40 px-4 py-1 text-xs text-muted-foreground"
    >
      <span>{orgNome}</span>
      <button
        type="button"
        onClick={onSwitch}
        className="rounded-md border border-border bg-background px-2 py-0.5 text-xs font-medium text-foreground hover:bg-accent"
      >
        Trocar org
      </button>
    </div>
  );
}

export function ActingAsBanner() {
  // Visibility is driven off query `data` (never isLoading).
  const sel = useOrgSelection();
  const s = sel.selection;
  if (!s.available || !s.org) return null;
  if (!s.acting) {
    // Staff in their own org: compact control, hidden while the mandatory picker is up.
    if (s.required) return null;
    return <OrgSwitchBarView orgNome={s.org.nome} onSwitch={sel.openPicker} />;
  }
  return <ActingAsBannerView orgNome={s.org.nome} onSwitch={sel.openPicker} />;
}
