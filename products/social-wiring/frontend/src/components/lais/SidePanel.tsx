/**
 * Right-side panel (local pattern). Non-modal on purpose: the seed
 * ConfirmProvider dialog portals outside, and a modal parent would make it
 * inert. Kept in ONE file so it can be swapped for the seed SideDrawer organ.
 */
import type { ReactNode } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";

export function SidePanel({
  title,
  onClose,
  children,
  footer,
  testId,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  testId?: string;
  wide?: boolean;
}) {
  return (
    <aside
      role="dialog"
      aria-label={title}
      data-testid={testId}
      className={`fixed inset-y-0 right-0 z-50 flex w-full ${wide ? "max-w-2xl" : "max-w-md"} flex-col border-l bg-background shadow-xl`}
    >
      <header className="flex items-start justify-between gap-2 border-b p-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <Button variant="ghost" size="icon" aria-label="Fechar" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">{children}</div>
      {footer && <footer className="flex justify-end gap-2 border-t p-4">{footer}</footer>}
    </aside>
  );
}
