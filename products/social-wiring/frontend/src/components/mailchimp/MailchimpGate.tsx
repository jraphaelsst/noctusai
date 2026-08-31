/**
 * MailchimpGate — wraps any Mailchimp page.
 *
 * Probes GET /api/mailchimp/connection (always 200).
 *   loading  → skeleton
 *   connected=false → <MailchimpNotConnected/>
 *   connected=true  → children
 *
 * Because the connection endpoint never returns an error status (by contract),
 * network errors are treated as a soft "not configured" fallback.
 */
import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useMailchimpConnection } from "@/hooks/useMailchimpConnection";
import { MailchimpNotConnected } from "./MailchimpNotConnected";

interface MailchimpGateProps {
  children: ReactNode;
}

export function MailchimpGate({ children }: MailchimpGateProps) {
  // `isPending` (not `isLoading`) — TanStack v5's `isLoading` is
  // `isPending && isFetching` and goes FALSE mid-refetch, which would let
  // the `!data?.connected` branch below win and unmount `children` on
  // every background refetch. Bare `isPending` is correct here: it stays
  // true only until data first resolves. → KB § PATTERNS/frontend/lying-loading-state.md
  const { data, isPending } = useMailchimpConnection();

  if (isPending) {
    return (
      <div className="space-y-4 p-6" data-testid="mailchimp-gate-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // connected=false (or network error — treat as not configured)
  if (!data?.connected) {
    return <MailchimpNotConnected />;
  }

  return <>{children}</>;
}
