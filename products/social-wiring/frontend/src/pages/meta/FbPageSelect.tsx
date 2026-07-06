/**
 * FbPageSelect — shared Facebook Page picker for the 3 FB subtabs
 * (Visão geral / Conteúdo / Comentários). Extracted at N=3 (DRY rule) rather
 * than repeating the `useMetaContext` + page-Select wiring in each subtab.
 *
 * Owns nothing beyond selection — the caller still fetches page-scoped data
 * (insights/posts/comments) keyed by the returned `pageId`.
 */
import { useEffect } from "react";
import { CircleAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useMetaContext, type FacebookPage } from "@/hooks/useMeta";

export function useFbPages(accountId: string | null) {
  return useMetaContext(accountId);
}

interface FbPageSelectProps {
  accountId: string;
  pages: FacebookPage[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function FbPageSelect({ pages, selectedId, onSelect }: FbPageSelectProps) {
  useEffect(() => {
    if (!selectedId && pages.length > 0) {
      onSelect(pages[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages, selectedId]);

  if (pages.length <= 1) return null;

  return (
    <Select value={selectedId ?? undefined} onValueChange={onSelect}>
      <SelectTrigger className="w-full max-w-xs" data-testid="fb-page-select">
        <SelectValue placeholder="Selecione uma página" />
      </SelectTrigger>
      <SelectContent>
        {pages.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Common "no page on this connection" empty state. */
export function FbNoPages() {
  return (
    <div
      className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
      data-testid="fb-no-pages"
    >
      Nenhuma página do Facebook encontrada para esta conexão do Meta.
    </div>
  );
}

export function FbContextError() {
  return (
    <div
      className="flex items-center gap-2 rounded-md border border-dashed p-4 text-sm text-destructive"
      data-testid="fb-context-error"
    >
      <CircleAlert className="h-4 w-4 shrink-0" />
      Erro ao carregar páginas do Facebook.
    </div>
  );
}

export function FbContextLoading() {
  return <Skeleton className="h-10 w-64" data-testid="fb-context-loading" />;
}
