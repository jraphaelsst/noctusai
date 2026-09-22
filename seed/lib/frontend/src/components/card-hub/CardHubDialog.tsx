/**
 * CardHubDialog — the card detail: rail + active subpage + activity pane.
 *
 * MOVED from the chrome of
 * `products/social-wiring/frontend/src/components/card/ClienteCardDialog.tsx`
 * (`:489-1046`) into the seed card hub
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` §2,
 * Slice C). Desktop markup, classes and data-testids are SW's: SW's
 * `ClienteCardDialog` becomes a thin adapter over this (Slice F) and its
 * 2325-line suite passes unchanged.
 *
 * 🔴 SUBPAGES ARE A REGISTRY
 * --------------------------
 * The dialog knows no subpage. A product declares `subpages` — each with its
 * rail entry (`key`, `label`, `icon`), an optional `toolbar` rendered above it
 * (Geral's quick actions), `isEmpty` (rail entry disabled, never dropped) and a
 * `render(ctx)` THUNK, so a subpage nobody opened costs nothing. Only the
 * ACTIVE subpage renders. `onSubpageChange` reports each selection upward so
 * the owner can fetch a tab's data when it is first opened.
 *
 * 🔴 MOBILE-FIRST (R0) — a full-screen sheet below 640px
 * ------------------------------------------------------
 * Every mobile rule is a `max-sm:` utility, so desktop (≥640px) keeps SW's
 * exact classes. Below `sm` the dialog fills the viewport (`100dvh` — the
 * visible height, not the one behind the mobile URL bar), drops its frame, and
 * scrolls as ONE column: the rail becomes a sticky, horizontally scrollable
 * tab strip, the subpage follows, and the activity pane stacks below it.
 * Touch targets reach 40px. `data-layout` mirrors the breakpoint for tests and
 * behaviour (see `useSheetLayout`).
 *
 * States: loading / error / not-found / success at the dialog level. `isLoading`
 * is the caller's `showSkeleton` (`isPending && !data`) — never a raw
 * `isLoading`/`isFetching` (`KB § PATTERNS/frontend/lying-loading-state.md`).
 *
 * Presentational only: props in, callbacks out; the owner holds the queries
 * (see `createCardHubHooks`).
 */
import type { ReactNode } from "react";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertCircle } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../../design-system/ui/radix-dialog";
import { ScrollArea } from "../../design-system/ui/scroll-area";
import { cn } from "../../utils";

import { CardSidebarNav } from "./CardSidebarNav";
import { ComentarioComposer, type ComentarioComposerProps } from "./ComentarioComposer";
import { Timeline, type TimelineProps } from "./Timeline";
import { useSheetLayout } from "./useSheetLayout";

/** What a subpage's `render` receives. */
export interface CardHubRenderCtx<K extends string = string> {
  /** The active subpage (the one being rendered). */
  subpage: K;
  /** Switch subpage from inside one (e.g. a "see all" link). */
  select: (key: K) => void;
  /** True below 640px — the full-screen sheet layout. */
  isSheet: boolean;
}

/** One entry of the subpage registry. */
export interface CardSubpage<K extends string = string> {
  key: K;
  label: string;
  icon: LucideIcon;
  render: (ctx: CardHubRenderCtx<K>) => ReactNode;
  /** Nothing to show — the rail entry renders disabled (never dropped). */
  isEmpty?: boolean;
  /** Rendered above the subpage, below the header (Geral: `GeralActions`). */
  toolbar?: ReactNode;
}

export interface CardHubActivityProps {
  timeline: TimelineProps;
  composer: ComentarioComposerProps;
  /** The pane's heading. */
  title?: string;
}

export interface CardHubDialogProps<K extends string = string> {
  open: boolean;
  onClose: () => void;
  /** The caller's `showSkeleton` — `isPending && !data`. */
  isLoading: boolean;
  error?: string | null;
  notFound?: boolean;

  /** The card's title (also the dialog's accessible name). */
  nome: string;
  /** Rendered beside the title, top-right — surface/product actions. */
  headerActions?: ReactNode;

