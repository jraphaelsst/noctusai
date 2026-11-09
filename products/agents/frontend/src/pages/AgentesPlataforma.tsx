/**
 * Agentes da plataforma — `/agentes-plataforma` (platform admin only, server-enforced by `require_platform_admin`).
 *
 * The platform's own internal AI calls: pick one, choose Fornecedor + Modelo, edit the ONE whole-prompt field, Salvar.
 * Draft discipline: `useUnsavedChanges` (badge + leave guard), `useConfirm` before dropping a draft, a failed save keeps
 * the text and says why (inline + `toastRetryableError`), `modelo_invalido` (422) lands inline under Modelo.
 */
import { useEffect, useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Bot } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState, Skeleton, Select, Textarea } from "@noctusai/lib/design-system";
import { QueryErrorState, UnsavedChangesNotice, toastRetryableError, useConfirm, useUnsavedChanges } from "@noctusai/lib/components";
import { ApiError } from "@noctusai/lib";
import {
  VENDORS,
  usePlataformaAgente,
  usePlataformaAgentes,
  usePlataformaModelos,
  useSalvarPlataformaAgente,
  type AgentePlataformaDetalhe,
  type EstatisticaModelo,
  type Vendor,
} from "@/hooks/usePlataformaAgentes";

interface Draft {
  vendor: Vendor;
  modelo: string;
  prompt: string;
}

const toDraft = (a: AgentePlataformaDetalhe): Draft => ({ vendor: a.vendor, modelo: a.modelo, prompt: a.prompt });

const vendorRotulo = (v: Vendor) => VENDORS.find((x) => x.valor === v)?.rotulo ?? v;

function fmtData(value: string | null): string {
  return value ? format(new Date(value), "dd/MM/yyyy HH:mm", { locale: ptBR }) : "";
}

