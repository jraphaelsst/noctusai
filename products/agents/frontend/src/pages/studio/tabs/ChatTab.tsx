/**
 * Agent Studio — "Conversar" tab. CONTRACT §J2.4: FE-DEF ships this file as a
 * minimal compiling stub so the shell builds; slice FE-KE REPLACES it
 * wholesale (the orchestrator takes FE-KE's side for this path at merge).
 */
export default function ChatTab({ agentKey }: { agentKey: string }) {
  return (
    <div
      className="rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground"
      data-testid="studio-tab-em-breve"
      data-agent-key={agentKey}
    >
      Conversar: disponível em breve.
    </div>
  );
}
