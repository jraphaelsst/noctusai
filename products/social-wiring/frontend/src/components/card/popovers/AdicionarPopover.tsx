/**
 * AdicionarPopover — screenshot 04: the `+ Adicionar` extension menu.
 * Etiquetas / Datas / Checklist / Membros / Anexo, each with a one-line
 * explainer, verbatim from the shot. PROJECT.md §4.
 *
 * Presentational (S3): `onSelect` reports which row was picked; the caller
 * (`ClienteCardDialog`) decides what opens (another popover, or the file
 * picker for Anexo).
 */
import { Paperclip, Plus, Tag, Users, Calendar, CheckSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export type AdicionarOption = "etiquetas" | "datas" | "checklist" | "membros" | "anexo";

export interface AdicionarPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (option: AdicionarOption) => void;
}

const ROWS: { option: AdicionarOption; icon: React.ComponentType<{ className?: string }>; title: string; explainer: string }[] = [
  { option: "etiquetas", icon: Tag, title: "Etiquetas", explainer: "Organize, categorize e priorize" },
  { option: "datas", icon: Calendar, title: "Datas", explainer: "Datas de início, datas de entrega e lembretes" },
  { option: "checklist", icon: CheckSquare, title: "Checklist", explainer: "Adicionar subtarefas" },
  { option: "membros", icon: Users, title: "Membros", explainer: "Atribuir membros" },
  { option: "anexo", icon: Paperclip, title: "Anexo", explainer: "Adicione links, páginas, itens de trabalho e muito mais" },
];

export function AdicionarPopover({ open, onOpenChange, onSelect }: AdicionarPopoverProps) {
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button size="sm" data-testid="adicionar-trigger">
          <Plus className="mr-2 h-4 w-4" />
          Adicionar
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" data-testid="adicionar-popover">
        <p className="mb-3 text-sm font-semibold">Adicionar ao cartão</p>
        <div className="space-y-1">
          {ROWS.map(({ option, icon: Icon, title, explainer }) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                onSelect(option);
                onOpenChange(false);
              }}
              className="flex w-full items-start gap-3 rounded p-2 text-left hover:bg-accent"
              data-testid={`adicionar-opcao-${option}`}
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <span>
                <span className="block text-sm font-medium">{title}</span>
                <span className="block text-xs text-muted-foreground">{explainer}</span>
              </span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
