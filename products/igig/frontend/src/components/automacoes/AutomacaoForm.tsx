/**
 * Create / edit one automação (wave-2 contract, Slice E2; roadmap R11):
 * quadro (pipeline) → etapa (from THAT board's stages endpoint) → gatilho
 * (entrada na etapa | SLA em horas) → ação (tipo + its params) → ativa.
 *
 * `pipeline` is fixed once created (the PATCH does not accept it — a rule
 * moved to the other board would point at a stage of the wrong board).
 * Text fields accept `{nome}`, `{empresa}`, `{titulo}`, `{etapa}`, `{cliente}`.
 */
import { useEffect, useState } from "react";
import { Button, Field, FormError, Input, Select, Switch, Textarea } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import {
  GATILHO_LABEL,
  TIPOS_POR_PIPELINE,
  TIPO_ACAO_LABEL,
  useAutomacaoMutations,
  type Automacao,
  type Gatilho,
  type PipelineAutomacao,
  type TipoAcao,
} from "@/hooks/useAutomacoes";
import { useMembrosEquipe, useProfissionais } from "@/hooks/useCustos";
import { esteiraPipeline } from "@/hooks/useEsteira";
import { describeError } from "@/lib/errors";
import { comercialPipeline } from "@/lib/pipelines";
import { DRAFT_VAZIO, draftDe, montarAcao, problemaDoDraft, type AcaoDraft } from "./acaoParams";

export const PIPELINE_LABEL: Record<PipelineAutomacao, string> = {
  comercial: "Comercial (funil)",
  esteira: "Esteira de produção",
};

export interface AutomacaoFormProps {
  open: boolean;
  /** null ⇒ create. */
  automacao: Automacao | null;
  onClose: () => void;
}

