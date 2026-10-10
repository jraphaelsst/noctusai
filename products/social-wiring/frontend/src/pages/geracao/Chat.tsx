/**
 * Chat (P2, `/media-creation/chat`) — contract §7.2. Two agents (HEADLINE /
 * ROTEIRO) over a streaming conversation with @-references, memory, a context
 * meter and mic dictation. Loading: `showSkeleton` / `isRefreshing`, never
 * `.isLoading`. Deep links: `?c=` selects a conversation, `?cite_viral=` and
 * `?cite_perfil=` pre-attach a reference. Documents upload is phase 2 (not shown).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Brain, BookMarked } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Composer, MENSAGEM_MAX } from "@/components/geracao/chat/Composer";
import { ConversasRail } from "@/components/geracao/chat/ConversasRail";
import { MemoriaModal } from "@/components/geracao/chat/MemoriaModal";
import { MencaoPicker } from "@/components/geracao/chat/MencaoPicker";
import { MensagemItem } from "@/components/geracao/chat/MensagemItem";
import { ViralModal } from "@/components/geracao/biblioteca/ViralModal";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import {
  MAX_REFERENCIAS,
  resolverViralPorCodigo,
  useApagarConversa,
  useContextoChat,
  useConversas,
  useCriarConversa,
  useDitadoChat,
  useEnviarMensagem,
  useMensagens,
  useRenomearConversa,
  useSalvarHeadline,
} from "@/hooks/geracao/useChat";
import { usePerfisMonitorados } from "@/hooks/geracao/useBiblioteca";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { Agente, Mencao } from "@/types/geracao";

const msg = (e: unknown, fallback: string) =>
  e instanceof Error && e.message ? e.message.replace(/^\[\d+\]\s*/, "") : fallback;

