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
  const { data, isLoading } = useMailchimpConnection();

  if (isLoading) {
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
