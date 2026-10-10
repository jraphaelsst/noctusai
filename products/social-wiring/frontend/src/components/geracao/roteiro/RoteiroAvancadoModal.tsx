/**
 * Roteiro Avançado — "Crie um roteiro avançado em 3 passos" (contract §7.8,
 * page-map-v2 §20). Shared by Roteiros, Headlines Favoritas/Sugeridas, Chat
 * and the Dashboard: pass `headlineInicial` to open it prefilled.
 *
 * Flow (REAL status from polling `GET /roteiros/{id}`, never a fake bar):
 *   form → criando → [perguntas → processando] → completo | falha
 * Fontes: only "Deixe a IA pensar" is enabled in v1 (contract §4.5 #32, phase 2
 * brings web / link). Closing mid-run is safe — the run continues server-side
 * and shows up in Meus roteiros.
 */
import { useEffect, useState } from "react";
import { AlertCircle, Brain, Globe, Link2, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { VideoPicker } from "@/components/geracao/biblioteca/VideoPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCerebroBrains } from "@/hooks/useCerebro";
import {
  useCriarRoteiro,
  useGerarRoteiro,
  useResponderPerguntas,
  useRoteiro,
} from "@/hooks/geracao/useRoteiros";
import { cn } from "@/lib/utils";
import type { Roteiro } from "@/types/geracao";
import { HEADLINE_TEXTO_MAX } from "../labels";
import { FeedbackRoteiro } from "./FeedbackRoteiro";
import { RoteiroCorpo, useEdicaoRoteiro } from "./RoteiroEdicao";

export const INSTRUCOES_MAX = 5000;
export const RESPOSTA_MAX = 1000;

const DURACOES: { valor: Roteiro["duracao"]; rotulo: string }[] = [
  { valor: "auto", rotulo: "Auto (recomendado)" },
  { valor: "1", rotulo: "~1 min" },
  { valor: "2", rotulo: "~2 min" },
  { valor: "3", rotulo: "~3 min" },
];

export interface HeadlineInicial {
  id?: string | null;
  texto: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string | null;
  /** Prefill from a favorita / sugerida / dashboard row; omit for an empty headline. */
  headlineInicial?: HeadlineInicial | null;
  onCriado?: (roteiro: Roteiro) => void;
}

function mensagemErro(e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message.replace(/^\[\d+\]\s*/, "") : "";
  return msg || fallback;
}

export function RoteiroAvancadoModal({ open, onOpenChange, marcaId, headlineInicial, onCriado }: Props) {
  const [headline, setHeadline] = useState("");
  const [instrucoes, setInstrucoes] = useState("");
  const [duracao, setDuracao] = useState<Roteiro["duracao"]>("auto");
  const [brainId, setBrainId] = useState<string>("");
  const [viralId, setViralId] = useState<string | null>(null);
  const [comPerguntas, setComPerguntas] = useState(true);
  const [roteiroId, setRoteiroId] = useState<string | null>(null);
  const [respostas, setRespostas] = useState<Record<string, string>>({});

  const brainsQ = useCerebroBrains(open ? marcaId : null);
  const brains = (brainsQ.data ?? []).filter((b) => b.content_chars > 0);

  const criar = useCriarRoteiro();
  const responder = useResponderPerguntas();
  const gerar = useGerarRoteiro();
  const roteiroQ = useRoteiro(roteiroId);
  const roteiro = roteiroQ.data;
  const edicao = useEdicaoRoteiro(roteiro);

  // (Re)open: reset to a fresh form, prefilled when the modal comes from a headline.
  useEffect(() => {
    if (!open) return;
    setHeadline(headlineInicial?.texto ?? "");
    setInstrucoes("");
    setDuracao("auto");
    setBrainId("");
    setViralId(null);
    setComPerguntas(true);
    setRoteiroId(null);
    setRespostas({});
  }, [open, headlineInicial?.id, headlineInicial?.texto]);

  // Seed the answers form once the questions arrive.
  useEffect(() => {
    if (roteiro?.status !== "perguntas") return;
    setRespostas((atual) => {
      const novo: Record<string, string> = {};
      for (const p of roteiro.perguntas) novo[p.id] = atual[p.id] ?? p.resposta ?? "";
      return novo;
    });
  }, [roteiro?.id, roteiro?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const headlineLimpa = headline.trim();
  const podeCriar =
    !!marcaId && headlineLimpa.length > 0 && headlineLimpa.length <= HEADLINE_TEXTO_MAX && !criar.isPending;

  async function enviar() {
    if (!podeCriar || !marcaId) return;
    const mesmaHeadline = !!headlineInicial?.id && headlineLimpa === headlineInicial.texto.trim();
    try {
      const novo = await criar.mutateAsync({
        marca_id: marcaId,
        headline_id: mesmaHeadline ? headlineInicial?.id : null,
        headline_texto: headlineLimpa,
        instrucoes: instrucoes.trim() || undefined,
        fonte: "ia",
        duracao,
        brain_id: brainId || null,
        viral_id: viralId,
        gerar_perguntas: comPerguntas,
      });
      setRoteiroId(novo.id);
      onCriado?.(novo);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível criar o roteiro."));
    }
  }

  async function pularPerguntas() {
    if (!roteiro) return;
    try {
      await gerar.mutateAsync({ id: roteiro.id, pular_perguntas: true });
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível gerar o roteiro."));
    }
  }

  async function gerarComRespostas() {
    if (!roteiro) return;
    try {
      await responder.mutateAsync({
        id: roteiro.id,
        respostas: roteiro.perguntas.map((p) => ({ id: p.id, resposta: (respostas[p.id] ?? "").trim() })),
      });
      await gerar.mutateAsync({ id: roteiro.id });
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível gerar o roteiro."));
    }
  }

  const ocupado = responder.isPending || gerar.isPending;
  const status = roteiro?.status;
  const emForm = !roteiroId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Roteiro Avançado</DialogTitle>
          <DialogDescription>Crie um roteiro avançado em 3 passos</DialogDescription>
        </DialogHeader>

        {emForm && (
          <div className="space-y-5">
            <div className="space-y-1.5">
              <Label htmlFor="ra-headline">Headline</Label>
              <p className="text-xs text-muted-foreground">
                Base do roteiro. Se veio de sugerida ou favorita, já está preenchida.
              </p>
              <Textarea
                id="ra-headline"
                rows={2}
                maxLength={HEADLINE_TEXTO_MAX}
                placeholder="Ex: 3 alimentos que aumentam testosterona"
                value={headline}
                onChange={(e) => setHeadline(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ra-instrucoes">Instruções</Label>
              <p className="text-xs text-muted-foreground">
                Tom, público-alvo, o que pode ou não falar. Quanto mais detalhes, melhor.
              </p>
              <Textarea
                id="ra-instrucoes"
                rows={3}
                maxLength={INSTRUCOES_MAX}
                placeholder="Ex: tom descontraído, público iniciante, não citar marcas"
                value={instrucoes}
                onChange={(e) => setInstrucoes(e.target.value)}
              />
            </div>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Fonte das informações</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                <button
                  type="button"
                  aria-pressed
                  className="flex flex-col items-start gap-1 rounded-md border-2 border-primary bg-primary/5 p-3 text-left text-sm"
                >
                  <Sparkles className="h-4 w-4" />
                  <span className="font-medium">Deixe a IA pensar</span>
                </button>
                {[
                  { rotulo: "Pesquisar na web", Icone: Globe },
                  { rotulo: "Link específico", Icone: Link2 },
                ].map(({ rotulo, Icone }) => (
                  <button
                    key={rotulo}
                    type="button"
                    disabled
                    aria-disabled
                    className={cn(
                      "flex flex-col items-start gap-1 rounded-md border p-3 text-left text-sm",
                      "cursor-not-allowed opacity-60",
                    )}
                  >
                    <Icone className="h-4 w-4" />
                    <span className="font-medium">{rotulo}</span>
                    <Badge variant="secondary">Em breve</Badge>
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Duração do vídeo</legend>
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Duração do vídeo">
                {DURACOES.map((d) => (
                  <Button
                    key={d.valor}
                    type="button"
                    size="sm"
                    role="radio"
                    aria-checked={duracao === d.valor}
                    variant={duracao === d.valor ? "default" : "outline"}
                    onClick={() => setDuracao(d.valor)}
                  >
                    {d.rotulo}
                  </Button>
                ))}
              </div>
            </fieldset>

            <div className="space-y-1.5">
              <Label htmlFor="ra-brain">
                <Brain className="mr-1 inline h-4 w-4" />
                Segundo Cérebro (opcional)
              </Label>
              {brainsQ.showSkeleton ? (
                <Skeleton className="h-9 w-full" />
              ) : (
                <select
                  id="ra-brain"
                  value={brainId}
                  onChange={(e) => setBrainId(e.target.value)}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm"
                >
                  <option value="">Nenhum</option>
                  {brains.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>Vídeo da biblioteca (opcional)</Label>
              {marcaId && <VideoPicker marcaId={marcaId} value={viralId} onChange={setViralId} />}
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="ra-perguntas"
                checked={comPerguntas}
                onCheckedChange={(v) => setComPerguntas(v === true)}
              />
              <Label htmlFor="ra-perguntas">Responder perguntas estratégicas antes (recomendado)</Label>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button disabled={!podeCriar} onClick={enviar}>
                {criar.isPending ? "Criando…" : "Criar roteiro"}
              </Button>
            </DialogFooter>
          </div>
        )}

        {!emForm && roteiroQ.showSkeleton && <Skeleton className="h-40 w-full" />}

        {!emForm && roteiroQ.isError && !roteiro && (
          <div role="alert" className="flex items-center justify-between rounded-md border p-3 text-sm">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar o roteiro.
            </span>
            <Button size="sm" variant="outline" onClick={() => roteiroQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        )}

        {roteiro && (status === "criando" || status === "processando") && (
          <div role="status" className="space-y-2 py-8 text-center text-sm text-muted-foreground">
            <Loader2 className="mx-auto h-6 w-6 animate-spin" />
            <p className="font-medium text-foreground">{roteiro.etapa ?? (status === "criando" ? "Criando…" : "Gerando roteiro…")}</p>
            <p>Isto pode levar 1–2 minutos. Você pode fechar: o roteiro continua em Meus roteiros.</p>
          </div>
        )}

        {roteiro && status === "perguntas" && (
          <div className="space-y-4">
            <div className="rounded-md border bg-muted/30 p-3 text-sm">
              <p className="text-xs uppercase text-muted-foreground">Headline Base</p>
              <p>{roteiro.headline_texto}</p>
            </div>
            <p className="text-sm">Responda as perguntas abaixo para personalizar seu roteiro</p>
            {roteiro.perguntas.map((p) => (
              <div key={p.id} className="space-y-1.5">
                <Label htmlFor={`ra-p-${p.id}`}>{p.pergunta}</Label>
                <Textarea
                  id={`ra-p-${p.id}`}
                  rows={2}
                  maxLength={RESPOSTA_MAX}
                  value={respostas[p.id] ?? ""}
                  onChange={(e) => setRespostas((r) => ({ ...r, [p.id]: e.target.value }))}
                />
              </div>
            ))}
            <DialogFooter>
              <Button variant="outline" disabled={ocupado} onClick={pularPerguntas}>
                Pular perguntas
              </Button>
              <Button disabled={ocupado} onClick={gerarComRespostas}>
                {ocupado ? "Enviando…" : "Gerar Roteiro"}
              </Button>
            </DialogFooter>
          </div>
        )}

        {roteiro && status === "falha" && (
          <div className="space-y-3">
            <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
              {roteiro.erro ?? "Não foi possível criar o roteiro."}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
              <Button onClick={() => setRoteiroId(null)}>Tentar novamente</Button>
            </DialogFooter>
          </div>
        )}

        {roteiro && status === "completo" && (
          <div className="space-y-4">
            <p className="font-medium text-emerald-700">Roteiro criado com sucesso!</p>
            <RoteiroCorpo
              roteiro={roteiro}
              edicao={edicao}
              mostrarNome={false}
              onRecarregar={() => roteiroQ.refetch()}
            />
            <FeedbackRoteiro roteiro={roteiro} />
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
              <Button disabled={!edicao.alterou || !edicao.valido || edicao.salvando} onClick={() => void edicao.salvar()}>
                {edicao.salvando ? "Atualizando…" : "Atualizar Roteiro"}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