export default function Chat() {
  const [params, setParams] = useSearchParams();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [agente, setAgente] = useState<Agente>("headline");
  const conversaId = params.get("c");
  const setConversa = (id: string | null) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        if (id) n.set("c", id);
        else n.delete("c");
        return n;
      },
      { replace: true },
    );

  const conversasQ = useConversas(marcaId, agente);
  const mensagensQ = useMensagens(conversaId);
  const contextoQ = useContextoChat(conversaId);
  const criarConversa = useCriarConversa();
  const renomear = useRenomearConversa();
  const apagar = useApagarConversa();
  const salvarHeadline = useSalvarHeadline();
  const { estado, enviar, parar } = useEnviarMensagem();
  const perfisQ = usePerfisMonitorados();

  const [texto, setTexto] = useState("");
  const [referencias, setReferencias] = useState<Mencao[]>([]);
  const [mencoesAberto, setMencoesAberto] = useState(false);
  const [memoriaAberta, setMemoriaAberta] = useState(false);
  const [viralId, setViralId] = useState<string | null>(null);
  const [roteiro, setRoteiro] = useState<{ id?: string; texto: string } | null>(null);
  const [salvos, setSalvos] = useState<Map<string, string>>(new Map());
  const fimRef = useRef<HTMLDivElement | null>(null);

  const ditado = useDitadoChat(marcaId, (t) => setTexto((atual) => (atual.trim() ? `${atual.trimEnd()} ${t}` : t).slice(0, MENSAGEM_MAX)));

  // Conversations belong to (marca, agente): drop the selection when either changes.
  const chaveEscopo = `${marcaId ?? ""}:${agente}`;
  const escopoAnterior = useRef(chaveEscopo);
  useEffect(() => {
    if (escopoAnterior.current !== chaveEscopo) {
      escopoAnterior.current = chaveEscopo;
      setConversa(null);
      setReferencias([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaveEscopo]);

  // Deep links: pre-attach once, then clean the URL.
  const citeViral = params.get("cite_viral");
  const citePerfil = params.get("cite_perfil");
  useEffect(() => {
    if (citeViral) {
      setReferencias((r) =>
        r.some((x) => x.tipo === "biblioteca" && x.id === citeViral)
          ? r
          : [...r, { tipo: "biblioteca", id: citeViral, rotulo: "Viral citado", detalhe: null }],
      );
      setParams((p) => { const n = new URLSearchParams(p); n.delete("cite_viral"); return n; }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [citeViral]);
  useEffect(() => {
    if (!citePerfil || !perfisQ.data) return;
    const handle = perfisQ.data.find((p) => p.id === citePerfil)?.handle;
    setReferencias((r) =>
      r.some((x) => x.tipo === "biblioteca" && x.id === `perfil:${citePerfil}`)
        ? r
        : [
            ...r,
            {
              tipo: "biblioteca",
              // BE-6 convention: a whole-profile reference is `perfil:<uuid>` (chat_contexto.py).
              id: `perfil:${citePerfil}`,
              rotulo: `${handle ? `@${handle}` : "@perfil"} — Todos os vídeos`,
              detalhe: null,
            },
          ],
    );
    setParams((p) => { const n = new URLSearchParams(p); n.delete("cite_perfil"); return n; }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [citePerfil, perfisQ.data]);

  const mensagens = mensagensQ.mensagens;
  useEffect(() => {
    fimRef.current?.scrollIntoView?.({ block: "end" });
  }, [mensagens.length, estado.texto, estado.usuario]);

  const codigosPermitidos = estado.codigosPermitidos;
  const contextoChars = estado.contextoChars ?? contextoQ.data?.contexto_chars ?? null;
  const semMarca = !marcaId && !marcasQ.isPending;
  const ocupado = estado.ativo || criarConversa.isPending;

  async function onEnviar() {
    const conteudo = texto.trim();
    if (!conteudo || !marcaId || ocupado) return;
    let id = conversaId;
    if (!id) {
      try {
        const c = await criarConversa.mutateAsync({ marca_id: marcaId, agente, titulo: conteudo.slice(0, 60) });
        id = c.id;
        setConversa(c.id);
      } catch (e) {
        toast.error(msg(e, "Não foi possível criar a conversa."));
        return;
      }
    }
    const refs = referencias.map((r) => ({ tipo: r.tipo, id: r.id }));
    setTexto("");
    setReferencias([]);
    const ok = await enviar(id, conteudo, refs);
    if (!ok) {
      // Keep what the user wrote so a refused send (409/429/503) is retryable.
      setTexto((atual) => atual || conteudo);
      setReferencias((atual) => (atual.length ? atual : referencias));
    }
  }

  async function abrirEstrutura(codigo: number) {
    if (!marcaId) return;
    try {
      const v = await resolverViralPorCodigo(marcaId, codigo);
      if (v) setViralId(v.id);
      else toast.error(`A estrutura #${codigo} não está na sua Biblioteca.`);
    } catch (e) {
      toast.error(msg(e, "Não foi possível abrir a estrutura."));
    }
  }

  async function salvar(textoHeadline: string): Promise<string | null> {
    const existente = salvos.get(textoHeadline);
    if (existente) return existente;
    if (!marcaId) return null;
    try {
      const h = await salvarHeadline.mutateAsync({ marca_id: marcaId, texto: textoHeadline });
      setSalvos((m) => new Map(m).set(textoHeadline, h.id));
      toast.success("Headline salva nos favoritos.");
      return h.id;
    } catch (e) {
      toast.error(msg(e, "Não foi possível salvar a headline."));
      return null;
    }
  }

  async function criarRoteiro(textoHeadline: string, editavel: boolean) {
    // "a partir desta headline" links the roteiro to a saved headline; the
    // editable variant opens the modal with free text the user can rewrite.
    if (editavel) {
      setRoteiro({ texto: textoHeadline });
      return;
    }
    const id = await salvar(textoHeadline);
    setRoteiro(id ? { id, texto: textoHeadline } : null);
  }

  const salvosSet = useMemo(() => new Set(salvos.keys()), [salvos]);
  const erroMensagens = mensagensQ.isError && !mensagensQ.data;

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Criar Headlines e Roteiros</h1>
          <p className="text-sm text-muted-foreground">Converse com a IA para gerar headlines e roteiros com a sua voz.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button asChild variant="outline" size="sm">
            <Link to="/media-creation/cerebro">
              <Brain className="mr-1 h-4 w-4" /> Segundo cérebro
            </Link>
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={!marcaId} onClick={() => setMemoriaAberta(true)}>
            <BookMarked className="mr-1 h-4 w-4" /> Memória
          </Button>
        </div>
      </header>

      <Tabs value={agente} onValueChange={(v) => setAgente(v as Agente)}>
        <TabsList aria-label="Agente">
          <TabsTrigger value="headline">HEADLINE</TabsTrigger>
          <TabsTrigger value="roteiro">ROTEIRO</TabsTrigger>
        </TabsList>
      </Tabs>

      {semMarca ? (
        <p className="text-sm text-muted-foreground">Cadastre uma marca para conversar com a IA.</p>
      ) : (
        <div className="flex flex-col gap-4 md:flex-row">
          <ConversasRail
            conversas={conversasQ.conversas}
            selecionadaId={conversaId}
            showSkeleton={conversasQ.showSkeleton}
            isRefreshing={conversasQ.isRefreshing}
            erro={conversasQ.isError && !conversasQ.data}
            onTentarNovamente={() => void conversasQ.refetch()}
            temMais={!!conversasQ.hasNextPage}
            carregandoMais={conversasQ.isFetchingNextPage}
            onVerMais={() => void conversasQ.fetchNextPage()}
            onSelecionar={setConversa}
            onNova={() => {
              setConversa(null);
              setReferencias([]);
            }}
            onRenomear={async (id, titulo) => {
              try {
                await renomear.mutateAsync({ id, titulo });
              } catch (e) {
                toast.error(msg(e, "Não foi possível renomear."));
                throw e;
              }
            }}
            onApagar={async (id) => {
              try {
                await apagar.mutateAsync(id);
                if (id === conversaId) setConversa(null);
                toast.success("Conversa apagada.");
              } catch (e) {
                toast.error(msg(e, "Não foi possível apagar a conversa."));
                throw e;
              }
            }}
          />

          <section className="flex min-w-0 flex-1 flex-col gap-3" aria-label="Conversa">
            <div className="flex min-h-[320px] flex-1 flex-col gap-4 overflow-y-auto rounded-lg border p-4" aria-busy={mensagensQ.isRefreshing}>
              {mensagensQ.showSkeleton ? (
                <div className="space-y-3" data-testid="mensagens-skeleton">
                  <Skeleton className="h-16 w-2/3" />
                  <Skeleton className="ml-auto h-10 w-1/2" />
                  <Skeleton className="h-24 w-3/4" />
                </div>
              ) : erroMensagens ? (
                <div role="alert" className="text-sm">
                  Não foi possível carregar as mensagens.{" "}
                  <Button type="button" size="sm" variant="outline" onClick={() => void mensagensQ.refetch()}>
                    Tentar novamente
                  </Button>
                </div>
              ) : (
                <>
                  {mensagensQ.hasNextPage && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="self-center"
                      disabled={mensagensQ.isFetchingNextPage}
                      onClick={() => void mensagensQ.fetchNextPage()}
                    >
                      {mensagensQ.isFetchingNextPage ? "Carregando..." : "Carregar mensagens anteriores"}
                    </Button>
                  )}
                  {mensagens.length === 0 && !estado.usuario && (
                    <p className="m-auto max-w-md text-center text-sm text-muted-foreground">
                      {agente === "headline"
                        ? "Peça headlines: por exemplo, “me dê 10 headlines sobre o meu tema, baseadas em @um perfil da Biblioteca”."
                        : "Peça um roteiro: cole uma headline ou mencione uma pesquisa ou um cérebro."}
                    </p>
                  )}
                  {mensagens.map((m) => (
                    <MensagemItem
                      key={m.id}
                      role={m.role}
                      conteudo={m.conteudo}
                      agente={agente}
                      referencias={m.referencias}
                      status={m.status}
                      truncada={m.truncada}
                      salvos={salvosSet}
                      salvando={salvarHeadline.isPending}
                      onAbrirEstrutura={(c) => void abrirEstrutura(c)}
                      onSalvar={(t) => void salvar(t)}
                      onCriarRoteiro={(t, ed) => void criarRoteiro(t, ed)}
                    />
                  ))}
                  {estado.usuario && (
                    <MensagemItem
                      role="user"
                      conteudo={estado.usuario}
                      agente={agente}
                      salvos={salvosSet}
                      salvando={false}
                      onAbrirEstrutura={() => undefined}
                      onSalvar={() => undefined}
                      onCriarRoteiro={() => undefined}
                    />
                  )}
                  {estado.ativo && (
                    <MensagemItem
                      role="assistant"
                      conteudo={estado.texto}
                      agente={agente}
                      streaming
                      truncada={estado.truncada}
                      codigosPermitidos={codigosPermitidos}
                      salvos={salvosSet}
                      salvando={false}
                      onAbrirEstrutura={(c) => void abrirEstrutura(c)}
                      onSalvar={() => undefined}
                      onCriarRoteiro={() => undefined}
                    />
                  )}
                  {estado.erro && (
                    <p role="alert" className="text-sm text-destructive">
                      {estado.erro}
                    </p>
                  )}
                </>
              )}
              <div ref={fimRef} />
            </div>

            <Composer
              valor={texto}
              onValor={setTexto}
              referencias={referencias}
              onRemoverReferencia={(r) => setReferencias((l) => l.filter((x) => !(x.tipo === r.tipo && x.id === r.id)))}
              onAbrirMencoes={() => setMencoesAberto(true)}
              contextoChars={contextoChars}
              streaming={estado.ativo}
              desabilitado={!marcaId || criarConversa.isPending}
              onEnviar={() => void onEnviar()}
              onParar={parar}
              onAudio={(blob, mime) => ditado.enviar(blob, mime)}
              transcrevendo={ditado.transcrevendo}
              erroDitado={ditado.erro}
            />
          </section>
        </div>
      )}

      <MencaoPicker
        open={mencoesAberto}
        onOpenChange={setMencoesAberto}
        marcaId={marcaId}
        anexados={referencias}
        limiteAtingido={referencias.length >= MAX_REFERENCIAS}
        onEscolher={(m) => setReferencias((l) => (l.length >= MAX_REFERENCIAS ? l : [...l, m]))}
      />
      <MemoriaModal open={memoriaAberta} onOpenChange={setMemoriaAberta} marcaId={marcaId} />
      <ViralModal open={!!viralId} onOpenChange={(o) => !o && setViralId(null)} marcaId={marcaId} viralId={viralId} />
      <RoteiroAvancadoModal
        open={!!roteiro}
        onOpenChange={(o) => !o && setRoteiro(null)}
        marcaId={marcaId}
        headlineInicial={roteiro}
        onCriado={() => toast.success("Roteiro criado. Acompanhe em Roteiros.")}
      />
    </div>
  );
}
