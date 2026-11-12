/**
 * "Controles" (Julia v2 CONTRACT §5.3): the agent's 3-state switch (ligado / drenando / desligado),
 * the open-conversation count and the drain progress. A change always goes through a confirmation
 * dialog that says what happens to the conversations already open. The state on screen is the last
 * server answer; the server decides every turn (this card is not a gate).
 */
import { useState } from "react";
import { env } from "@noctusai/lib";
import { toast } from "sonner";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, Switch } from "@noctusai/lib/design-system";
import type { Controle, ModoOperacao } from "@/api/studio/types-julia";
import { ContatosPermitidosSection } from "@/components/studio/ContatosPermitidosSection";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useControle, useControlePlataforma, useSetControle, useSetControlePlataforma } from "@/hooks/studio/useControle";
import { useIsPlatformAdmin } from "@/hooks/useIsPlatformAdmin";
import { useOrgMembers } from "@/hooks/studio/useOrgMembers";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

const MODOS: ReadonlyArray<{ valor: ModoOperacao; rotulo: string }> = [
  { valor: "ligado", rotulo: "Ligado" },
  { valor: "drenando", rotulo: "Drenando" },
  { valor: "desligado", rotulo: "Desligado" },
];

export function consequencia(modo: ModoOperacao, c: Controle, dias: number): string {
  const abertas = c.threads_abertas;
  if (modo === "ligado") {
    return "O agente passa a atender novos leads e as conversas abertas.";
  }
  if (modo === "drenando") {
    return (
      `O agente deixa de aceitar novos leads. As ${abertas} conversa(s) aberta(s) continuam sendo atendidas; ` +
      `uma conversa em que o lead não responde há ${dias} dia(s) ou mais é encerrada (e fica fora da contagem). ` +
      "Quando todas terminarem, a drenagem está concluída."
    );
  }
  return (
    `O agente para de responder imediatamente, inclusive nas ${abertas} conversa(s) aberta(s). ` +
    "As mensagens dos leads continuam sendo registradas, sem resposta automática."
  );
}

function Drenagem({ c }: { c: Controle }) {
  const d = c.drenagem;
  return (
    <div className="space-y-1 text-sm" data-testid="controle-drenagem">
      <p>
        <span className="font-semibold tabular-nums" data-testid="controle-abertas">{c.threads_abertas}</span> conversa(s) aberta(s)
        {d.ociosas > 0 && <> · <span className="tabular-nums">{d.ociosas}</span> ociosa(s) há {c.dreno_inatividade_dias}+ dias</>}
      </p>
      {c.modo === "drenando" && (
        <p className="text-xs text-muted-foreground" data-testid="controle-drenagem-progresso">
          {d.concluida ? "Drenagem concluída: nenhuma conversa ativa." : `${d.efetivas} ainda ativa(s); a mais antiga está parada há ${d.idade_max_dias} dia(s).`}
        </p>
      )}
      {d.idades_dias.length > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="controle-idades">
          Dias desde a última mensagem do lead: {d.idades_dias.slice(0, 12).join(", ")}
          {d.idades_dias.length > 12 ? "…" : ""}
        </p>
      )}
    </div>
  );
}

const MOTIVO_MAX = 500;

/**
 * Julia v3 §12.1: the platform-wide kill switch. The banner is shown to everyone while it is off
 * (a 403 for a non-admin just means "nothing to show"); the danger zone is platform-admin only.
 */
