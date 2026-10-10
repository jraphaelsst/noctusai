/**
 * Questionário do cérebro Sistema (`/media-creation/cerebro/:brainId/perguntas`).
 * Contract: cerebro-contract.md §6 "Questionnaire". Numbered question cards,
 * autosave (blur + 1.5 s debounce), reveal in groups, AI review chips,
 * Finalizar → synthesis polled until done → editor. Loading: two signals off
 * `data`, never `isLoading`.
 *
 * NOC-REMEDIATE[voice-answers]: the "Prefiro falar ⇄ Prefiro escrever" toggle is
 * built but OFF (VOZ_HABILITADA). Destination: the seed recorder organ
 * (`useAudioRecorder` + `VoiceAnswerInput`, transcription-contract S4) plus the
 * shared transcription product slice (S3, endpoint 13 `/answers/{id}/audio`).
 * No product-local MediaRecorder component — wire the organ here and flip the flag.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, Loader2, RefreshCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { SugestaoRevisao } from "@/components/cerebro/SugestaoRevisao";
import { mensagemErro, formatarChars } from "@/components/cerebro/labels";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import {
  useCerebroPerguntas,
  useDecidirSugestao,
  useFinalizarRespostas,
  useRevisarRespostas,
  useSalvarResposta,
  useZerarRespostas,
} from "@/hooks/useCerebroPerguntas";
import type { Answer, BrainQuestion } from "@/types/cerebro";

const CEREBRO = "/media-creation/cerebro";
export const AUTOSAVE_MS = 1500;
/** Voice answers are OFF until the seed recorder organ + shared transcription exist (see header). */
export const VOZ_HABILITADA = false;

function Chip({ answer, texto, salvando }: { answer: Answer | undefined; texto: string; salvando: boolean }) {
  if (salvando) return <Badge variant="outline">Salvando…</Badge>;
  const t = answer?.transcricao;
  if (t && (t.status === "na_fila" || t.status === "processando")) {
    return (
      <Badge variant="outline">
        {t.status === "na_fila" && t.posicao != null ? `Na fila (posição ${t.posicao})` : "Transcrevendo áudio…"}
      </Badge>
    );
  }
  if (t?.status === "falhou") {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <Badge variant="destructive">Falha na transcrição</Badge>
        {t.erro?.mensagem && <span className="text-xs text-destructive">{t.erro.mensagem}</span>}
      </span>
    );
  }
  if (answer?.review.status === "pending") return <Badge variant="outline">Revisando…</Badge>;
  return texto.trim() ? <Badge variant="secondary">Respondida</Badge> : <Badge variant="outline">Aguardando resposta</Badge>;
}