  subpages: readonly CardSubpage<K>[];
  /** The open-on-mount subpage. Defaults to the first registered one. */
  defaultSubpage?: K;
  onSubpageChange?: (key: K) => void;

  activity: CardHubActivityProps;

  /** Root testid; `-error` / `-loading` / `-not-found` derive from it. */
  testId?: string;
}

export function CardHubDialog<K extends string>({
  open,
  onClose,
  isLoading,
  error,
  notFound,
  nome,
  headerActions,
  subpages,
  defaultSubpage,
  onSubpageChange,
  activity,
  testId = "card-hub-dialog",
}: CardHubDialogProps<K>) {
  const [subpage, setSubpage] = useState<K>(
    () => defaultSubpage ?? (subpages[0]?.key as K),
  );
  const isSheet = useSheetLayout();

  // 🔴 Reported upward so the owner can fetch a tab's data WHEN IT IS OPENED.
  function selecionar(key: K) {
    setSubpage(key);
    onSubpageChange?.(key);
  }

  const active = subpages.find((s) => s.key === subpage) ?? subpages[0];
  const emptyKeys = subpages.filter((s) => s.isEmpty).map((s) => s.key);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {/*
        90vh × 90vw. The card carries three panes; the rail's column is the
        rail's COLLAPSED width and stays that width while it is open — see
        `CardSidebarNav`: the expansion floats over the middle pane rather
        than squeezing it.

        Below `sm`: the full-screen sheet (see the module docblock).
      */}
      <DialogContent
        className={cn(
          "grid h-[90vh] w-[90vw] max-w-[90vw] grid-cols-1 gap-0 overflow-hidden p-0",
          "md:grid-cols-[3.25rem_1fr_360px]",
          "max-sm:h-[100dvh] max-sm:w-screen max-sm:max-w-none max-sm:content-start",
          "max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0",
        )}
        data-testid={testId}
        data-layout={isSheet ? "sheet" : "dialog"}
      >
        {error ? (
          <div className="col-span-full flex flex-col items-center justify-center gap-3 p-10 text-center">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-destructive" data-testid={`${testId}-error`}>
              Não foi possível carregar este cartão.
            </p>
          </div>
        ) : isLoading ? (
          <div className="col-span-full space-y-3 p-10" data-testid={`${testId}-loading`}>
            <div className="h-6 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-32 w-full animate-pulse rounded bg-muted" />
          </div>
        ) : notFound ? (
          <div className="col-span-full flex items-center justify-center p-10">
            <p className="text-sm text-muted-foreground" data-testid={`${testId}-not-found`}>
              Cartão não encontrado.
            </p>
          </div>
        ) : (
          <>
            <DialogTitle className="sr-only">{nome}</DialogTitle>
            <DialogDescription className="sr-only">
              Detalhes do cartão de {nome}
            </DialogDescription>

            {/* ── Left rail — subpage navigation (hover rail) ─────── */}
            <CardSidebarNav
              items={subpages}
              active={active?.key ?? subpage}
              onSelect={selecionar}
              emptyKeys={emptyKeys}
            />

            {/* ── Middle pane — the active subpage ────────────────── */}
            <ScrollArea className="border-r p-6 max-sm:border-b max-sm:border-r-0 max-sm:p-4">
              <div className="mb-4 flex items-start justify-between gap-3">
                <h2 className="text-xl font-semibold">{nome}</h2>
                <div className="flex shrink-0 items-center gap-1">{headerActions}</div>
              </div>

              {active?.toolbar}

              {active?.render({ subpage: active.key, select: selecionar, isSheet })}
            </ScrollArea>

            {/* ── Right pane — Comentários e atividade ────────────── */}
            <div
              className="flex min-h-0 flex-col p-6 max-sm:p-4"
              data-testid={`${testId}-activity`}
            >
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                {activity.title ?? "Comentários e atividade"}
              </h3>

              <ComentarioComposer {...activity.composer} />

              <ScrollArea className="mt-4 flex-1">
                <Timeline {...activity.timeline} />
              </ScrollArea>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
