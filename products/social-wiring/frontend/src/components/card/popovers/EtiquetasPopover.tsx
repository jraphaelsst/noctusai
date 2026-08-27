/**
 * EtiquetasPopover — screenshot 05: search box, colour swatches (with
 * optional label text), per-label edit affordance, "Criar uma nova
 * etiqueta", and — mandatory per the brief, it is in the shot — "Habilitar
 * o modo compatível para usuários com daltonismo" (D6 inherits this).
 * PROJECT.md §4.
 *
 * Presentational (S3): every tag toggle / create / colour-blind-mode flip
 * is a callback out; the caller (via `useCardHub`) owns the PUT/POST.
 */
import { useState } from "react";
import { Check, Pencil, Tag as TagIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { TooltipCaption } from "../TooltipIconButton";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { Tag } from "@/types/cardHub";

const SWATCHES = [
  "#eb5a46",
  "#d29034",
  "#f2d600",
  "#61bd4f",
  "#0079bf",
  "#c377e0",
  "#344563",
];

export interface EtiquetasPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  allTags: Tag[];
  selectedTagIds: string[];
  onToggleTag: (tagId: string) => void;
  onCreateTag: (nome: string, cor: string) => void;
  onEditTag: (tagId: string) => void;
  colorBlindMode: boolean;
  onToggleColorBlindMode: (enabled: boolean) => void;
  saving?: boolean;
}

export function EtiquetasPopover({
  open,
  onOpenChange,
  allTags,
  selectedTagIds,
  onToggleTag,
  onCreateTag,
  onEditTag,
  colorBlindMode,
  onToggleColorBlindMode,
  saving,
}: EtiquetasPopoverProps) {
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [novaCor, setNovaCor] = useState(SWATCHES[0]);

  const visible = allTags.filter((t) => t.nome.toLowerCase().includes(search.toLowerCase()));

  function submitCreate() {
    if (!novoNome.trim()) return;
    onCreateTag(novoNome.trim(), novaCor);
    setNovoNome("");
    setCreating(false);
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setCreating(false);
      }}
      // `modal` — see MembrosPopover: portaled out of the card dialog, whose
      // scroll lock otherwise swallows wheel events aimed in here.
      modal
    >
      {/* Icon-only, caption on hover — the card's rule for every action
          (see `TooltipIconButton`). `aria-label` carries the SAME word, so
          the button keeps an accessible name a hover cannot provide.
          `TooltipCaption` wraps the PopoverTrigger rather than replacing the
          Button, because the trigger is what must own the ref Radix hands it. */}
      <TooltipCaption label="Etiquetas">
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            aria-label="Etiquetas"
            data-testid="etiquetas-trigger"
          >
            <TagIcon className="h-4 w-4" aria-hidden="true" />
          </Button>
        </PopoverTrigger>
      </TooltipCaption>
      <PopoverContent className="w-80" data-testid="etiquetas-popover">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold">Etiquetas</p>
        </div>

        <Input
          placeholder="Buscar etiquetas…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mb-3"
          data-testid="etiquetas-search"
        />

        <div className="mb-3 space-y-1.5" data-testid="etiquetas-list">
          {visible.map((tag) => {
            const checked = selectedTagIds.includes(tag.id);
            return (
              <div key={tag.id} className="flex items-center gap-2">
                <Checkbox
                  checked={checked}
                  disabled={saving}
                  onCheckedChange={() => onToggleTag(tag.id)}
                  data-testid={`etiqueta-checkbox-${tag.id}`}
                />
                <button
                  type="button"
                  onClick={() => onToggleTag(tag.id)}
                  className="flex h-8 flex-1 items-center justify-between rounded px-2 text-sm font-medium text-white"
                  style={{ backgroundColor: tag.cor }}
                  data-testid={`etiqueta-swatch-${tag.id}`}
                >
                  <span className="truncate">{tag.nome}</span>
                  {colorBlindMode && checked && (
                    <Check className="h-4 w-4 shrink-0" data-testid={`etiqueta-colorblind-check-${tag.id}`} />
                  )}
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => onEditTag(tag.id)}
                  data-testid={`etiqueta-edit-${tag.id}`}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
          {visible.length === 0 && (
            <p className="py-2 text-center text-xs text-muted-foreground">Nenhuma etiqueta encontrada.</p>
          )}
        </div>

        {creating ? (
          <div className="mb-3 space-y-2 rounded border p-2">
            <Input
              placeholder="Nome da etiqueta"
              value={novoNome}
              onChange={(e) => setNovoNome(e.target.value)}
              data-testid="etiquetas-nova-nome"
              autoFocus
            />
            <div className="flex flex-wrap gap-1.5">
              {SWATCHES.map((cor) => (
                <button
                  key={cor}
                  type="button"
                  className={cn(
                    "h-6 w-6 rounded",
                    novaCor === cor && "ring-2 ring-offset-1 ring-offset-background",
                  )}
                  style={{ backgroundColor: cor }}
                  onClick={() => setNovaCor(cor)}
                  data-testid={`etiquetas-nova-cor-${cor}`}
                />
              ))}
            </div>
            <Button size="sm" className="w-full" onClick={submitCreate} data-testid="etiquetas-nova-salvar">
              Adicionar
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="mb-3 w-full"
            onClick={() => setCreating(true)}
            data-testid="etiquetas-criar-btn"
          >
            Criar uma nova etiqueta
          </Button>
        )}

        <div className="flex items-center justify-between gap-2 border-t pt-3">
          <label htmlFor="etiquetas-daltonismo" className="text-xs text-muted-foreground">
            Habilitar o modo compatível para usuários com daltonismo
          </label>
          <Switch
            id="etiquetas-daltonismo"
            checked={colorBlindMode}
            onCheckedChange={onToggleColorBlindMode}
            data-testid="etiquetas-daltonismo-switch"
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