export default function CerebroPerguntas({ vozHabilitada = VOZ_HABILITADA }: { vozHabilitada?: boolean } = {}) {
  const { brainId = null } = useParams<{ brainId: string }>();
  const navigate = useNavigate();
  const brainQ = useCerebroPerguntas(brainId);
  const brain = brainQ.data;
  const salvar = useSalvarResposta(brainId ?? "");
  const zerar = useZerarRespostas(brainId ?? "");
  const revisar = useRevisarRespostas(brainId ?? "");
  const decidir = useDecidirSugestao(brainId ?? "");
  const finalizar = useFinalizarRespostas(brainId ?? "");

  const [textos, setTextos] = useState<Record<string, string>>({});
  const textosRef = useRef(textos);
  textosRef.current = textos;
  const sujos = useRef(new Set<string>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [salvando, setSalvando] = useState<Set<string>>(new Set());
  const [grupos, setGrupos] = useState<number | null>(null);
  const [falar, setFalar] = useState(false);
  const [zerarAberto, setZerarAberto] = useState(false);
  const [modoAberto, setModoAberto] = useState(false);
  const [sintetizando, setSintetizando] = useState(false);
  const [decidindo, setDecidindo] = useState<string | null>(null);
  // Cached data can still read "idle" right after the 202; only treat idle as "done"
  // once we saw "processing" or the synthesized_at stamp moved.
  const sintese = useRef<{ viuProcessando: boolean; base: string | null }>({ viuProcessando: false, base: null });

  const perguntas: BrainQuestion[] = useMemo(
    () => [...(brain?.template?.questions ?? [])].sort((a, b) => a.position - b.position),
    [brain?.template],
  );
  const respostas = useMemo(() => {
    const m = new Map<string, Answer>();
    for (const a of brain?.answers ?? []) m.set(a.question_id, a);
    return m;
  }, [brain?.answers]);

  // Custom brains have no questionnaire.
  useEffect(() => {
    if (brain && brain.kind !== "sistema") navigate(`${CEREBRO}/${brain.id}`, { replace: true });
  }, [brain, navigate]);

  // Adopt server text for every question the user is not editing right now.
  useEffect(() => {
    if (!brain) return;
    setTextos((prev) => {
      let mudou = false;
      const next = { ...prev };
      for (const q of perguntas) {
        if (sujos.current.has(q.id)) continue;
        const srv = respostas.get(q.id)?.text ?? "";
        if ((next[q.id] ?? "") !== srv) {
          next[q.id] = srv;
          mudou = true;
        }
      }
      return mudou ? next : prev;
    });
  }, [brain, perguntas, respostas]);

  const totalGrupos = useMemo(() => new Set(perguntas.map((q) => q.group)).size, [perguntas]);
  const ordemGrupos = useMemo(() => [...new Set(perguntas.map((q) => q.group))].sort((a, b) => a - b), [perguntas]);

  // Initial reveal: everything if more than 3 were answered on load, else the first group.
  useEffect(() => {
    if (grupos !== null || !brain || perguntas.length === 0) return;
    const respondidas = brain.answers.filter((a) => a.text.trim()).length;
    setGrupos(respondidas > 3 ? ordemGrupos.length : 1);
  }, [brain, perguntas, ordemGrupos, grupos]);

  const respondeu = (q: BrainQuestion) => (textos[q.id] ?? "").trim().length > 0;
  const visiveis = grupos ?? 1;
  const grupoAtualCompleto = useMemo(() => {
    const g = ordemGrupos[Math.min(visiveis, ordemGrupos.length) - 1];
    return perguntas.filter((q) => q.group === g && !q.optional).every((q) => (textos[q.id] ?? "").trim().length > 0);
  }, [ordemGrupos, visiveis, perguntas, textos]);

  useEffect(() => {
    if (grupos !== null && grupos < ordemGrupos.length && grupoAtualCompleto) setGrupos(grupos + 1);
  }, [grupos, ordemGrupos.length, grupoAtualCompleto]);

  const flush = useCallback(
    async (qid: string) => {
      const t = timers.current.get(qid);
      if (t) {
        clearTimeout(t);
        timers.current.delete(qid);
      }
      if (!sujos.current.has(qid) || !brainId) return;
      const enviado = textosRef.current[qid] ?? "";
      setSalvando((s) => new Set(s).add(qid));
      try {
        await salvar.mutateAsync({ questionId: qid, text: enviado });
        if ((textosRef.current[qid] ?? "") === enviado) sujos.current.delete(qid);
      } catch (e) {
        toast.error(mensagemErro(e, "Não foi possível salvar a resposta."));
      } finally {
        setSalvando((s) => {
          const n = new Set(s);
          n.delete(qid);
          return n;
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [brainId, salvar.mutateAsync],
  );

  const flushTudo = useCallback(async () => {
    await Promise.all([...sujos.current].map((qid) => flush(qid)));
  }, [flush]);

  useEffect(
    () => () => {
      timers.current.forEach((t) => clearTimeout(t));
      timers.current.clear();
    },
    [],
  );

  function onChange(qid: string, valor: string) {
    setTextos((p) => ({ ...p, [qid]: valor }));
    textosRef.current = { ...textosRef.current, [qid]: valor };
    sujos.current.add(qid);
    const antigo = timers.current.get(qid);
    if (antigo) clearTimeout(antigo);
    timers.current.set(
      qid,
      setTimeout(() => void flush(qid), AUTOSAVE_MS),
    );
  }

  const ocupado = salvando.size > 0 || sujos.current.size > 0;
  useEffect(() => {
    if (!ocupado) return;
    const guard = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [ocupado]);

  // Synthesis finished (idle) or failed while we were waiting → leave / report.
  useEffect(() => {
    if (!sintetizando || !brain) return;
    if (brain.synthesis_status === "processing") sintese.current.viuProcessando = true;
    if (brain.synthesis_status === "idle" && (sintese.current.viuProcessando || brain.synthesized_at !== sintese.current.base)) {
      setSintetizando(false);
      toast.success("Cérebro gerado!");
      navigate(`${CEREBRO}/${brain.id}`);
    } else if (brain.synthesis_status === "error") {
      setSintetizando(false);
      toast.error(brain.synthesis_error ?? "Não foi possível gerar o cérebro.");
    }
  }, [sintetizando, brain, navigate]);

  const respondidas = perguntas.filter(respondeu).length;

  async function onRascunho() {
    await flushTudo();
    toast.success("Rascunho salvo com sucesso!");
  }

  async function onRevisar() {
    await flushTudo();
    try {
      await revisar.mutateAsync(undefined);
      toast.success("Respostas enviadas para revisão. Aguarde...");
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível enviar para revisão."));
    }
  }

  async function onZerar() {
    try {
      await zerar.mutateAsync();
      timers.current.forEach((t) => clearTimeout(t));
      timers.current.clear();
      sujos.current.clear();
      setTextos({});
      setGrupos(1);
      setZerarAberto(false);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível zerar as respostas."));
      setZerarAberto(false);
    }
  }

  async function sintetizar(mode: "replace" | "append") {
    if (!brain) return;
    setModoAberto(false);
    try {
      sintese.current = { viuProcessando: false, base: brain.synthesized_at };
      await finalizar.mutateAsync({ mode, expected_version: brain.content_version });
      setSintetizando(true);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível gerar o cérebro."));
    }
  }

  async function onFinalizar() {
    if (!brain) return;
    await flushTudo();
    if (brain.content.trim()) setModoAberto(true);
    else await sintetizar("replace");
  }

  async function onDecidir(qid: string, action: "accept" | "dismiss") {
    setDecidindo(qid);
    try {
      const a = await decidir.mutateAsync({ questionId: qid, action });
      if (action === "accept") {
        sujos.current.delete(qid);
        setTextos((p) => ({ ...p, [qid]: a.text }));
      }
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível registrar a decisão."));
    } finally {
      setDecidindo(null);
    }
  }

  if (brainQ.showSkeleton) {
    return (
      <div className="space-y-4 p-6" aria-busy="true" data-testid="perguntas-skeleton">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!brain) {
    return (
      <div role="alert" className="flex flex-col items-center gap-3 p-16 text-sm">
        <AlertCircle className="h-6 w-6 text-destructive" />
        Não foi possível carregar o questionário.
        <Button variant="outline" size="sm" onClick={() => void brainQ.refetch()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  const gruposVisiveis = new Set(ordemGrupos.slice(0, visiveis));
  const perguntasVisiveis = perguntas.filter((q) => gruposVisiveis.has(q.group));
  const bloqueado = sintetizando || brain.synthesis_status === "processing";

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-2">
        <Button variant="ghost" size="sm" asChild>
          <Link to={`${CEREBRO}/${brain.id}`}>
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Voltar
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold">Cérebro</h1>
        <p className="text-sm text-muted-foreground">Personalize seu cérebro</p>
        {brainQ.isRefreshing && (
          <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Atualizando…
          </span>
        )}
      </header>

      <section className="space-y-1 rounded-lg border bg-card p-4">
        <h2 className="text-base font-semibold">{brain.name} - Sistema</h2>
        <p className="text-sm text-muted-foreground">
          Progresso das respostas {respondidas} de {perguntas.length}
        </p>
        {vozHabilitada && (
          <Button variant="outline" size="sm" onClick={() => setFalar((v) => !v)}>
            {falar ? "Prefiro escrever" : "Prefiro falar"}
          </Button>
        )}
      </section>

      {sintetizando && (
        <div role="status" className="flex items-center gap-2 rounded-md border bg-muted/40 px-4 py-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Gerando cérebro...
        </div>
      )}

      <ol className="space-y-4">
        {perguntasVisiveis.map((q) => {
          const resp = respostas.get(q.id);
          const texto = textos[q.id] ?? "";
          const mostraSugestao =
            resp?.review.status === "done" && resp.review.verdict !== null && resp.review.decision === null;
          return (
            <li key={q.id} className="space-y-2 rounded-lg border bg-card p-4" data-testid="pergunta-card">
              <p className="font-semibold">
                {q.position}. {q.text}
              </p>
              {q.hint && <p className="text-sm italic text-muted-foreground">{q.hint}</p>}
              {/* NOC-REMEDIATE[voice-answers]: `vozHabilitada && falar` renders the seed VoiceAnswerInput here. */}
              <Textarea
                aria-label={`Resposta da pergunta ${q.position}`}
                placeholder="Escreva sua resposta aqui"
                value={texto}
                rows={5}
                maxLength={10_000}
                disabled={bloqueado}
                onChange={(e) => onChange(q.id, e.target.value)}
                onBlur={() => void flush(q.id)}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <Chip answer={resp} texto={texto} salvando={salvando.has(q.id)} />
                <span className="text-muted-foreground">{formatarChars(texto.length)}</span>
              </div>
              {mostraSugestao && resp && (
                <SugestaoRevisao
                  answer={resp}
                  pendente={decidindo === q.id}
                  onDecidir={(action) => void onDecidir(q.id, action)}
                />
              )}
            </li>
          );
        })}
      </ol>

      {visiveis < ordemGrupos.length && (
        <p className="text-sm text-muted-foreground" data-testid="grupo-aviso">
          Grupo {visiveis} de {totalGrupos} - Continue respondendo as próximas perguntas
        </p>
      )}

      <footer className="flex flex-wrap gap-2">
        <Button variant="destructive" disabled={bloqueado} onClick={() => setZerarAberto(true)}>
          Zerar Tudo
        </Button>
        <Button variant="outline" disabled={bloqueado} onClick={() => void onRascunho()}>
          Salvar Rascunho
        </Button>
        <Button variant="outline" disabled={bloqueado || respondidas === 0 || revisar.isPending} onClick={() => void onRevisar()}>
          Revisar com IA
        </Button>
        <Button
          className="ml-auto"
          disabled={bloqueado || respondidas === 0 || finalizar.isPending}
          onClick={() => void onFinalizar()}
        >
          Finalizar Respostas
        </Button>
      </footer>

      <ConfirmarModal
        open={zerarAberto}
        onOpenChange={setZerarAberto}
        titulo="Confirmar Exclusão"
        descricao="Todas as respostas deste cérebro serão apagadas. O conteúdo atual do cérebro não muda."
        rotuloConfirmar="Sim, Zerar Tudo"
        onConfirmar={() => void onZerar()}
        pendente={zerar.isPending}
      />

      <Dialog open={modoAberto} onOpenChange={setModoAberto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Este cérebro já tem conteúdo</DialogTitle>
            <DialogDescription>Deseja substituir o conteúdo atual ou anexar o novo abaixo dele?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => void sintetizar("append")}>
              Anexar abaixo
            </Button>
            <Button onClick={() => void sintetizar("replace")}>Substituir o conteúdo atual</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
