/**
 * "Are you sure?" for a destructive action — igig's `SheetDialog` (a sheet
 * below 640px, R0) with a message and two buttons.
 *
 * The description must say WHAT is lost ("apaga também a marca, os
 * contratos…"), not only ask — a bare "tem certeza?" tells nobody anything.
 *
 * NOC-REMEDIATE[seed-confirm-dialog]: the seed ships `MotivoMoveDialog`
 * (reason-capturing) but no plain confirm; igig now has 5 call sites
 * (cliente, marca, automação, SMTP, Gmail) — lift to `@noctusai/lib`. — 2026-09-23
 */
import type { ReactNode } from "react";
import { Button } from "@noctusai/lib/design-system";

import { SheetDialog } from "./SheetDialog";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  testId?: string;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy,
  destructive = true,
  onConfirm,
  onCancel,
  testId,
}: ConfirmDialogProps) {
  return (
    <SheetDialog
      open={open}
      onClose={onCancel}
      title={title}
      widthClassName="sm:max-w-md"
      testId={testId}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="max-sm:h-10 max-sm:flex-1" onClick={onCancel} disabled={busy}>
            Cancelar
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            className="max-sm:h-10 max-sm:flex-1"
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </div>
      }
    >
      <div className="text-sm text-foreground">{description}</div>
    </SheetDialog>
  );
}
