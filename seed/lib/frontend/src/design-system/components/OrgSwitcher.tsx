/**
 * `<OrgSwitcher/>` — the AppShell header control a MEMBER uses to switch org (owner D1,
 * 2026-10-14; roadmap multi-org-membership-2026-10 § P2.4).
 *
 * Shows the org this visit is in and opens the SAME picker staff use (`OrgPickerModal`, via
 * `useOrgSelection().openPicker`) — no second mechanism. Rendered only when the picker applies
 * to a member (>=2 eligible orgs for this product) and a choice was made: during the required
 * entry pick the modal is already up. Platform staff keep their own controls (`ActingAsBanner`);
 * everyone else renders nothing.
 */
import { Building2, ChevronsUpDown } from 'lucide-react';

import { useOrgSelection } from '../../org-selection';

export interface OrgSwitcherViewProps {
  orgNome: string;
  onSwitch: () => void;
}

export function OrgSwitcherView({ orgNome, onSwitch }: OrgSwitcherViewProps) {
  return (
    <button
      type="button"
      data-testid="org-switcher"
      onClick={onSwitch}
      aria-label={`Trocar organização (atual: ${orgNome})`}
      title="Trocar organização"
      className="inline-flex h-9 max-w-[11rem] items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-sm text-foreground hover:bg-accent sm:max-w-[16rem]"
    >
      <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="truncate">{orgNome}</span>
      <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
    </button>
  );
}

export function OrgSwitcher() {
  const sel = useOrgSelection();
  const s = sel.selection;
  if (!sel.memberPicker || sel.pickerRequired || !s.selection_id || !s.org) return null;
  return <OrgSwitcherView orgNome={s.org.nome} onSwitch={sel.openPicker} />;
}
