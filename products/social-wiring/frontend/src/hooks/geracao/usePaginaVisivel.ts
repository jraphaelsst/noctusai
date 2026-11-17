/**
 * usePaginaVisivel — is a `status_pagina` page key visible to the viewer? Same rule the sidebar applies
 * (`isPageVisible`: `desativado` hidden, `desenvolvimento` dev/owner only), read from the SAME query
 * (`usePageStatus`, key `['status-paginas']`) the layout already filled, so this is no extra request.
 * Until the statuses load (or when they fail) it returns true, like the layout's own ungated fallback:
 * the server enforces the real gate, this is UX only.
 */
import { isPageVisible, usePageStatus } from "@noctusai/lib";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";
import { supabase } from "@noctusai/seed/infra";

export function usePaginaVisivel(): (route: string) => boolean {
  const { data } = usePageStatus(supabase);
  const role = useEffectiveSSOContext().org.role;
  return (route) => (data?.length ? isPageVisible(route, data, role) : true);
}