export function AutomacaoForm({ open, automacao, onClose }: AutomacaoFormProps) {
  const editando = !!automacao;
  const { criar, atualizar } = useAutomacaoMutations();
  const [pipeline, setPipeline] = useState<PipelineAutomacao>("comercial");
  const [stageId, setStageId] = useState("");
  const [gatilho, setGatilho] = useState<Gatilho>("entrada_etapa");
  const [slaHoras, setSlaHoras] = useState("24");
  const [tipo, setTipo] = useState<TipoAcao>("notificar");
  const [draft, setDraft] = useState<AcaoDraft>({ ...DRAFT_VAZIO });
  const [ativo, setAtivo] = useState(true);

  // Re-seed on every open (create ⇒ blank; edit ⇒ the rule).
  useEffect(() => {
    if (!open) return;
    setPipeline(automacao?.pipeline ?? "comercial");
    setStageId(automacao?.stage_id ?? "");
    setGatilho(automacao?.gatilho ?? "entrada_etapa");
    setSlaHoras(String(automacao?.sla_horas ?? 24));
    setTipo(automacao?.acao.tipo ?? "notificar");
    setDraft(draftDe(automacao?.acao));
    setAtivo(automacao?.ativo ?? true);
    criar.reset();
    atualizar.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-seed on open/rule only
  }, [open, automacao]);

  const comercialStages = comercialPipeline.useStages({ enabled: open });
  const esteiraStages = esteiraPipeline.useStages({ enabled: open });
  const stagesQuery = pipeline === "comercial" ? comercialStages : esteiraStages;
  const etapas = (stagesQuery.data ?? []).filter((s) => s.ativo !== false);
  const carregandoEtapas = stagesQuery.isPending && !stagesQuery.data;

  // A tipo the chosen board cannot run (checklist on the Esteira) is reset.
  useEffect(() => {
    if (!TIPOS_POR_PIPELINE[pipeline].includes(tipo)) setTipo(TIPOS_POR_PIPELINE[pipeline][0]);
  }, [pipeline, tipo]);

  const slaValido = gatilho !== "sla" || (/^\d+$/.test(slaHoras) && Number(slaHoras) > 0 && Number(slaHoras) <= 8760);
  const problema = !stageId
    ? "Escolha a etapa."
    : !slaValido
      ? "SLA em horas: um número entre 1 e 8760."
      : problemaDoDraft(tipo, draft);
  const salvando = criar.isPending || atualizar.isPending;
  const erro = criar.error ?? atualizar.error;

  function salvar() {
    if (problema) return;
    const acao = montarAcao(tipo, draft);
    const sla_horas = gatilho === "sla" ? Number(slaHoras) : null;
    const done = {
      onSuccess: () => {
        toast.success(editando ? "Automação atualizada." : "Automação criada.");
        onClose();
      },
    };
    if (automacao) {
      atualizar.mutate({ id: automacao.id, patch: { stage_id: stageId, gatilho, sla_horas, acao, ativo } }, done);
    } else {
      criar.mutate({ pipeline, stage_id: stageId, gatilho, sla_horas, acao, ativo }, done);
    }
  }

  const setD = (k: keyof AcaoDraft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title={editando ? "Editar automação" : "Nova automação"}
      widthClassName="sm:max-w-xl"
      testId="automacao-form"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex min-h-10 items-center gap-2 text-sm text-foreground">
            <Switch checked={ativo} onCheckedChange={setAtivo} aria-label="Automação ativa" />
            Ativa
          </label>
          <div className="flex gap-2">
            <Button variant="outline" className="max-sm:h-10" onClick={onClose} disabled={salvando}>
              Cancelar
            </Button>
            <Button className="max-sm:h-10" onClick={salvar} disabled={!!problema || salvando} data-testid="automacao-salvar">
              {salvando ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Quadro">
            <Select
              className="h-10 sm:h-8"
              aria-label="Quadro"
              value={pipeline}
              disabled={editando}
              onChange={(e) => {
                setPipeline(e.target.value as PipelineAutomacao);
                setStageId("");
              }}
            >
              {(Object.keys(PIPELINE_LABEL) as PipelineAutomacao[]).map((p) => (
                <option key={p} value={p}>
                  {PIPELINE_LABEL[p]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Etapa" required>
            <Select
              className="h-10 sm:h-8"
              aria-label="Etapa"
              value={stageId}
              disabled={carregandoEtapas}
              onChange={(e) => setStageId(e.target.value)}
            >
              <option value="">{carregandoEtapas ? "Carregando etapas…" : "Escolha a etapa"}</option>
              {etapas.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {stagesQuery.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {describeError(stagesQuery.error, "Não foi possível carregar as etapas.")}
          </p>
        ) : null}

        <fieldset className="space-y-2">
          <legend className="mb-1 text-xs text-muted-foreground">Quando</legend>
          <div role="radiogroup" aria-label="Gatilho" className="grid grid-cols-2 gap-2">
            {(Object.keys(GATILHO_LABEL) as Gatilho[]).map((g) => (
              <button
                key={g}
                type="button"
                role="radio"
                aria-checked={gatilho === g}
                onClick={() => setGatilho(g)}
                className={cn(
                  "min-h-10 rounded-lg border p-2 text-left text-sm",
                  gatilho === g ? "border-primary bg-primary/5 text-foreground" : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {GATILHO_LABEL[g]}
              </button>
            ))}
          </div>
          {gatilho === "sla" ? (
            <Field label="Horas parado na etapa até disparar">
              <Input
                className="w-32 max-sm:h-10"
                type="number"
                inputMode="numeric"
                min={1}
                max={8760}
                aria-label="SLA em horas"
                value={slaHoras}
                onChange={(e) => setSlaHoras(e.target.value)}
              />
            </Field>
          ) : null}
        </fieldset>

        <Field label="Ação">
          <Select className="h-10 sm:h-8" aria-label="Tipo de ação" value={tipo} onChange={(e) => setTipo(e.target.value as TipoAcao)}>
            {TIPOS_POR_PIPELINE[pipeline].map((t) => (
              <option key={t} value={t}>
                {TIPO_ACAO_LABEL[t]}
              </option>
            ))}
          </Select>
        </Field>

        <ParamsForm tipo={tipo} draft={draft} setD={setD} setDraft={setDraft} />

        <p className="text-[11px] text-muted-foreground">
          Textos aceitam {"{nome}"}, {"{empresa}"}, {"{titulo}"}, {"{etapa}"} e {"{cliente}"}.
        </p>
        {problema ? <p className="text-xs text-muted-foreground">{problema}</p> : null}
        <FormError message={erro ? describeError(erro, "Não foi possível salvar a automação.") : null} />
      </div>
    </SheetDialog>
  );
}

function ParamsForm({
  tipo,
  draft,
  setD,
  setDraft,
}: {
  tipo: TipoAcao;
  draft: AcaoDraft;
  setD: (k: keyof AcaoDraft) => (e: { target: { value: string } }) => void;
  setDraft: (fn: (d: AcaoDraft) => AcaoDraft) => void;
}) {
  const { profissionais } = useProfissionais();
  const { membros, loading: carregandoMembros } = useMembrosEquipe();
  const ativos = profissionais.filter((p) => p.ativo);

  switch (tipo) {
    case "criar_checklist":
      return (
        <div className="space-y-3" data-testid="params-criar_checklist">
          <Field label="Título do checklist" required>
            <Input className="max-sm:h-10" value={draft.titulo} onChange={setD("titulo")} />
          </Field>
          <Field label="Itens (um por linha)">
            <Textarea rows={4} value={draft.itens} onChange={setD("itens")} />
          </Field>
        </div>
      );
    case "definir_responsavel":
      return (
        <Field label="Responsável" required>
          <Select className="h-10 sm:h-8" aria-label="Responsável" value={draft.profissional_id} onChange={setD("profissional_id")}>
            <option value="">Escolha…</option>
            {ativos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </Select>
        </Field>
      );
    case "criar_tarefa":
      return (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="params-criar_tarefa">
          <div className="sm:col-span-2">
            <Field label="Título da tarefa" required>
              <Input className="max-sm:h-10" value={draft.titulo} onChange={setD("titulo")} />
            </Field>
          </div>
          <Field label="Prazo (dias)">
            <Input className="max-sm:h-10" type="number" inputMode="numeric" min={0} max={365} value={draft.prazo_dias} onChange={setD("prazo_dias")} />
          </Field>
          <Field label="Responsável">
            <Select className="h-10 sm:h-8" aria-label="Responsável da tarefa" value={draft.responsavel_id} onChange={setD("responsavel_id")}>
              <option value="">O do card</option>
              {ativos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      );
    case "notificar":
      return (
        <div className="space-y-3" data-testid="params-notificar">
          <Field label="Título">
            <Input className="max-sm:h-10" value={draft.titulo} onChange={setD("titulo")} placeholder="{titulo} entrou em {etapa}" />
          </Field>
          <Field label="Mensagem">
            <Textarea rows={3} value={draft.mensagem} onChange={setD("mensagem")} />
          </Field>
          <fieldset>
            <legend className="mb-1 text-xs text-muted-foreground">
              Notificar também (o responsável do card sempre recebe)
            </legend>
            {carregandoMembros ? (
              <p className="text-xs text-muted-foreground">Carregando equipe…</p>
            ) : membros.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nenhum membro na equipe.</p>
            ) : (
              <ul className="grid gap-1 sm:grid-cols-2">
                {membros.map((m) => (
                  <li key={m.id}>
                    <label className="flex min-h-10 items-center gap-2 text-sm text-foreground sm:min-h-8">
                      <input
                        type="checkbox"
                        className="h-4 w-4"
                        checked={draft.usuario_ids.includes(m.id)}
                        onChange={(e) =>
                          setDraft((d) => ({
                            ...d,
                            usuario_ids: e.target.checked ? [...d.usuario_ids, m.id] : d.usuario_ids.filter((x) => x !== m.id),
                          }))
                        }
                      />
                      <span className="truncate">{m.nome || m.email}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
        </div>
      );
    case "enviar_email":
      return (
        <div className="space-y-3" data-testid="params-enviar_email">
          <Field label="Assunto" required>
            <Input className="max-sm:h-10" value={draft.assunto} onChange={setD("assunto")} />
          </Field>
          <Field label="Mensagem" required>
            <Textarea rows={5} value={draft.mensagem} onChange={setD("mensagem")} />
          </Field>
          <Field label="Para (vazio = e-mail do contato do card)">
            <Input className="max-sm:h-10" type="email" inputMode="email" value={draft.para} onChange={setD("para")} />
          </Field>
        </div>
      );
    case "enviar_whatsapp":
      return (
        <div className="space-y-3" data-testid="params-enviar_whatsapp">
          <Field label="Mensagem" required>
            <Textarea rows={4} value={draft.mensagem} onChange={setD("mensagem")} />
          </Field>
          <Field label="Para (vazio = WhatsApp do contato do card)">
            <Input className="max-sm:h-10" type="tel" inputMode="tel" value={draft.para} onChange={setD("para")} />
          </Field>
        </div>
      );
  }
}
