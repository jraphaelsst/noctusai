/**
 * Cobrança — grace period + billing automation (CONTRACT.md ninho-vazio
 * §Billing, `/api/cobranca/*`). Mounted by `Configuracoes.tsx` inside its
 * admin gate, next to the API keys panel.
 *
 * "Executar rotina agora" runs the same sweep the hourly scheduler runs and
 * shows its report verbatim — `pulado` means automations are off and the
 * sweep wrote nothing.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { Card, Checkbox, Field, FormError } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import {
  useCobrancaConfiguracoes,
  useExecutarRotinaCobranca,
  useSalvarCobrancaConfiguracoes,
  type RelatorioRotina,
} from "@/hooks/useCobranca";

const DIAS_MIN = 0;
const DIAS_MAX = 60;

export function CobrancaPanel() {
  const { data, isPending, isFetching, error } = useCobrancaConfiguracoes();
  const salvar = useSalvarCobrancaConfiguracoes();
  const executar = useExecutarRotinaCobranca();

  const [dias, setDias] = useState("");
  const [automacoes, setAutomacoes] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);
  const [relatorios, setRelatorios] = useState<RelatorioRotina[] | null>(null);

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  // Seed the form from the server once it arrives (and after a save).
  useEffect(() => {
    if (data && typeof data.dias_carencia === "number") {
      setDias(String(data.dias_carencia));
      setAutomacoes(!!data.automacoes_ativas);
    }
  }, [data]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const n = Number(dias);
    if (!Number.isInteger(n) || n < DIAS_MIN || n > DIAS_MAX) {
      setFormError(`Dias de carência deve ser um número inteiro entre ${DIAS_MIN} e ${DIAS_MAX}.`);
      return;
    }
    salvar.mutate(
      { dias_carencia: n, automacoes_ativas: automacoes },
      {
        onSuccess: () => toast.success("Configurações de cobrança salvas."),
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  async function handleExecutar() {
    setFormError(null);
    try {
      const res = await executar.mutateAsync();
      setRelatorios(res.relatorios ?? []);
      toast.success("Rotina de cobrança executada.");
    } catch (err) {
      setFormError(errorMessage(err));
    }
  }

  return (
    <Card className="space-y-4 p-6" data-testid="cobranca-panel">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Cobrança</h2>
        <p className="text-sm text-muted-foreground">
          Quando uma cobrança falha, a assinatura entra em carência e o acesso é mantido por estes dias. Depois disso
          ela expira e o membro volta para o plano gratuito.
          {/* lying-loading-ok: text-only suffix, the form stays mounted */}
          {isRefreshing ? " Atualizando…" : ""}
        </p>
      </div>

      {showSkeleton ? (
        <div className="space-y-2" data-testid="cobranca-skeleton">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-5 w-64" />
        </div>
      ) : error && !data ? (
        <p role="alert" className="text-sm text-destructive" data-testid="cobranca-erro">
          {errorMessage(error)}
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <FormError message={formError} />
          <Field label="Dias de carência" help={`Entre ${DIAS_MIN} e ${DIAS_MAX} dias.`}>
            <Input
              type="number"
              className="w-32"
              min={DIAS_MIN}
              max={DIAS_MAX}
              step={1}
              value={dias}
              onChange={(e) => setDias(e.target.value)}
              required
            />
          </Field>
          <Checkbox
            id="cobranca-automacoes"
            label="Automações ativas (expirar carências e encerrar cancelamentos automaticamente)"
            checked={automacoes}
            onChange={(e) => setAutomacoes(e.target.checked)}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" disabled={salvar.isPending}>
              {salvar.isPending ? "Salvando..." : "Salvar"}
            </Button>
            <Button type="button" variant="outline" onClick={() => void handleExecutar()} disabled={executar.isPending}>
              {executar.isPending ? "Executando..." : "Executar rotina agora"}
            </Button>
          </div>
        </form>
      )}

      {relatorios && <RelatorioRotinaView relatorios={relatorios} />}
    </Card>
  );
}

function RelatorioRotinaView({ relatorios }: { relatorios: RelatorioRotina[] }) {
  if (relatorios.length === 0) {
    return <p className="text-sm text-muted-foreground">A rotina não retornou nenhum relatório.</p>;
  }
  return (
    <div className="space-y-3 border-t border-border pt-4" data-testid="cobranca-relatorio">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Resultado da rotina</h3>
      {relatorios.map((r) => (
        <div key={r.nome} className="space-y-1 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-foreground">{r.nome}</span>
            {r.pulado ? (
              <Badge variant="muted">Pulada — automações desligadas</Badge>
            ) : (
              <Badge variant={r.erros.length ? "destructive" : "default"}>
                {r.examinadas} examinadas · {r.alteradas.length} alteradas · {r.erros.length} erros
              </Badge>
            )}
          </div>
          {r.alteradas.length > 0 && (
            <ul className="list-disc pl-5 text-muted-foreground">
              {r.alteradas.map((a, i) => (
                <li key={`a-${i}`}>{a}</li>
              ))}
            </ul>
          )}
          {r.erros.length > 0 && (
            <ul className="list-disc pl-5 text-destructive">
              {r.erros.map((e, i) => (
                <li key={`e-${i}`}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
