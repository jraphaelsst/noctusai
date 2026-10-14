/**
 * "Mover usuário" (owner D3, 2026-10-14) — move a member from the org on screen to another org
 * the viewer manages. The actor picks, EVERY time: the target org (only orgs they manage), the
 * role there (never above their own role in the target — staff count as owner) and the mode:
 * "Transferir" ends the current membership, "Adicionar" keeps both. No mode is preselected on
 * purpose: the choice is the actor's each time. `POST /api/team/move`; the SQL op decides.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, FormError, Select,
} from '@noctusai/lib/design-system';

import { useMoveMember } from '../../hooks/useTeam';
import type { MoveMode, TeamMember, TeamRole, TeamScopeOrg } from '../../hooks/useTeam';
import { teamErrorMessage } from '../../lib/team-errors';
import { roleName } from './roleName';

export interface MoveMemberDialogProps {
  member: TeamMember;
  sourceOrg: TeamScopeOrg;
  /** Orgs the viewer manages, the source excluded. */
  targets: TeamScopeOrg[];
  roles: TeamRole[];
  onClose: () => void;
}

const MODES: { value: MoveMode; label: string; help: string }[] = [
  {
    value: 'transfer',
    label: 'Transferir (sai da org atual)',
    help: 'A pessoa deixa esta organização e passa a fazer parte apenas da organização de destino.',
  },
  {
    value: 'add',
    label: 'Adicionar (mantém as duas)',
    help: 'A pessoa continua nesta organização e também passa a fazer parte da organização de destino.',
  },
];

/** Roles the actor may grant in `target`: never `owner` unless they are owner there (D3). */
export function grantableMoveRoles(roles: TeamRole[], target: TeamScopeOrg | undefined): TeamRole[] {
  return roles.filter((r) => r.slug !== 'owner' || target?.actorRole === 'owner');
}

export function MoveMemberDialog({ member, sourceOrg, targets, roles, onClose }: MoveMemberDialogProps) {
  const [targetId, setTargetId] = useState('');
  const [role, setRole] = useState(member.org_role === 'owner' ? '' : member.org_role);
  const [mode, setMode] = useState<MoveMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const move = useMoveMember();

  const target = targets.find((t) => t.id === targetId);
  const allowed = grantableMoveRoles(roles, target);
  const roleOk = allowed.some((r) => r.slug === role);
  const canSubmit = !!target && roleOk && mode !== null && !move.isPending;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!target || !mode || !roleOk) return;
    setError(null);
    try {
      const out = await move.mutateAsync({
        user_id: member.id, source_org_id: sourceOrg.id, target_org_id: target.id, role, mode,
      });
      const papel = roleName(out?.org_role ?? role, roles);
      toast.success(mode === 'transfer'
        ? `${member.nome} foi transferido(a) para ${target.nome} como ${papel}.`
        : `${member.nome} foi adicionado(a) a ${target.nome} como ${papel} e continua em ${sourceOrg.nome}.`);
      onClose();
    } catch (err) {
      setError(teamErrorMessage(err, 'Não foi possível mover o usuário.'));
    }
  }

  return (
    <Dialog open onClose={move.isPending ? () => {} : onClose} title="Mover usuário">
      <form onSubmit={submit}>
        <DialogHeader>
          <h2 className="text-base font-semibold text-foreground">Mover usuário</h2>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <p className="text-sm text-muted-foreground">
            <strong className="text-foreground">{member.nome}</strong> ({member.email}) — hoje em{' '}
            <strong className="text-foreground">{sourceOrg.nome}</strong>.
          </p>
          <FormError message={error} />
          <Field label="Organização de destino" required>
            <Select
              data-testid="move-target"
              value={targetId}
              onChange={(e) => { setTargetId(e.target.value); setError(null); }}
              className="h-10"
            >
              <option value="" disabled>Selecione…</option>
              {targets.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
            </Select>
          </Field>
          <Field label="Papel na organização de destino" required>
            <Select
              data-testid="move-role"
              value={roleOk ? role : ''}
              onChange={(e) => setRole(e.target.value)}
              disabled={!target}
              className="h-10"
            >
              <option value="" disabled>Selecione…</option>
              {allowed.map((r) => <option key={r.slug} value={r.slug}>{r.name}</option>)}
            </Select>
          </Field>
          <fieldset className="space-y-2">
            <legend className="text-xs font-medium text-foreground">
              Como mover<span className="text-destructive"> *</span>
            </legend>
            {MODES.map((m) => (
              <label
                key={m.value}
                className="flex cursor-pointer items-start gap-3 rounded-md border border-border p-3 text-sm hover:bg-muted/50"
              >
                <input
                  type="radio"
                  name="move-mode"
                  value={m.value}
                  checked={mode === m.value}
                  onChange={() => setMode(m.value)}
                  className="mt-0.5"
                />
                <span>
                  <span className="block font-medium text-foreground">{m.label}</span>
                  <span className="block text-xs text-muted-foreground">{m.help}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={move.isPending}>Cancelar</Button>
          <Button type="submit" disabled={!canSubmit}>{move.isPending ? 'Movendo...' : 'Mover'}</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
