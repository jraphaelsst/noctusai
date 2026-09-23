/** Cliente status labels + badge tones, shared by the list and the card. */
import type { BadgeVariant } from "@noctusai/lib/design-system";

import type { StatusCliente } from "@/hooks/useClientes";

export const STATUS_CLIENTE_LABEL: Record<StatusCliente, string> = {
  prospect: "Prospect",
  ativo: "Ativo",
  inativo: "Inativo",
  inadimplente: "Inadimplente",
};

/** Inadimplente is destructive because it gates the Módulo 4 approval
 *  portal — it must read as a problem. */
export const STATUS_CLIENTE_VARIANT: Record<StatusCliente, BadgeVariant> = {
  prospect: "muted",
  ativo: "default",
  inativo: "outline",
  inadimplente: "destructive",
};

export const STATUS_CLIENTE: StatusCliente[] = ["prospect", "ativo", "inativo", "inadimplente"];
