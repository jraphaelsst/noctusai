/**
 * Editor do cérebro (`/media-creation/cerebro/:brainId`) — markdown content with
 * optimistic concurrency (expected_version), file import, rename/delete for
 * custom brains, imports panel polled every 3 s while anything is running.
 * Contract: cerebro-contract.md §6. Loading: two signals, never `.isLoading`.
 */
import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, Loader2, Pencil, RefreshCw, Trash2, Upload } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ImportarArquivoModal } from "@/components/cerebro/ImportarArquivoModal";
import {
  MAX_CONTEUDO,
  STATUS_IMPORT_ROTULO,
  formatarChars,
  mensagemErro,
  statusDe,
} from "@/components/cerebro/labels";
import { ConfirmarModal } from "@/components/pesquisa/ConfirmarModal";
import {
  useCerebroBrain,
  useExcluirBrain,
  useRenomearBrain,
  useSalvarConteudo,
} from "@/hooks/useCerebro";

const CEREBRO = "/media-creation/cerebro";

export default function CerebroEditor() {
  const { brainId = null } = useParams<{ brainId: string }>();
  const navigate = useNavigate();
  const brainQ = useCerebroBrain(brainId);
  const brain = brainQ.data;
  const salvar = useSalvarConteudo();
  const renomear = useRenomearBrain();
  const excluir = useExcluirBrain();

  const [texto, setTexto] = useState("");
  const baseVersao = useRef(0);
  const carregadoPara = useRef<string | null>(null);
  const [conflito, setConflito] = useState(false);
  const [importarAberto, setImportarAberto] = useState(false);
  const [renomearAberto, setRenomearAberto] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [erroNome, setErroNome] = useState<string | null>(null);
  const [excluirAberto, setExcluirAberto] = useState(false);

  const sujo = !!brain && texto !== brain.content;
  const gerando = brain?.synthesis_status === "processing";

  // Adopt server content on first load / brain switch, and whenever the server
  // moved (import or synthesis appended) while the user has no unsaved edits.
  // With unsaved edits the base version stays old, so Aplicar hits the 409 modal.
  useEffect(() => {
    if (!brain) return;
    const trocou = carregadoPara.current !== brain.id;
    const servidorMudou = baseVersao.current !== brain.content_version;
    if (trocou || (servidorMudou && !sujo)) {
      setTexto(brain.content);
      baseVersao.current = brain.content_version;
      carregadoPara.current = brain.id;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brain?.id, brain?.content_version, brain?.content]);

  useEffect(() => {
    if (!sujo) return;
    const guard = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [sujo]);

  async function onAplicar() {
    if (!brain) return;
    try {
      await salvar.mutateAsync({ id: brain.id, content: texto, expected_version: baseVersao.current });
      toast.success("Conteúdo aplicado.");
    } catch (e) {
      if (statusDe(e) === 409 && !/gera[cç][aã]o/i.test(mensagemErro(e, ""))) setConflito(true);
      else toast.error(mensagemErro(e, "Não foi possível aplicar as alterações."));
    }
  }

  async function copiarMeuTexto() {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success("Texto copiado.");
    } catch {
      toast.error("Não foi possível copiar o texto.");
    }
  }

  function recarregar() {
    if (!brain) return;
    setConflito(false);
    carregadoPara.current = null;
    void brainQ.refetch();
  }

  async function onRenomear() {
    if (!brain) return;
    const name = novoNome.trim();
    if (!name) {
      setErroNome("Informe o nome do cérebro.");
      return;
    }
    try {
      await renomear.mutateAsync({ id: brain.id, name });
      setRenomearAberto(false);
      toast.success("Cérebro renomeado.");
    } catch (e) {
      setErroNome(mensagemErro(e, "Não foi possível renomear."));
    }
  }

  async function onExcluir() {
    if (!brain) return;
    try {
      await excluir.mutateAsync(brain.id);
      toast.success("Cérebro excluído.");
      navigate(CEREBRO);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível excluir o cérebro."));
      setExcluirAberto(false);
    }
  }

  if (brainQ.showSkeleton) {
    return (
      <div className="space-y-4 p-6" aria-busy="true" data-testid="editor-skeleton">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (!brain) {
    return (
      <div role="alert" className="flex flex-col items-center gap-3 p-16 text-sm">
        <AlertCircle className="h-6 w-6 text-destructive" />
        Não foi possível carregar o cérebro.
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void brainQ.refetch()}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to={CEREBRO}>Voltar</Link>
          </Button>
        </div>
      </div>
    );
  }

  const sistema = brain.kind === "sistema";

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-2">
        <Button variant="ghost" size="sm" asChild>
          <Link to={CEREBRO}>
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Voltar
          </Link>
        </Button>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{brain.name}</h1>
          {sistema ? (
            <Badge variant="secondary">Sistema</Badge>
          ) : (
            <>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Renomear Cérebro"
                onClick={() => {
                  setNovoNome(brain.name);
                  setErroNome(null);
                  setRenomearAberto(true);
                }}
              >
                <Pencil className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" aria-label="Excluir Cérebro" onClick={() => setExcluirAberto(true)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
          {brainQ.isRefreshing && (
            <span role="status" className="flex items-center gap-1 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Atualizando…
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          Alimente este cérebro com o seu conhecimento — quanto mais rico, melhores os resultados da IA.
        </p>
        <div className="flex flex-wrap gap-2">
          {sistema && (
            <Button variant="outline" asChild>
              <Link to={`${CEREBRO}/${brain.id}/perguntas`}>Responder perguntas</Link>
            </Button>
          )}
          <Button variant="outline" onClick={() => setImportarAberto(true)} disabled={gerando}>
            <Upload className="mr-1.5 h-4 w-4" />
            Enviar arquivo
          </Button>
        </div>
      </header>

      {gerando && (
        <div role="status" className="flex items-center gap-2 rounded-md border bg-muted/40 px-4 py-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Gerando cérebro…
        </div>
      )}
      {brain.synthesis_status === "error" && brain.synthesis_error && (
        <p role="alert" className="text-sm text-destructive">
          {brain.synthesis_error}
        </p>
      )}

      <section className="space-y-3 rounded-lg border bg-card p-4" aria-labelledby="cerebro-conteudo-titulo">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="cerebro-conteudo-titulo" className="text-base font-semibold">
            Conteúdo do cérebro
          </h2>
          <span className="text-sm text-muted-foreground">{formatarChars(texto.length)}</span>
        </div>
        <Textarea
          aria-label="Texto do cérebro"
          value={texto}
          rows={16}
          maxLength={MAX_CONTEUDO}
          readOnly={gerando}
          onChange={(e) => setTexto(e.target.value)}
          className="font-mono text-sm"
        />
        <div className="flex items-center gap-3">
          {sujo && <span className="text-sm text-amber-600">Alterações não aplicadas</span>}
          <Button className="ml-auto" disabled={!sujo || gerando || salvar.isPending} onClick={() => void onAplicar()}>
            {salvar.isPending ? "Aplicando…" : "Aplicar Alterações"}
          </Button>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border bg-card p-4" aria-labelledby="cerebro-imports-titulo">
        <h2 id="cerebro-imports-titulo" className="text-base font-semibold">
          Importações
        </h2>
        {brain.imports.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma importação ainda.</p>
        ) : (
          <ul className="space-y-1.5">
            {brain.imports.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant={i.status === "error" ? "destructive" : i.status === "appended" ? "secondary" : "outline"}>
                  {STATUS_IMPORT_ROTULO[i.status]}
                </Badge>
                <span>{i.filename ?? i.source_url ?? "Importação"}</span>
                {i.status === "appended" && i.chars_appended != null && (
                  <span className="text-muted-foreground">{formatarChars(i.chars_appended)}</span>
                )}
                {i.status === "error" && i.error_message && (
                  <span className="text-destructive">{i.error_message}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ImportarArquivoModal open={importarAberto} onOpenChange={setImportarAberto} brainId={brain.id} />

      <Dialog open={conflito} onOpenChange={setConflito}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>O conteúdo mudou (um arquivo ou transcrição foi anexado)</DialogTitle>
            <DialogDescription>
              Suas alterações não foram aplicadas. Copie seu texto antes de recarregar para não perdê-lo.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => void copiarMeuTexto()}>
              Copiar meu texto
            </Button>
            <Button onClick={recarregar}>Recarregar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renomearAberto} onOpenChange={setRenomearAberto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Renomear Cérebro</DialogTitle>
          </DialogHeader>
          <Input
            aria-label="Novo nome do cérebro"
            value={novoNome}
            maxLength={80}
            onChange={(e) => setNovoNome(e.target.value)}
          />
          {erroNome && (
            <p role="alert" className="text-sm text-destructive">
              {erroNome}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenomearAberto(false)} disabled={renomear.isPending}>
              Cancelar
            </Button>
            <Button onClick={() => void onRenomear()} disabled={renomear.isPending}>
              Renomear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmarModal
        open={excluirAberto}
        onOpenChange={setExcluirAberto}
        titulo="Deletar Cérebro"
        descricao="Tem certeza? Você realmente deseja deletar este Cérebro?"
        rotuloConfirmar="Deletar"
        onConfirmar={() => void onExcluir()}
        pendente={excluir.isPending}
      />
    </div>
  );
}
