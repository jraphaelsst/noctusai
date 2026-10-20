/**
 * "Envio de leads qualificados" editor (julia-v2 Q6): per operation, the MINIMUM computed stage at which a lead is sent
 * to the CRM. The stages come from agents (ordered, label only — SW holds no copy of the standard). No criteria
 * builder, no `grupos`. Writes happen only on Salvar. Admin-only (server-enforced).
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { SideDrawer } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  estagioDe,
  mensagemErroEnvio,
  rotuloOperacao,
  separaOperacao,
  useQualificacaoEstagios,
  useSalvarEnvioRegras,
  type OperacaoRegra,
  type RegrasEnvio,
} from "@/hooks/useJuliaEnvio";

type Rascunho = Record<OperacaoRegra, string>;

function inicial(regras: RegrasEnvio | undefined): Rascunho {
  const ambas = estagioDe(regras, "ambas") ?? "";
  return {
    ambas,
    compra: estagioDe(regras, "compra") ?? ambas,
    aluguel: estagioDe(regras, "aluguel") ?? ambas,
  };
}

export function EnvioWizard({
  regras,
  isAdmin,
  onClose,
}: {
  regras: RegrasEnvio | undefined;
  isAdmin: boolean;
  onClose: () => void;
}) {
  const salvar = useSalvarEnvioRegras();
  const estagios = useQualificacaoEstagios();
  const [separar, setSeparar] = useState(separaOperacao(regras));
  const [draft, setDraft] = useState<Rascunho>(() => inicial(regras));
  const [dirty, setDirty] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const ro = !isAdmin || salvar.isPending;
  const lista = estagios.data ?? [];
  const showSkeleton = estagios.isPending && !estagios.data;
  const ops: OperacaoRegra[] = separar ? ["compra", "aluguel"] : ["ambas"];

  const escolher = (op: OperacaoRegra, v: string) => {
    setDraft((d) => ({ ...d, [op]: v }));
    setDirty(true);
    setErro(null);
  };
  const onSalvar = () => {
    if (!dirty) return setErro("Nenhuma alteração para salvar.");
    const faltando = ops.find((op) => !draft[op]);
    if (faltando) {
      return setErro(
        separar ? `${rotuloOperacao(faltando)}: escolha a etapa a partir da qual o lead é enviado.` : "Escolha a etapa a partir da qual o lead é enviado.",
      );
    }
    salvar.mutate(
      { diferenciar: separar, regras: ops.map((op) => ({ operacao: op, estagio_minimo: draft[op] })) },
      {
        onSuccess: () => { toast.success("Regra de envio salva"); onClose(); },
        onError: (e) => setErro(mensagemErroEnvio(e, "Não foi possível salvar a regra de envio.")),
      },
    );
  };

  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      width="xl"
      dirty={dirty}
      testId="envio-wizard"
      title="Envio de leads qualificados"
      footer={({ requestClose }) => (
        <>
          <Button variant="outline" onClick={requestClose}>Cancelar</Button>
          {isAdmin && (
            <Button onClick={onSalvar} disabled={ro || !!estagios.isError} data-testid="wizard-salvar">
              {salvar.isPending ? "Salvando…" : "Salvar"}
            </Button>
          )}
        </>
      )}
    >
      {!isAdmin && <p className="text-xs text-muted-foreground" data-testid="envio-readonly">Somente owner/admin pode alterar.</p>}
      <p className="text-sm text-muted-foreground">
        O lead é enviado ao SW quando a qualificação da Julia chega à etapa escolhida, ou a uma etapa posterior.
      </p>
      <div className="flex items-center gap-2">
        <input id="env-separar" type="checkbox" checked={separar} disabled={ro}
          onChange={(e) => {
            setSeparar(e.target.checked);
            setDirty(true);
            setErro(null);
            if (e.target.checked) setDraft((d) => ({ ...d, compra: d.compra || d.ambas, aluguel: d.aluguel || d.ambas }));
          }} />
        <Label htmlFor="env-separar">Configurações diferentes para compra e aluguel</Label>
      </div>

      {showSkeleton ? (
        <div className="h-20 animate-pulse rounded bg-muted" data-testid="estagios-skeleton" />
      ) : estagios.isError ? (
        <div className="space-y-2 rounded-md border border-destructive/40 p-3 text-sm" data-testid="estagios-erro">
          <p className="text-destructive">Não foi possível carregar as etapas de qualificação do app de agentes.</p>
          <Button variant="outline" size="sm" onClick={() => estagios.refetch()}>Tentar de novo</Button>
        </div>
      ) : lista.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="estagios-vazio">
          O app de agentes ainda não tem etapas de qualificação publicadas para a sua organização.
        </p>
      ) : (
        <div className="space-y-3">
          {ops.map((op) => {
            const atual = draft[op];
            const conhecida = !atual || lista.some((e) => e.chave === atual);
            return (
              <div key={op} className="space-y-1" data-testid={`regra-${op}`}>
                <Label htmlFor={`estagio-${op}`}>
                  {separar ? `Enviar ${rotuloOperacao(op).toLowerCase()} a partir da etapa` : "Enviar a partir da etapa"}
                </Label>
                <select
                  id={`estagio-${op}`}
                  aria-label={separar ? `Etapa mínima — ${rotuloOperacao(op)}` : "Etapa mínima"}
                  className="flex h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
                  disabled={ro}
                  value={atual}
                  onChange={(e) => escolher(op, e.target.value)}
                >
                  <option value="">Selecionar etapa</option>
                  {!conhecida && <option value={atual}>{atual} (etapa que não existe mais)</option>}
                  {lista.map((e) => (
                    <option key={e.chave} value={e.chave}>{e.ordem}. {e.rotulo}</option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      )}
      {estagios.isFetching && !!estagios.data && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
      {erro && <p role="alert" className="text-sm text-destructive" data-testid="wizard-erro">{erro}</p>}
    </SideDrawer>
  );
}
