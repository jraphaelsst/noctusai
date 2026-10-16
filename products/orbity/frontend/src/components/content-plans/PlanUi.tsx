/** Shared bits for the Planejamento tab: modal shell, option lists, form-control classes. */
import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { ItemStatus } from "@/hooks/useContentPlans";
import type { Platform } from "@/hooks/useConteudo";

export const INPUT_CLS =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
export const TEXTAREA_CLS =
  "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
export const BTN_PRIMARY =
  "inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
export const BTN_OUTLINE =
  "inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed";

export const PLATFORM_OPTIONS: { value: Platform; label: string }[] = [
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
  { value: "tiktok", label: "TikTok" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "twitter", label: "X / Twitter" },
];

export const PLATFORM_LABEL: Record<string, string> = Object.fromEntries(
  PLATFORM_OPTIONS.map((p) => [p.value, p.label]),
);

export const FORMAT_OPTIONS = ["Reels", "Carrossel", "Feed", "Stories", "Vídeo", "Artigo", "Live"];

export const ITEM_STATUS_LABEL: Record<ItemStatus, string> = {
  planned: "Planejado",
  task_created: "Tarefa criada",
  in_progress: "Em produção",
  published: "Publicado",
  discarded: "Descartado",
};

export const ITEM_STATUS_COLOR: Record<ItemStatus, string> = {
  planned: "bg-muted text-muted-foreground",
  task_created: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  in_progress: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  published: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  discarded: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 line-through",
};

export function fmtDay(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        role="dialog"
        aria-label={title}
        className={`flex max-h-[90vh] w-full max-w-[calc(100vw-2rem)] flex-col rounded-lg border border-border bg-card p-6 shadow-lg ${
          wide ? "sm:max-w-2xl" : "sm:max-w-md"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted" aria-label="Fechar">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}