function Estatisticas({ itens }: { itens: EstatisticaModelo[] }) {
  if (itens.length === 0) return <p className="text-xs text-muted-foreground" data-testid="plat-stats-vazio">Sem chamadas registradas ainda.</p>;
  return (
    <table className="w-full text-xs" data-testid="plat-stats">
      <caption className="mb-1 text-left font-medium text-foreground">Uso recente por fornecedor e modelo</caption>
      <thead className="text-left text-muted-foreground">
        <tr>
          <th scope="col" className="py-1 pr-2 font-normal">Fornecedor / modelo</th>
          <th scope="col" className="py-1 pr-2 font-normal">Chamadas</th>
          <th scope="col" className="py-1 pr-2 font-normal">Latência p50</th>
          <th scope="col" className="py-1 pr-2 font-normal">Custo médio</th>
          <th scope="col" className="py-1 font-normal">Erros</th>
        </tr>
      </thead>
      <tbody>
        {itens.map((e) => (
          <tr key={`${e.vendor}/${e.modelo}`} className="border-t border-border">
            <td className="py-1 pr-2">{vendorRotulo(e.vendor)} · {e.modelo}</td>
            <td className="py-1 pr-2">{e.n.toLocaleString("pt-BR")}</td>
            <td className="py-1 pr-2">{e.p50_latencia_ms == null ? "—" : `${Math.round(e.p50_latencia_ms).toLocaleString("pt-BR")} ms`}</td>
            <td className="py-1 pr-2">{e.custo_medio_usd == null ? "—" : `US$ ${e.custo_medio_usd.toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`}</td>
            <td className="py-1">{e.taxa_erro == null ? "—" : `${(e.taxa_erro * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Editor({ agente, onDirty }: { agente: AgentePlataformaDetalhe; onDirty: (d: boolean) => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(agente));
  const [erroModelo, setErroModelo] = useState<string | null>(null);
  const [aviso, setAviso] = useState("");
  const salvar = useSalvarPlataformaAgente();
  const modelos = usePlataformaModelos(draft.vendor, agente.capacidade);
  const saved = toDraft(agente);

  const opcoes = (modelos.data ?? []).filter((m) => m.vendor === draft.vendor);
  // The saved model must stay selectable while the catalogue loads / when it is not listed.
  const mostrar = opcoes.some((m) => m.modelo === draft.modelo) || !draft.modelo ? opcoes : [{ vendor: draft.vendor, modelo: draft.modelo, nome: draft.modelo }, ...opcoes];

  function trocarVendor(v: Vendor) {
    if (v === draft.vendor) return;
    // The model list is filtered by vendor; the previous model cannot be valid for the new vendor.
    // The first valid model is applied as soon as the catalogue answers (see `useEffect`-free derivation below).
    setDraft({ ...draft, vendor: v, modelo: "" });
    setErroModelo(null);
    setAviso(`Fornecedor alterado para ${vendorRotulo(v)}. Escolha o modelo.`);
  }

  // Derive, don't sync: a vendor change leaves modelo "" until the filtered list is here, then the first valid one is used.
  const modeloEfetivo = draft.modelo || opcoes[0]?.modelo || "";
  const efetivo: Draft = { ...draft, modelo: modeloEfetivo };
  const { dirty: mudou } = useUnsavedChanges(efetivo, saved);
  useEffect(() => {
    onDirty(mudou);
    return () => onDirty(false);
  }, [mudou, onDirty]);

  function salvarAgora() {
    setErroModelo(null);
    const patch: { prompt?: string; modelo?: string; vendor?: Vendor } = {};
    if (efetivo.prompt !== saved.prompt) patch.prompt = efetivo.prompt;
    if (efetivo.vendor !== saved.vendor) {
      patch.vendor = efetivo.vendor;
      patch.modelo = efetivo.modelo; // vendor + modelo ALWAYS travel together
    } else if (efetivo.modelo !== saved.modelo) {
      patch.modelo = efetivo.modelo;
    }
    salvar.mutate(
      { chave: agente.chave, patch },
      {
        onSuccess: (resp) => {
          setDraft(toDraft(resp));
          setAviso("Alterações salvas.");
          toast.success("Alterações salvas. Valem a partir da próxima chamada.");
        },
        onError: (err) => {
          if (err instanceof ApiError && (err.code === "modelo_invalido" || err.status === 422)) {
            setErroModelo("Este modelo não é válido para o fornecedor escolhido. Escolha outro da lista.");
            return;
          }
          toastRetryableError({ title: "Não foi possível salvar.", error: err, onRetry: salvarAgora });
        },
      },
    );
  }

  const falhou = salvar.isError && !erroModelo;

  return (
    <div className="space-y-4" data-testid="plat-editor">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-foreground">{agente.nome}</h2>
          {agente.descricao && <p className="text-xs text-muted-foreground">{agente.descricao}</p>}
          <p className="text-xs text-muted-foreground"><code>{agente.chave}</code></p>
        </div>
        {mudou && <Badge variant="outline" className="border-amber-500 font-semibold text-amber-600" data-testid="plat-nao-salvo">não salvo</Badge>}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="plat-vendor" className="mb-1 block text-xs font-medium">Fornecedor</label>
          <Select id="plat-vendor" value={draft.vendor} onChange={(e) => trocarVendor(e.target.value as Vendor)} data-testid="plat-vendor">
            {VENDORS.map((v) => (
              <option key={v.valor} value={v.valor}>{v.rotulo}</option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="plat-modelo" className="mb-1 block text-xs font-medium">Modelo</label>
          <Select
            id="plat-modelo"
            value={modeloEfetivo}
            aria-invalid={erroModelo ? true : undefined}
            aria-describedby={erroModelo ? "plat-modelo-erro" : "plat-modelo-dica"}
            onChange={(e) => {
              setDraft({ ...draft, modelo: e.target.value });
              setErroModelo(null);
            }}
            data-testid="plat-modelo"
          >
            {mostrar.map((m) => (
              <option key={m.modelo} value={m.modelo}>{m.nome || m.modelo}</option>
            ))}
          </Select>
          {erroModelo ? (
            <p id="plat-modelo-erro" role="alert" className="mt-1 text-xs text-destructive" data-testid="plat-modelo-erro">{erroModelo}</p>
          ) : (
            <p id="plat-modelo-dica" className="mt-1 text-xs text-muted-foreground">Só aparecem modelos do fornecedor escolhido.</p>
          )}
        </div>
      </div>

      <div>
        <label htmlFor="plat-prompt" className="mb-1 block text-xs font-medium">Prompt</label>
        <Textarea id="plat-prompt" monospace rows={16} spellCheck={false} value={draft.prompt} onChange={(e) => setDraft({ ...draft, prompt: e.target.value })} data-testid="plat-prompt" />
        <p className="mt-1 text-xs text-muted-foreground">{draft.prompt.length.toLocaleString("pt-BR")} caracteres · o texto inteiro é enviado ao fornecedor a cada chamada.</p>
      </div>

      <UnsavedChangesNotice dirty={mudou}>Você tem alterações não salvas. Elas só valem para as próximas chamadas depois de salvar.</UnsavedChangesNotice>
      {falhou && (
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive" data-testid="plat-salvar-erro">
          <strong className="block">Não foi possível salvar.</strong>
          Seu texto continua aqui. Tente salvar de novo; se continuar, avise o suporte.
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground" data-testid="plat-atualizado">
          {agente.atualizado_em
            ? `Atualizado em ${fmtData(agente.atualizado_em)}${agente.atualizado_por ? ` por ${agente.atualizado_por}` : ""}`
            : "Atualizado em — (padrão do código, nunca editado)"}
        </span>
        <span className="flex gap-2">
          <Button variant="outline" disabled={!mudou || salvar.isPending} onClick={() => { setDraft(toDraft(agente)); setErroModelo(null); salvar.reset(); }} data-testid="plat-descartar">
            Descartar alterações
          </Button>
          <Button disabled={!mudou || salvar.isPending || !modeloEfetivo} onClick={salvarAgora} data-testid="plat-salvar">
            {salvar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </span>
      </div>
      <p className="sr-only" role="status" aria-live="polite">{aviso}</p>
      <Estatisticas itens={agente.estatisticas ?? []} />
    </div>
  );
}

export default function AgentesPlataforma() {
  const lista = usePlataformaAgentes();
  const confirm = useConfirm();
  const [chave, setChave] = useState<string | null>(null);
  const [sujo, setSujo] = useState(false);
  const detalhe = usePlataformaAgente(chave);

  async function escolher(nova: string) {
    if (nova === chave) return;
    if (sujo) {
      const ok = await confirm({
        title: "Descartar alterações?",
        description: "Você tem alterações não salvas neste agente. Sair agora perde o que foi editado.",
        confirmLabel: "Descartar e sair",
        cancelLabel: "Continuar editando",
        tone: "danger",
      });
      if (!ok) return;
    }
    setSujo(false);
    setChave(nova);
  }

  return (
    <div className="space-y-4" data-testid="agentes-plataforma-page">
      <div className="flex items-center gap-3">
        <Bot className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agentes da plataforma</h1>
          <p className="text-sm text-muted-foreground">As chamadas de IA que a própria plataforma faz a fornecedores. Aqui você vê e ajusta o que cada uma recebe.</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[280px_1fr]">
        <section aria-label="Lista de agentes da plataforma" className="rounded-lg border border-border bg-card">
          {lista.showSkeleton ? (
            <div className="space-y-2 p-3" data-testid="plat-lista-skeleton"><Skeleton height={36} announce /><Skeleton height={36} /><Skeleton height={36} /></div>
          ) : lista.isError && !lista.data ? (
            <div className="p-3"><QueryErrorState query={lista} /></div>
          ) : (lista.data ?? []).length === 0 ? (
            <EmptyState message="Nenhum agente da plataforma ainda. Quando uma chamada de IA interna for registrada, ela aparece aqui." />
          ) : (
            <ul>
              {(lista.data ?? []).map((a) => (
                <li key={a.chave} className="border-b border-border last:border-b-0">
                  <button
                    type="button"
                    aria-current={a.chave === chave}
                    onClick={() => void escolher(a.chave)}
                    className="block w-full px-3 py-2 text-left hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:bg-accent"
                    data-testid={`plat-item-${a.chave}`}
                  >
                    <span className="block text-sm font-semibold text-foreground">
                      {a.nome}
                      {a.chave === chave && sujo && <Badge variant="outline" className="ml-2 border-amber-500 text-amber-600">não salvo</Badge>}
                    </span>
                    <span className="block text-xs text-muted-foreground">{vendorRotulo(a.vendor)} · {a.modelo}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Detalhe do agente" className="rounded-lg border border-border bg-card p-4">
          {!chave ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Selecione um agente para ver o prompt.</p>
          ) : detalhe.showSkeleton ? (
            <div className="space-y-3" data-testid="plat-detalhe-skeleton"><Skeleton height={20} announce /><Skeleton height={36} /><Skeleton height={240} /></div>
          ) : detalhe.isError && !detalhe.data ? (
            <QueryErrorState query={detalhe} />
          ) : detalhe.data ? (
            <Editor key={detalhe.data.chave} agente={detalhe.data} onDirty={setSujo} />
          ) : null}
        </section>
      </div>
    </div>
  );
}
