/** Agent Studio — "Controles" (Julia v2 CONTRACT §5.3): the agent's operating mode and drain progress. */
import { ControlesCard } from "@/components/studio/ControlesCard";

export default function ControlesTab({ agentKey }: { agentKey: string }) {
  return (
    <div className="space-y-4" data-testid="controles-tab">
      <ControlesCard agentKey={agentKey} />
    </div>
  );
}
