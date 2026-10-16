/** Lais › Reengajamento (`/lais/reengajamento`, `?tab=reguas`) — contract §6 W4. */
import { useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { useIsFetching } from "@tanstack/react-query";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ReengajamentoPadraoTab } from "@/components/lais/reengajamento/ReengajamentoPadraoTab";
import { ReguasTab } from "@/components/lais/reengajamento/ReguasTab";
import { LAIS_LABEL, LAIS_PAGES } from "@/nav/lais";

export default function LaisReengajamento() {
  const isAdmin = useIsOrgAdmin();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "reguas" ? "reguas" : "padrao";
  const refreshing = useIsFetching({ queryKey: ["sw", "lais", "reengajamento"] }) > 0;

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {LAIS_LABEL} · {LAIS_PAGES.reengajamento.name}
          </h1>
          <p className="text-sm text-muted-foreground">
            A Julia retoma a conversa com leads que pararam de responder.
          </p>
        </div>
        {refreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="reeng-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </header>
      <Tabs value={tab} onValueChange={(v) => setParams(v === "reguas" ? { tab: "reguas" } : {}, { replace: true })}>
        <TabsList>
          <TabsTrigger value="padrao">Reengajamento padrão</TabsTrigger>
          <TabsTrigger value="reguas">
            Réguas de reengajamento <span className="ml-1 rounded bg-primary/10 px-1 text-[10px] text-primary">NOVO</span>
          </TabsTrigger>
        </TabsList>
        <TabsContent value="padrao">
          <ReengajamentoPadraoTab isAdmin={isAdmin} />
        </TabsContent>
        <TabsContent value="reguas">
          <ReguasTab isAdmin={isAdmin} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
