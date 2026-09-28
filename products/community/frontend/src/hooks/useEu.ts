/**
 * Identity hook — ninho-vazio CONTRACT.md §Identity, `GET /api/eu`.
 *
 * The one source the FE reads to decide which side of the app a signed-in
 * user belongs to: `papel === "membro"` → member portal only; `admin` /
 * `moderador` → the back office. Route guarding lives in
 * `components/RoleLayout.tsx`; `/assinar` also reads it to pre-fill the
 * checkout form for a logged-in member.
 *
 * Personal data scoped to the session — no `placeholderData` (there is no
 * user-controlled key to switch between; the key is fixed per session).
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type Papel = "admin" | "moderador" | "membro";
export type NivelGrupoterapia = "nenhum" | "ouvir" | "falar";

export interface EuMembro {
  id: string;
  status: string;
  plano_id: string | null;
  plano_nome: string | null;
  nivel_grupoterapia: NivelGrupoterapia;
}

export interface Eu {
  papel: Papel;
  nome: string;
  email: string;
  membro: EuMembro | null;
}

export const euKeys = {
  all: ["eu"] as const,
};

export function useEu(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: euKeys.all,
    queryFn: () => api.get<Eu>("/api/eu"),
    enabled: options.enabled ?? true,
    staleTime: 60_000,
  });
}

/** `membro` is the only role confined to the portal; every other papel is staff. */
export function isMembro(eu: Pick<Eu, "papel"> | null | undefined): boolean {
  return eu?.papel === "membro";
}
