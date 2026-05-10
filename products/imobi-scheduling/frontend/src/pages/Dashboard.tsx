import { useAuthStore } from '@noctusai/seed/infra';
import { resolveSSOContext } from "@noctusai/lib";
import { CalendarClock, Users, CheckCircle2 } from "lucide-react";

export default function Dashboard() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <CalendarClock className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Welcome to Imobi Scheduling
          </p>
        </div>
      </div>

      {/* Status Card */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-success" />
          <h2 className="text-lg font-semibold text-foreground">Stack Status</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          If you can see this page, the entire NoctusAI shared stack is working:
          authentication, SSO context, layout (AppShell + Sidebar + Header),
          theme toggle, notifications, and activity-based token refresh.
        </p>
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          <StatusItem label="User" value={user?.email || "N/A"} />
          <StatusItem label="Organization" value={ssoCtx.org.name || "N/A"} />
          <StatusItem label="Org Role" value={ssoCtx.org.role || "N/A"} />
          <StatusItem label="SSO" value={ssoCtx.isSSO ? "Yes" : "No"} />
          <StatusItem label="Product Admin" value={ssoCtx.isProductAdmin ? "Yes" : "No"} />
          <StatusItem label="Plan" value={ssoCtx.plan?.slug || "N/A"} />
        </div>
      </div>

      {/* Info Card */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-3">
        <div className="flex items-center gap-3">
          <Users className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">Getting Started</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          This is the simplest possible NoctusAI product. Use it as a starting
          point for new products or as a test harness for shared infrastructure
          changes. The Equipe page lets you manage team members and invitations.
        </p>
      </div>
    </div>
  );
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/50 px-4 py-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold text-foreground truncate">{value}</p>
    </div>
  );
}