function ControlePlataformaSecao({ agentKey }: { agentKey: string }) {
  const admin = useIsPlatformAdmin();
  const q = useControlePlataforma(agentKey, true);
  const set = useSetControlePlataforma(agentKey);
  const [aberto, setAberto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const cp = q.data;

  if (q.showSkeleton) return admin ? <StudioLoading rows={1} testId="controle-plataforma-skeleton" /> : null;
  if (q.isError && !cp) {
    // Non-admins get 403 here by design: nothing to show. An admin must see the refusal.
    return admin ? <StudioError error={q.error} onRetry={q.refetch} /> : null;
  }
  if (!cp) return null;

  const desligado = cp.desligado;
  const motivoOk = motivo.trim().length > 0 && motivo.length <= MOTIVO_MAX;

  async function aplicar(alvo: boolean) {
    setErro(null);
    try {
      await set.mutateAsync({ desligado: alvo, motivo: alvo ? motivo.trim() : null });
      toast.success(alvo ? "Julia desligada em todas as empresas." : "Julia religada em todas as empresas.");
      setAberto(false);
      setMotivo("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <>
      {desligado && (
        <div role="alert" className="rounded-md border border-red-600 bg-red-600 p-3 text-sm font-semibold text-white" data-testid="plataforma-banner">
          Julia desligada na plataforma — nenhuma empresa recebe respostas.
          {cp.motivo && <span className="block text-xs font-normal">Motivo: {cp.motivo}</span>}
        </div>
      )}
      {admin && (
        <div className="space-y-2 rounded-md border border-red-300 p-3" data-testid="plataforma-zona-perigo">
          <h3 className="text-sm font-semibold text-red-700">Zona de perigo</h3>
          <div className="flex items-center gap-2 text-sm">
            <Switch
              checked={desligado}
              disabled={set.isPending}
              aria-label="Desligar a Julia em TODAS as empresas"
              data-testid="plataforma-switch"
              onCheckedChange={(v) => {
                setErro(null);
                if (v) setAberto(true);
                else void aplicar(false);
              }}
            />
            Desligar a Julia em TODAS as empresas
          </div>
          {erro && !aberto && <p className="text-sm text-destructive" role="alert" data-testid="plataforma-erro">{erro}</p>}
          <Dialog open={aberto} onClose={() => setAberto(false)} title="Desligar a Julia em todas as empresas" className="max-w-lg">
            <DialogHeader><h2 className="text-base font-semibold">Desligar a Julia em TODAS as empresas?</h2></DialogHeader>
            <DialogBody className="space-y-3">
              <p className="text-sm">Nenhuma empresa receberá respostas da Julia até você religar. Informe o motivo.</p>
              <div>
                <label htmlFor="plataforma-motivo" className="mb-1 block text-xs font-medium">Motivo (obrigatório)</label>
                <textarea
                  id="plataforma-motivo"
                  rows={3}
                  maxLength={MOTIVO_MAX}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                />
              </div>
              {erro && <p className="text-sm text-destructive" role="alert" data-testid="plataforma-erro-dialog">{erro}</p>}
            </DialogBody>
            <DialogFooter className="gap-2">
              <Button variant="ghost" onClick={() => setAberto(false)}>Cancelar</Button>
              <Button variant="primary" disabled={!motivoOk || set.isPending} onClick={() => aplicar(true)} data-testid="plataforma-confirmar">
                {set.isPending ? "Desligando..." : "Desligar em todas as empresas"}
              </Button>
            </DialogFooter>
          </Dialog>
        </div>
      )}
    </>
  );
}

export function ControlesCard({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const q = useControle(agentKey);
  const set = useSetControle(agentKey);
  const [alvo, setAlvo] = useState<ModoOperacao | null>(null);
  const [dias, setDias] = useState<string>("");
  const [erro, setErro] = useState<string | null>(null);
  const [novoMembro, setNovoMembro] = useState("");
  const membros = useOrgMembers(isAdmin);

  if (q.showSkeleton) return <StudioLoading rows={2} testId="controles-skeleton" />;
  if (q.isError) return <StudioError error={q.error} onRetry={q.refetch} />;
  const c = q.data;
  if (!c) return null;
  const diasAtuais = c.dreno_inatividade_dias;
  const diasNum = dias.trim() === "" ? diasAtuais : Number(dias);
  const diasValidos = Number.isInteger(diasNum) && diasNum >= 1 && diasNum <= 365;

  async function confirmar() {
    if (!alvo) return;
    setErro(null);
    try {
      await set.mutateAsync({ modo: alvo, ...(alvo === "drenando" || dias.trim() ? { dreno_inatividade_dias: diasNum } : {}) });
      toast.success(`Agente ${MODOS.find((m) => m.valor === alvo)?.rotulo.toLowerCase()}.`);
      setAlvo(null);
      setDias("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  const usuarios = c.avaliacao_usuarios ?? [];
  const resolvidos = c.avaliacao_resolvidos ?? [];
  const resolvidoPor = new Map(resolvidos.map((r) => [r.usuario_id, r]));
  const comTelefone = resolvidos.filter((r) => usuarios.includes(r.usuario_id) && !!r.telefone);
  const emAvaliacao = !!c.modo_avaliacao;
  const nomeDe = (id: string) => resolvidoPor.get(id)?.nome ?? membros.data?.find((m) => m.id === id)?.nome ?? id;
  const disponiveis = (membros.data ?? []).filter((m) => !usuarios.includes(m.id));

  async function salvarAvaliacao(patch: { modo_avaliacao?: boolean; avaliacao_usuarios?: string[] }, ok: string) {
    setErro(null);
    try {
      await set.mutateAsync({ modo: c!.modo, ...patch });
      toast.success(ok);
      return true;
    } catch (err) {
      setErro(errorMessage(err));
      return false;
    }
  }

  async function adicionarMembro() {
    if (!novoMembro || usuarios.includes(novoMembro)) return;
    if (await salvarAvaliacao({ avaliacao_usuarios: [...usuarios, novoMembro] }, "Membro adicionado.")) setNovoMembro("");
  }

  async function salvarDias() {
    setErro(null);
    try {
      await set.mutateAsync({ modo: c!.modo, dreno_inatividade_dias: diasNum });
      toast.success("Prazo de inatividade salvo.");
      setDias("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4" data-testid="controles-card">
      <ControlePlataformaSecao agentKey={agentKey} />
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Controles</h2>
        <Badge variant={c.modo === "ligado" ? "default" : c.modo === "drenando" ? "outline" : "muted"} data-testid="controle-modo">
          {MODOS.find((m) => m.valor === c.modo)?.rotulo}
        </Badge>
        {emAvaliacao && (
          <span className="rounded-md border border-amber-500 bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900" data-testid="controle-avaliacao-badge">
            {c.avaliacao_herdada ? "Julia em modo de avaliação" : `Em avaliação — responde só a ${comTelefone.length} número(s)`}
          </span>
        )}
        <span className="text-xs text-muted-foreground">{c.aceita_novos_leads ? "Aceita novos leads" : "Não aceita novos leads"}</span>
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>

      <div className="inline-flex rounded-md border border-input p-0.5" role="radiogroup" aria-label="Modo de operação">
        {MODOS.map((m) => (
          <button
            key={m.valor}
            type="button"
            role="radio"
            aria-checked={c.modo === m.valor}
            disabled={!isAdmin || set.isPending}
            data-testid={`controle-modo-${m.valor}`}
            onClick={() => {
              if (m.valor === c.modo) return;
              setErro(null);
              setAlvo(m.valor);
            }}
            className={cn(
              "rounded px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60",
              c.modo === m.valor ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {m.rotulo}
          </button>
        ))}
      </div>
      {!isAdmin && <p className="text-xs text-muted-foreground">Somente administradores da organização alteram o modo.</p>}

      <Drenagem c={c} />

      {c.avaliacao_herdada ? (
        <div className="space-y-1" data-testid="controle-avaliacao-herdada">
          <p className="text-sm font-medium">{emAvaliacao ? "Julia em modo de avaliação" : "Julia fora do modo de avaliação"}</p>
          <p className="text-xs text-muted-foreground">
            O modo de avaliação é um só, definido no núcleo da Julia pela NoctusAI, e vale para todas as empresas. Não é configurada por instância.
          </p>
        </div>
      ) : (
        <div className="space-y-2" data-testid="controle-avaliacao">
          <div className="flex items-center gap-2 text-sm">
            <Switch
              checked={emAvaliacao}
              disabled={!isAdmin || set.isPending || (!emAvaliacao && comTelefone.length === 0)}
              aria-label="Modo de avaliação"
              data-testid="controle-avaliacao-switch"
              onCheckedChange={(v) => void salvarAvaliacao({ modo_avaliacao: v, avaliacao_usuarios: usuarios }, v ? "Modo de avaliação ligado." : "Modo de avaliação desligado.")}
            />
            Modo de avaliação
          </div>
          <p className="text-xs text-muted-foreground">Com a Julia ligada, ela responde SÓ aos números abaixo. Os demais contatos não recebem resposta. Desligue quando o fluxo estiver validado.</p>
          {!emAvaliacao && comTelefone.length === 0 && (
            <p className="text-xs text-amber-700" data-testid="controle-avaliacao-dica">Escolha ao menos um membro com WhatsApp cadastrado no noc para ligar o modo de avaliação.</p>
          )}
          <ul className="space-y-1" data-testid="controle-avaliacao-lista">
            {usuarios.map((id) => {
              const r = resolvidoPor.get(id);
              return (
                <li key={id} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`controle-avaliacao-membro-${id}`}>
                  <span>{nomeDe(id)}</span>
                  {r?.telefone && <span className="tabular-nums text-muted-foreground">{r.telefone}</span>}
                  {r && !r.telefone && (
                    <a
                      href={`${env.CORE_URL}/settings`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-md border border-amber-500 bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900"
                      data-testid={`controle-avaliacao-sem-whatsapp-${id}`}
                    >
                      Sem WhatsApp — cadastre no noc
                    </a>
                  )}
                  {isAdmin && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={set.isPending || (emAvaliacao && comTelefone.length === 1 && !!r?.telefone)}
                      title={emAvaliacao && comTelefone.length === 1 && !!r?.telefone ? "Desligue o modo de avaliação para remover o último número." : undefined}
                      aria-label={`Remover ${nomeDe(id)}`}
                      onClick={() => void salvarAvaliacao({ avaliacao_usuarios: usuarios.filter((x) => x !== id) }, "Membro removido.")}
                    >
                      Remover
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
          {isAdmin && (
            membros.showSkeleton ? (
              <StudioLoading rows={1} testId="controle-avaliacao-membros-skeleton" />
            ) : membros.isError && !membros.data ? (
              <StudioError error={membros.error} onRetry={membros.refetch} />
            ) : (
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label htmlFor="controle-avaliacao-membro" className="mb-1 block text-xs font-medium">Membro permitido</label>
                  <select
                    id="controle-avaliacao-membro"
                    className="h-9 w-64 rounded-md border border-input bg-background px-3 text-sm"
                    value={novoMembro}
                    onChange={(e) => setNovoMembro(e.target.value)}
                  >
                    <option value="">{disponiveis.length ? "Escolha um membro…" : "Todos os membros já foram escolhidos"}</option>
                    {disponiveis.map((m) => <option key={m.id} value={m.id}>{m.nome || m.email}</option>)}
                  </select>
                </div>
                <Button size="sm" variant="outline" disabled={!novoMembro || set.isPending} onClick={adicionarMembro} data-testid="controle-avaliacao-adicionar">
                  Adicionar
                </Button>
              </div>
            )
          )}
        </div>
      )}

      <ContatosPermitidosSection agentKey={agentKey} c={c} isAdmin={isAdmin} />

      {isAdmin && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="controle-dias" className="mb-1 block text-xs font-medium">Encerrar conversa parada após (dias)</label>
            <input
              id="controle-dias"
              type="number"
              min={1}
              max={365}
              className="h-9 w-28 rounded-md border border-input bg-background px-3 text-sm"
              value={dias === "" ? String(diasAtuais) : dias}
              onChange={(e) => setDias(e.target.value)}
            />
          </div>
          <Button size="sm" variant="outline" disabled={dias === "" || !diasValidos || set.isPending} onClick={salvarDias} data-testid="controle-dias-salvar">
            Salvar prazo
          </Button>
        </div>
      )}
      {erro && !alvo && (
        <p className="text-sm text-destructive" role="alert" data-testid="controle-erro">{erro}</p>
      )}

      <Dialog open={alvo !== null} onClose={() => setAlvo(null)} title="Alterar o modo do agente" className="max-w-lg">
        <DialogHeader>
          <h2 className="text-base font-semibold">
            Mudar para “{MODOS.find((m) => m.valor === alvo)?.rotulo}”?
          </h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {alvo && (
            <p className="text-sm" data-testid="controle-consequencia">
              {consequencia(alvo, c, diasNum)}
            </p>
          )}
          {alvo === "drenando" && (
            <div>
              <label htmlFor="controle-dias-dialog" className="mb-1 block text-xs font-medium">Dias de inatividade para encerrar</label>
              <input
                id="controle-dias-dialog"
                type="number"
                min={1}
                max={365}
                className="h-9 w-28 rounded-md border border-input bg-background px-3 text-sm"
                value={dias === "" ? String(diasAtuais) : dias}
                onChange={(e) => setDias(e.target.value)}
              />
            </div>
          )}
          {erro && (
            <p className="text-sm text-destructive" role="alert" data-testid="controle-erro-dialog">{erro}</p>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => setAlvo(null)}>Cancelar</Button>
          <Button variant="primary" disabled={set.isPending || (alvo === "drenando" && !diasValidos)} onClick={confirmar} data-testid="controle-confirmar">
            {set.isPending ? "Aplicando..." : "Confirmar"}
          </Button>
        </DialogFooter>
      </Dialog>
    </section>
  );
}
