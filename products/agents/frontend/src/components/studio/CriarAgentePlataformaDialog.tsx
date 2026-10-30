/**
 * "Criar agente" (platform admin): registers an agent by key. Two modes behind ONE submit
 * (`POST /api/studio/plataforma/agents`): `vazio` (an empty shell that grows over time) and `gerar`
 * ("Gerar com IA": a briefing makes the server write a first DRAFT — a starting point to review, never
 * published). Any valid key is accepted; a NEW key needs a name. Key suggestions come from the agents
 * list (the API), never a literal.
 */
import React, { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import { useCreatePlatformAgent } from "@/hooks/studio/useAgentLifecycle";
import { useStudioAgents } from "@/hooks/studio/useStudioAgents";
import { LIMITE_USD_MAX } from "@/api/studio/types-geracao";
import { lifecycleError } from "@/lib/agentLifecycle";
import { BRIEFING_VAZIO, KEY_RE, slugify, validarBriefing, type BriefingDraft, type BriefingErrors } from "@/lib/briefing";
import { BriefingForm } from "./BriefingForm";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm font-mono text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

export type ModoCriacao = "vazio" | "gerar";
export const MODOS_CRIACAO: { id: ModoCriacao; label: string }[] = [
  { id: "vazio", label: "Vazio" },
  { id: "gerar", label: "Gerar com IA" },
];

interface CamposProps {
  draft: BriefingDraft;
  onChange: (d: BriefingDraft) => void;
  errors: BriefingErrors;
  onNomeChange: (nome: string) => void;
}
/** Mode-specific fields. `vazio` has none; `gerar` renders the Briefing. */
const CAMPOS_POR_MODO: Record<ModoCriacao, ((p: CamposProps) => React.ReactElement) | null> = {
  vazio: null,
  gerar: ({ draft, onChange, errors, onNomeChange }) => (
    <>
      <BriefingForm value={draft} onChange={onChange} errors={errors} idPrefix="criar-briefing" onNomeChange={onNomeChange} />
      <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground" data-testid="criar-agente-aviso-ia">
        A IA escreve um primeiro rascunho (custo máximo de US$ {LIMITE_USD_MAX.toFixed(2)} por geração). O resultado é um ponto
        de partida: revise e edite antes de publicar — nada é publicado automaticamente.
      </p>
    </>
  ),
};

export function CriarAgentePlataformaDialog({ onClose }: { onClose: () => void }) {
  const create = useCreatePlatformAgent();
  const navigate = useNavigate();
  const { data: agentes } = useStudioAgents();
  const [key, setKey] = useState("");
  const [keyTocada, setKeyTocada] = useState(false);
  const [modo, setModo] = useState<ModoCriacao>("vazio");
  const [nome, setNome] = useState("");
  const [draft, setDraft] = useState<BriefingDraft>(BRIEFING_VAZIO);
  const [errors, setErrors] = useState<BriefingErrors>({});
  const [instanciavel, setInstanciavel] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const existente = useMemo(() => (agentes ?? []).some((a) => a.key === key.trim()), [agentes, key]);
  const nomeEfetivo = (modo === "gerar" ? draft.nome : nome).trim();

  function mudarNome(v: string) {
    setNome(v);
    setDraft((d) => ({ ...d, nome: v }));
    if (!keyTocada) setKey(slugify(v));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    const k = key.trim();
    if (!KEY_RE.test(k)) {
      setErro("A chave usa letras minúsculas, números e hífens (2 a 63 caracteres, começando por letra ou número).");
      return;
    }
    let briefing;
    if (modo === "gerar") {
      const v = validarBriefing(draft);
      setErrors(v.errors);
      if (!v.briefing) return;
      briefing = v.briefing;
    } else if (!existente && !nomeEfetivo) {
      setErro("Informe o nome do agente.");
      return;
    }
    try {
      const created = await create.mutateAsync({
        key: k,
        ...(nomeEfetivo ? { nome: nomeEfetivo } : {}),
        ...(briefing ? { briefing } : {}),
        ...(instanciavel ? { instanciavel: true } : {}),
      });
      toast.success(
        created.geracao
          ? "Agente criado. A IA está gerando o primeiro rascunho — revise antes de publicar."
          : "Agente criado. Ele começa vazio e cresce com o tempo.",
      );
      onClose();
      navigate(`/agentes/${encodeURIComponent(created.key)}`);
    } catch (err) {
      setErro(lifecycleError(err).message);
    }
  }

  const Campos = CAMPOS_POR_MODO[modo];
  const pronto = !!key.trim() && (modo === "gerar" || existente || !!nomeEfetivo);

  return (
    <Dialog open onClose={onClose} title="Criar agente" className="max-w-lg">
      <form onSubmit={submit}>
        <DialogHeader>
          <h2 className="text-base font-semibold text-foreground">Criar agente da plataforma</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div role="radiogroup" aria-label="Modo de criação" className="flex gap-3 text-sm">
            {MODOS_CRIACAO.map((m) => (
              <label key={m.id} className="flex items-center gap-1">
                <input type="radio" name="criar-modo" checked={modo === m.id} onChange={() => setModo(m.id)} data-testid={`criar-modo-${m.id}`} /> {m.label}
              </label>
            ))}
          </div>
          {modo === "vazio" && (
            <div>
              <label htmlFor="criar-agente-nome" className="mb-1 block text-sm font-medium">
                Nome do agente {existente ? "" : "*"}
              </label>
              <input
                id="criar-agente-nome"
                className={INPUT_CLASS.replace("font-mono", "")}
                value={nome}
                maxLength={80}
                onChange={(e) => mudarNome(e.target.value)}
                data-testid="criar-agente-nome"
              />
            </div>
          )}
          {Campos && <Campos draft={draft} onChange={setDraft} errors={errors} onNomeChange={mudarNome} />}
          <div>
            <label htmlFor="criar-agente-key" className="mb-1 block text-sm font-medium">
              Chave do agente *
            </label>
            <input
              id="criar-agente-key"
              className={INPUT_CLASS}
              value={key}
              list="criar-agente-chaves"
              required
              onChange={(e) => {
                setKeyTocada(true);
                setKey(e.target.value.toLowerCase());
              }}
              data-testid="criar-agente-key"
            />
            <datalist id="criar-agente-chaves">
              {(agentes ?? []).map((a) => (
                <option key={a.key} value={a.key} />
              ))}
            </datalist>
            <p className="mt-1 text-xs text-muted-foreground">
              {modo === "vazio"
                ? "O agente nasce vazio — nenhum conteúdo é exigido para criar. Só a publicação exige os textos completos."
                : "Sugerida a partir do nome; você pode editar."}
            </p>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={instanciavel}
              onChange={(e) => setInstanciavel(e.target.checked)}
              data-testid="criar-agente-instanciavel"
            />
            <span>
              Disponível para as organizações
              <span className="block text-xs text-muted-foreground">
                Depois de publicado, o agente é instanciado em todas as organizações.
              </span>
            </span>
          </label>
          {erro && (
            <p className="text-sm text-destructive" data-testid="criar-agente-erro">
              {erro}
            </p>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={!pronto || create.isPending} data-testid="criar-agente-submit">
            {create.isPending ? "Criando..." : modo === "gerar" ? "Criar e gerar" : "Criar agente"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
