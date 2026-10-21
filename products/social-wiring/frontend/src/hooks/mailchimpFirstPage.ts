/**
 * `predicate` for the Mailchimp list caches (`["mailchimp", <resource>, params?]`, params = `{ count?, offset? }`):
 * true only for a FIRST-page list entry. A created row is committed into those and nowhere else — a page at
 * `offset > 0`, a detail (`[…, id]`) or a sub-resource (`[…, id, "members", …]`) must not receive it.
 */
import type { QueryKey } from "@tanstack/react-query";

export const isFirstMailchimpPage = (queryKey: QueryKey): boolean => {
  if (queryKey.length !== 3) return false;
  const params = queryKey[2];
  if (params === undefined) return true;
  return !!params && typeof params === "object" && !(params as { offset?: number | null }).offset;
};
