/**
 * InfoPopover — the small muted "i" next to a label that explains it.
 *
 * Two pieces, deliberately separate:
 *
 *   - `InfoPopover` — the trigger + popover shell. A muted `Info` icon button
 *     (the accessible name is `label`; a tooltip is NOT one) that opens a
 *     Radix popover. Keyboard: Tab focuses it, Enter/Space opens, Esc closes
 *     and returns focus. Touch: the visible icon stays small so it does not
 *     reflow a dense row, but its hit area is padded (`after:-inset-2`) to a
 *     usable target.
 *   - `InfoSecoes` — the usual body: an optional title, bullet sections
 *     ("Dados lidos deste documento", "Usado em", …) and an optional footer
 *     (typically a "Ver no guia" link the caller builds with its router).
 *
 * 🔴 THE BODY MOUNTS ONLY WHEN OPEN.
 * ----------------------------------
 * Radix unmounts `PopoverContent` while closed, so `children` is rendered
 * lazily. A product wrapper can therefore put a data hook INSIDE the body:
 * nothing is fetched until someone actually opens the "i", and a row that
 * carries the icon stays presentational (renderable in a test with no query
 * provider) as long as it is never opened.
 *
 * The trigger stops click propagation: these icons sit inside clickable rows,
 * labels and table cells, and opening an explanation must never also toggle
 * the row it explains.
 */
import type { ReactNode } from "react";
import { Info } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "../design-system/ui/popover";
import { cn } from "../utils";

type Lado = "top" | "right" | "bottom" | "left";

export interface InfoPopoverProps {
  /** Accessible name of the trigger, e.g. "Sobre: RG". Required — an
   *  icon-only button without a name is invisible to a screen reader. */
  label: string;
  /** The popover body. Mounted only while open (see the file docblock). */
  children: ReactNode;
  side?: Lado;
  align?: "start" | "center" | "end";
  testId?: string;
  /** Extra classes for the trigger button. */
  className?: string;
  /** Extra classes for the popover panel (default width `w-80`). */
  contentClassName?: string;
}

export function InfoPopover({
  label,
  children,
  side = "bottom",
  align = "start",
  testId = "info-popover",
  className,
  contentClassName,
}: InfoPopoverProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          data-testid={`${testId}-trigger`}
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "relative inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full align-middle",
            "text-muted-foreground/70 transition-colors hover:text-foreground",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
            // Padded touch target without reflowing the row it sits in.
            "after:absolute after:-inset-2 after:content-['']",
            className,
          )}
        >
          <Info className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side={side}
        align={align}
        data-testid={`${testId}-content`}
        className={cn("w-80 max-w-[calc(100vw-2rem)] p-3 text-sm", contentClassName)}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}

export interface InfoSecao {
  titulo: string;
  itens: ReactNode[];
  /** Shown instead of the bullets when `itens` is empty. Omit to hide an
   *  empty section entirely. */
  vazio?: string;
}

export interface InfoSecoesProps {
  titulo?: ReactNode;
  secoes: InfoSecao[];
  /** Free text under the sections (a caveat, a hint). */
  nota?: ReactNode;
  /** Footer — typically a "Ver no guia" link. */
  rodape?: ReactNode;
  testId?: string;
}

export function InfoSecoes({ titulo, secoes, nota, rodape, testId = "info-secoes" }: InfoSecoesProps) {
  const visiveis = secoes.filter((s) => s.itens.length > 0 || s.vazio);
  return (
    <div className="space-y-2" data-testid={testId}>
      {titulo && <p className="font-semibold leading-tight">{titulo}</p>}
      {visiveis.map((s) => (
        <div key={s.titulo} data-testid={`${testId}-secao`}>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{s.titulo}</p>
          {s.itens.length > 0 ? (
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-sm">
              {s.itens.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-0.5 text-sm italic text-muted-foreground">{s.vazio}</p>
          )}
        </div>
      ))}
      {nota && <p className="text-xs text-muted-foreground">{nota}</p>}
      {rodape && <div className="border-t pt-2 text-sm">{rodape}</div>}
    </div>
  );
}
