/**
 * `itemLabel(id)` for organs that only know item ids (inventory, purchasing): returns `SKU · name` once the item
 * has been fetched and a short id until then. The ids are the ones the organs ASK FOR while rendering, so only the
 * VISIBLE items are fetched (`GET /api/items/{id}`, one cached query per id, shared with the items organ's detail
 * key).
 */
import * as React from "react";
import { useQueries } from "@tanstack/react-query";
import { itemsKeys, type Item } from "@noctusai/lib";

import { api } from "@/lib/api";

export function useItemLabels(): (itemId: string) => string {
  const wanted = React.useRef<Set<string>>(new Set());
  const [ids, setIds] = React.useState<string[]>([]);

  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: itemsKeys.item(id),
      queryFn: async () => (await api.get<{ data: Item }>(`/api/items/${id}`)).data,
      staleTime: 5 * 60_000,
    })),
  });

  // A stable scalar signature of what has loaded (a variable-length dependency array is not allowed).
  const loaded = results.map((r) => r.data?.id ?? "").join(",");
  const names = React.useMemo(() => {
    const map = new Map<string, string>();
    ids.forEach((id, i) => {
      const it = results[i]?.data;
      if (it) map.set(id, `${it.sku} · ${it.name}`);
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `results` is a fresh array each render; `loaded` drives this
  }, [ids, loaded]);

  return React.useCallback(
    (itemId: string) => {
      if (!wanted.current.has(itemId)) {
        wanted.current.add(itemId);
        // Called while a CHILD organ renders (the host does not re-render), and setState during render is not
        // allowed: commit the new id to state from a microtask, which re-renders the host and starts the fetch.
        queueMicrotask(() => setIds([...wanted.current]));
      }
      return names.get(itemId) ?? itemId.slice(0, 8);
    },
    [names],
  );
}
