/**
 * Chat (`/media-creation/chat`) — Estruturas contract §11.3. ONE unified conversation (no
 * headline/roteiro agents) over a streaming chat with @-references, memory, a context meter and
 * mic dictation. Assistant answers carry server-parsed propostas (cards); choosing one writes the
 * roteiro right away in the same conversation (`roteiro_gerado` message). Loading:
 * `showSkeleton` / `isRefreshing`, never `.isLoading`. Deep links: `?conversa=` (legacy `?c=`)
 * selects a conversation, `?estrutura=<id>` pre-attaches an Estrutura, `?cite_viral=` and
 * `?cite_perfil=` pre-attach a reference.
 */
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Brain, BookMarked } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Composer, MENSAGEM_MAX } from "@/components/geracao/chat/Composer";
import { ConversasRail } from "@/components/geracao/chat/ConversasRail";
import { MemoriaModal } from "@/components/geracao/chat/MemoriaModal";
import { MencaoPicker } from "@/components/geracao/chat/MencaoPicker";
import { MensagemItem } from "@/components/geracao/chat/MensagemItem";
import { PerfilPendenteChips } from "@/components/geracao/chat/PerfilPendenteChips";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import {
  MAX_REFERENCIAS,
  mensagemEscolher,
  useApagarConversa,
  useContextoChat,
  useConversas,
  useCriarConversa,
  useDitadoChat,
  useEnviarMensagem,
  useEscolherProposta,
  useMensagens,
  useRenomearConversa,
} from "@/hooks/geracao/useChat";
import { usePerfisMonitorados } from "@/hooks/geracao/useBiblioteca";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { Mencao } from "@/types/geracao";

const msg = (e: unknown, fallback: string) =>
  e instanceof Error && e.message ? e.message.replace(/^\[\d+\]\s*/, "") : fallback;

export default function Chat() {
  const [params, setParams] = useSearchParams();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  // `?conversa=` is the contract's deep link; `?c=` is the legacy one (still opens).
  const conversaId = params.get("conversa") ?? params.get("c");
  const setConversa = (id: string | null) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        n.delete("c");
        if (id) n.set("conversa", id);
        else n.delete("conversa");
        return n;
      },
      { replace: true },
    );

  const conversasQ = useConversas(marcaId);
  const mensagensQ = useMensagens(conversaId);
  const contextoQ = useContextoChat(conversaId);
  const criarConversa = useCriarConversa();
  const renomear = useRenomearConversa();
  const apagar = useApagarConversa();
  const escolher = useEscolherProposta();
  const { estado, enviar, parar, perfilPendente, limparPerfilPendente } = useEnviarMensagem();
  const perfisQ = usePerfisMonitorados();

  const [texto, setTexto] = useState("");
  const [referencias, setReferencias] = useState<Mencao[]>([]);
  const [mencoesAberto, setMencoesAberto] = useState(false);
  const [memoriaAberta, setMemoriaAberta] = useState(false);
  const fimRef = useRef<HTMLDivElement | null>(null);

  const ditado = useDitadoChat(marcaId, (t) => setTexto((atual) => (atual.trim() ? `${atual.trimEnd()} ${t}` : t).slice(0, MENSAGEM_MAX)));

  // Conversations belong to a marca: switching marca drops the selection. The first resolution
  // (null -> marca) is not a switch — it must not discard a `?conversa=` deep link.
  const marcaAnterior = useRef(marcaId);
  useEffect(() => {
    const anterior = marcaAnterior.current;
    marcaAnterior.current = marcaId;
    if (anterior && anterior !== marcaId) {
      setConversa(null);
      setReferencias([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marcaId]);

  // A profile-choice prompt belongs to the conversation it came from.
  useEffect(() => {
    limparPerfilPendente();
  }, [conversaId, limparPerfilPendente]);

  // Deep links: pre-attach once, then clean the URL.
  const estruturaParam = params.get("estrutura");
  useEffect(() => {
    if (estruturaParam) {
      setReferencias((r) =>
        r.some((x) => x.tipo === "estrutura" && x.id === estruturaParam)
          ? r
          : [...r, { tipo: "estrutura", id: estruturaParam, rotulo: "Estrutura escolhida", detalhe: null }],
      );
      setParams((p) => { const n = new URLSearchParams(p); n.delete("estrutura"); return n; }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estruturaParam]);
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

  const contextoChars = estado.contextoChars ?? contextoQ.data?.contexto_chars ?? null;
  const semMarca = !marcaId && !marcasQ.isPending;
  const ocupado = estado.ativo || criarConversa.isPending;

  async function onEnviar() {
    const conteudo = texto.trim();
    if (!conteudo || !marcaId || ocupado) return;
    let id = conversaId;
    if (!id) {
      try {
        const c = await criarConversa.mutateAsync({ marca_id: marcaId, titulo: conteudo.slice(0, 60) });
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

  /** Click on a proposta (or "Tentar de novo" on a failed flow): the roteiro is written right away. */
  async function onEscolher(propostaId: string) {
    if (!conversaId || escolher.isPending) return;
    try {
      const r = await escolher.mutateAsync({ conversaId, proposta_id: propostaId });
      if (r.ja_existia) toast.info(r.em_andamento ? "Este roteiro já está sendo criado." : "Este roteiro já foi criado.");
    } catch (e) {
      toast.error(mensagemEscolher(e));
    }
  }

  /** The user picked the profile a name meant: the same message goes out again with it attached. */
  async function onEscolherPerfil(perfilId: string) {
    if (!perfilPendente || !conversaId || ocupado) return;
    const refs = [...perfilPendente.referencias, { tipo: "biblioteca" as const, id: `perfil:${perfilId}` }].slice(-MAX_REFERENCIAS);
    const ok = await enviar(conversaId, perfilPendente.conteudo, refs);
    if (!ok) toast.error("Não foi possível reenviar a mensagem com o perfil escolhido.");
  }

  const escolhendoId = escolher.isPending && escolher.variables && "proposta_id" in escolher.variables ? escolher.variables.proposta_id : null;
  const erroMensagens = mensagensQ.isError && !mensagensQ.data;

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Criar Headlines e Roteiros</h1>
          <p className="text-sm text-muted-foreground">
            Converse com a IA: ela propõe headlines a partir das estruturas da Biblioteca e, ao escolher uma, escreve o roteiro.
          </p>
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
                      Peça headlines: por exemplo, “me dê 10 headlines sobre o meu tema, no estilo de @um perfil da Biblioteca”.
                      Escolha uma e eu escrevo o roteiro aqui mesmo.
                    </p>
                  )}
                  {mensagens.map((m) => (
                    <MensagemItem
                      key={m.id}
                      role={m.role}
                      conteudo={m.conteudo}
                      tipo={m.tipo}
                      propostas={m.propostas}
                      fluxo={m.fluxo}
                      referencias={m.referencias}
                      status={m.status}
                      truncada={m.truncada}
                      escolhendoId={escolhendoId}
                      onEscolher={(id) => void onEscolher(id)}
                    />
                  ))}
                  {estado.usuario && (
                    <MensagemItem role="user" conteudo={estado.usuario} />
                  )}
                  {estado.ativo && (
                    <MensagemItem
                      role="assistant"
                      conteudo={estado.texto}
                      streaming
                      truncada={estado.truncada}
                    />
                  )}
                  {perfilPendente && !estado.ativo && (
                    <PerfilPendenteChips
                      pendente={perfilPendente}
                      desabilitado={ocupado}
                      onEscolher={(id) => void onEscolherPerfil(id)}
                      onDispensar={limparPerfilPendente}
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
    </div>
  );
}
