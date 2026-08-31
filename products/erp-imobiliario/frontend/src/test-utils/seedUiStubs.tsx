import React from 'react';

/**
 * Plain-DOM stand-ins for the Radix-backed `@noctusai/seed/components/ui/*`
 * primitives (Select / Dialog / AlertDialog / Tabs / Tooltip / ScrollArea).
 *
 * A product's `react-dom` lives in `products/<slug>/frontend/node_modules`
 * while these organs' `react` resolves from `seed/framework/frontend/
 * node_modules` — two physical React copies, so a Radix context provider's
 * hook call reads a null dispatcher ("Cannot read properties of null
 * (reading 'useMemo')"). Same root cause + same fix as documented in
 * `products/social-wiring/frontend/src/pages/WhatsAppChat.test.tsx` and
 * `components/vista/__tests__/ClientesTab.test.tsx` (which stubs `dialog`
 * alone for the same reason) — these page tests need the wider set because
 * they render filter `Select`s + create/edit `Dialog`s + delete
 * `AlertDialog`s in the same tree.
 *
 * Deliberately NOT interactive (no keyboard nav, no portal) — these tests
 * only need the summary-card VALUES to render without the tree crashing;
 * open/close state is honored so hidden dialog content never pollutes a
 * `screen.getByText` query in the visible tree.
 */

export const SelectModule = {
  Select: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'select-stub' }, children),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('div', null, children),
  SelectContent: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('div', null, children),
  SelectItem: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('div', null, children),
  SelectValue: ({ placeholder }: { placeholder?: string }) =>
    React.createElement('span', null, placeholder),
};

export const DialogModule = {
  Dialog: ({ open, children }: { open?: boolean; children?: React.ReactNode }) =>
    open ? React.createElement('div', { 'data-testid': 'dialog-stub' }, children) : null,
  DialogContent: ({ children, className }: { children?: React.ReactNode; className?: string }) =>
    React.createElement('div', { className }, children),
  DialogHeader: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  DialogFooter: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  DialogTitle: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  DialogDescription: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  DialogTrigger: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
};

export const AlertDialogModule = {
  AlertDialog: ({ open, children }: { open?: boolean; children?: React.ReactNode }) =>
    open ? React.createElement('div', { 'data-testid': 'alert-dialog-stub' }, children) : null,
  AlertDialogContent: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  AlertDialogHeader: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  AlertDialogFooter: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  AlertDialogTitle: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  AlertDialogDescription: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  AlertDialogAction: ({ children, onClick }: { children?: React.ReactNode; onClick?: () => void }) =>
    React.createElement('button', { onClick }, children),
  AlertDialogCancel: ({ children }: { children?: React.ReactNode }) => React.createElement('button', null, children),
  AlertDialogTrigger: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
};

export const TabsModule = {
  Tabs: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  TabsList: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  TabsTrigger: ({ children }: { children?: React.ReactNode }) => React.createElement('button', null, children),
  TabsContent: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
};

export const TooltipModule = {
  Tooltip: ({ children }: { children?: React.ReactNode }) => React.createElement(React.Fragment, null, children),
  TooltipTrigger: ({ children }: { children?: React.ReactNode }) => React.createElement(React.Fragment, null, children),
  TooltipContent: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
  TooltipProvider: ({ children }: { children?: React.ReactNode }) => React.createElement(React.Fragment, null, children),
};

export const ScrollAreaModule = {
  ScrollArea: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
};

export const ProgressModule = {
  Progress: ({ value, className }: { value?: number; className?: string }) =>
    React.createElement('div', { className, role: 'progressbar', 'aria-valuenow': value }),
};

export const SwitchModule = {
  Switch: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: (v: boolean) => void }) =>
    React.createElement('input', {
      type: 'checkbox',
      role: 'switch',
      checked: !!checked,
      onChange: () => onCheckedChange?.(!checked),
    }),
};
