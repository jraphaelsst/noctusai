/**
 * `<IntegrationCardModal/>` — detail modal for a single IntegrationAccount.
 *
 * Config-driven: uses `ProviderCardConfig.modalSections(account)` to derive
 * the displayed sections. The modal is a controlled component; open/close is
 * managed by the parent (the consuming page or IntegrationCard's onOpenModal).
 *
 * Built on the shared Dialog / DialogHeader / DialogBody / DialogFooter
 * primitives from `../ui/Dialog` — no Radix dependency, lib-only.
 * The organ MUST NOT import from any `products/` path.
 */
import * as React from "react";
import { X } from "lucide-react";

import { cn } from "../../utils";
import { Dialog, DialogHeader, DialogBody, DialogFooter } from "../ui/Dialog";
import { Button } from "../ui/Button";
import type { IntegrationAccount } from "./types";
import type { ProviderCardConfig } from "./providerCardConfig";
import { getProviderConfig } from "./providerCardConfig";
import { resolveStatusBadge } from "./IntegrationCard";

export interface IntegrationCardModalProps {
  /** When `null`, the modal is closed. */
  account: IntegrationAccount | null;
  /** Override the provider config (falls back to registry lookup). */
  config?: ProviderCardConfig;
  /** Called when the user closes the modal. */
  onClose: () => void;
  /** Optional extra className on the dialog panel. */
  className?: string;
}

export function IntegrationCardModal({
  account,
  config: configProp,
  onClose,
  className = "",
}: IntegrationCardModalProps) {
  if (!account) return null;

  const config: ProviderCardConfig | undefined =
    configProp ?? getProviderConfig(account.provider);

  const Icon = config?.icon;
  const primaryLabel = config ? config.primary(account) : account.account_label;
  const sections = config ? config.modalSections(account) : [];
  const { label: statusLabel, className: statusClass } = resolveStatusBadge(
    account.status,
  );

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Detalhes: ${primaryLabel}`}
      className={className}
    >
      {/* Header */}
      <DialogHeader>
        <div className="flex items-center gap-3">
          {Icon && (
            <span
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted",
                config?.accent,
              )}
              aria-hidden="true"
            >
              <Icon className="h-5 w-5" />
            </span>
          )}
          <div>
            <p className="text-sm font-semibold text-foreground">{primaryLabel}</p>
            {config && (
              <p className="text-xs text-muted-foreground">{config.displayName}</p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {/* Status badge */}
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
              statusClass,
            )}
          >
            {statusLabel}
          </span>

          {/* Close button */}
          <Button
            variant="ghost"
            size="icon"
            aria-label="Fechar"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </DialogHeader>

      {/* Body — sections */}
      <DialogBody className="space-y-5">
        {sections.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Sem detalhes adicionais para este provedor.
          </p>
        ) : (
          sections.map((section) => (
            <section key={section.title}>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {section.title}
              </h4>
              <dl className="space-y-1.5">
                {section.fields.map((field) => (
                  <div
                    key={field.label}
                    className="flex items-start justify-between gap-3 text-sm"
                  >
                    <dt className="text-muted-foreground">{field.label}</dt>
                    <dd className="text-right font-medium text-foreground break-all">
                      {field.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))
        )}
      </DialogBody>

      {/* Footer */}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

export default IntegrationCardModal;
