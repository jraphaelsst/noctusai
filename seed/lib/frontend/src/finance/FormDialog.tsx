/** Modal frame used by every finance dialog: title, scrollable body, footer slot. */
import * as React from 'react';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';

export function FormDialog({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title} className={wide ? 'max-w-2xl' : undefined}>
      <DialogHeader>
        <h3 className="text-base font-semibold">{title}</h3>
      </DialogHeader>
      <DialogBody>{children}</DialogBody>
      {footer ? <DialogFooter className="gap-2">{footer}</DialogFooter> : null}
    </Dialog>
  );
}
