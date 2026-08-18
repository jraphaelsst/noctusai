/**
 * MembrosPopover — screenshot 08: search + "Membros do Quadro" list with
 * avatars. Maps to corretor-responsável (D10) — the roster IS the org's
 * `lead_corretores`, the same list `useLeadCorretores` already serves for
 * the Corretor filter on `ClientesBoard`; this popover is not a new roster
 * source, just a picker over it. PROJECT.md §3/§4.
 *
 * Presentational (S3): `onToggleMembro` is the only callback out; the
 * caller (`useSetCardMembrosMutation`) owns the PUT.
 */
import { useState } from "react";
import { Check, Users } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Membro } from "@/types/cardHub";

export interface MembrosPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  allMembros: Membro[];
  selectedMembroIds: string[];
  onToggleMembro: (membroId: string) => void;
  saving?: boolean;
}

function initials(nome: string): string {
  const parts = nome.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}

export function MembrosPopover({
  open,
  onOpenChange,
  allMembros,
  selectedMembroIds,
  onToggleMembro,
  saving,
}: MembrosPopoverProps) {
  const [search, setSearch] = useState("");
  const visible = allMembros.filter((m) => m.nome.toLowerCase().includes(search.toLowerCase()));

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" data-testid="membros-trigger">
          <Users className="mr-2 h-4 w-4" />
          Membros
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" data-testid="membros-popover">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold">Membros</p>
        </div>

        <Input
          placeholder="Pesquisar membros"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mb-3"
          data-testid="membros-search"
        />

        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Membros do Quadro
        </p>
        <div className="max-h-64 space-y-0.5 overflow-y-auto" data-testid="membros-list">
          {visible.map((membro) => {
            const checked = selectedMembroIds.includes(membro.id);
            return (
              <button
                key={membro.id}
                type="button"
                disabled={saving}
                onClick={() => onToggleMembro(membro.id)}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent"
                data-testid={`membro-item-${membro.id}`}
              >
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-red-600 text-xs text-white">
                    {initials(membro.nome)}
                  </AvatarFallback>
                </Avatar>
                <span className="flex-1 truncate text-left">{membro.nome}</span>
                {checked && <Check className="h-4 w-4 text-primary" data-testid={`membro-checked-${membro.id}`} />}
              </button>
            );
          })}
          {visible.length === 0 && (
            <p className="py-2 text-center text-xs text-muted-foreground">Nenhum membro encontrado.</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
