/**
 * ImobShotAI -- photo funnel (`/imobshotai/fotos/novo`, status_pagina `imobshotai-fotos-novo`, contract §8). Six
 * steps: 1 Imóvel · 2 Fotos · 3 Estilo · 4 Enviar · 5 Revisão · 6 Pronto.
 *
 *  1. `ImovelCodigoPicker` in select-only mode (free text can never be submitted) + the speed, then
 *     `POST /api/imobshotai/lotes` (contract §1). The speed is asked HERE because the lote's speed is fixed at
 *     creation (there is no later edit route); step 3 shows it read-only.
 *  2. Upload (≤ 10 files per request, sent in blocks) via the Edição de Fotos hooks, or "Puxar fotos do Vista".
 *  3. Read-only view of the speed and of the org's active style guide.
 *  4. Submit, then progress by polling the lote.
 *  5. The shared review screen; D6: approve/reject only for an org admin (`useIsOrgAdmin`, UX only -- the server
 *     answers `403 restrito_admin_organizacao`).
 *  6. Link to the card; the video CTA is disabled ("em breve").
 *
 * The photo work reuses `UploadFotosField`, `VelocidadeField` and `RevisaoLote` (extracted from the Edição de
 * Fotos pages); nothing is copied. Loading-state contract: `showSkeleton` gates the form until `capacidades` land.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertCircle, Check, Lock, Upload } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ImovelCodigoPicker } from "@/components/card/ImovelCodigoPicker";
import { RevisaoLote } from "@/components/edicao-fotos/RevisaoLote";
import { UploadFotosField } from "@/components/edicao-fotos/UploadFotosField";
import { VelocidadeField } from "@/components/edicao-fotos/VelocidadeField";
import { useVelocidadeLote } from "@/components/edicao-fotos/useVelocidadeLote";
import {
  fotosPermissions,
  useCapacidades,
  useConfiguracoes,
  useGuiaEfetivo,
  useLoteVista,
  useUploadFotos,
} from "@/hooks/useEdicaoFotos";
import {
  useImobLoteProgresso,
  useIniciarImobLote,
  useRefrescarCards,
  useSubmeterLoteImob,
  type IniciarLoteResposta,
} from "@/hooks/useImobShotAI";
import { mensagemImobShotAI } from "@/lib/imobshotaiErros";

const PASSOS = ["Imóvel", "Fotos", "Estilo", "Enviar", "Revisão", "Pronto"] as const;
/** Contract §8: at most 10 files per upload request. */
export const MAX_ARQUIVOS_POR_REQUISICAO = 10;

const DEFAULT_LIMITE_FOTOS = 100;
const DEFAULT_LIMITE_BYTES = 25 * 1024 * 1024;

const VELOCIDADE_LABEL = { urgente: "Urgente", economico: "Econômico" } as const;

export function emBlocos<T>(itens: T[], tamanho: number): T[][] {
  const blocos: T[][] = [];
  for (let i = 0; i < itens.length; i += tamanho) blocos.push(itens.slice(i, i + tamanho));
  return blocos;
}

export default function FotosNovo() {
  const { capacidades, showSkeleton, error, refetch } = useCapacidades();
  const { configuracoes, showSkeleton: configuracoesCarregando, error: configuracoesErro } = useConfiguracoes();
  const vel = useVelocidadeLote(capacidades, configuracoes);

  const [passo, setPasso] = useState(1);
  const [codigo, setCodigo] = useState<string | null>(null);
  const [iniciado, setIniciado] = useState<IniciarLoteResposta | null>(null);
  const [arquivos, setArquivos] = useState<File[]>([]);

  const podeCriar = !!capacidades && fotosPermissions.podeCriarLote(capacidades);
  const modeloConfigurado = fotosPermissions.modeloConfigurado(capacidades);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Nova edição de fotos</h1>
        <p className="text-sm text-muted-foreground">Escolha o imóvel, envie as fotos e revise o resultado.</p>
      </div>

      <ol className="flex flex-wrap gap-2" aria-label="Etapas">
        {PASSOS.map((nome, i) => (
          <li
            key={nome}
            aria-current={passo === i + 1 ? "step" : undefined}
            className={
              passo === i + 1
                ? "rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
                : "rounded-full border px-3 py-1 text-xs text-muted-foreground"
            }
          >
            {i + 1}. {nome}
          </li>
        ))}
      </ol>

      {error ? (
        <ErroCapacidades onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <FormSkeleton />
      ) : !podeCriar ? (
        <Card data-testid="imobshotai-sem-permissao">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Lock className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">Seu papel não dá acesso ao ImobShotAI.</p>
          </CardContent>
        </Card>
      ) : !modeloConfigurado ? (
        <Card data-testid="imobshotai-modelo-ausente">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <AlertCircle className="h-10 w-10 text-warning-foreground" />
            <p className="font-medium">Nenhum modelo de edição configurado.</p>
            <p className="text-sm text-muted-foreground">Peça a um administrador para escolher um modelo antes de editar fotos.</p>
          </CardContent>
        </Card>
      ) : passo === 1 || !iniciado ? (
        <PassoImovel
          codigo={codigo}
          onCodigo={setCodigo}
          velocidadeField={
            <VelocidadeField
              velocidade={vel.velocidade}
              onChange={vel.escolher}
              carregando={configuracoesCarregando}
              economicoDisponivel={vel.economicoDisponivel}
              economicoBloqueadoMotivo={vel.economicoBloqueadoMotivo}
              padraoEconomicoIndisponivel={vel.padraoEconomicoIndisponivel}
              mostrarErroPadrao={!!configuracoesErro && vel.escolhida === null}
            />
          }
          velocidade={vel.velocidade}
          onIniciado={(r) => {
            setIniciado(r);
            setPasso(2);
          }}
        />
      ) : passo === 2 ? (
        <PassoFotos
          iniciado={iniciado}
          arquivos={arquivos}
          setArquivos={setArquivos}
          limiteFotos={fotosPermissions.limiteFotosPorLote(capacidades) ?? DEFAULT_LIMITE_FOTOS}
          limiteBytes={fotosPermissions.limiteBytesPorFoto(capacidades) ?? DEFAULT_LIMITE_BYTES}
          onContinuar={() => setPasso(3)}
        />
      ) : passo === 3 ? (
        <PassoEstilo iniciado={iniciado} onVoltar={() => setPasso(2)} onContinuar={() => setPasso(4)} />
      ) : passo === 4 ? (
        <PassoEnviar iniciado={iniciado} onRevisar={() => setPasso(5)} />
      ) : passo === 5 ? (
        <PassoRevisao iniciado={iniciado} onConcluir={() => setPasso(6)} />
      ) : (
        <PassoPronto iniciado={iniciado} />
      )}
    </div>
  );
}

// ─── 1 · Imóvel ────────────────────────────────────────────────────────────

function PassoImovel({
  codigo,
  onCodigo,
  velocidadeField,
  velocidade,
  onIniciado,
}: {
  codigo: string | null;
  onCodigo: (c: string | null) => void;
  velocidadeField: React.ReactNode;
  velocidade: "urgente" | "economico" | null;
  onIniciado: (r: IniciarLoteResposta) => void;
}) {
  const iniciar = useIniciarImobLote();

  async function handleIniciar() {
    if (!codigo || !velocidade) return;
    try {
      onIniciado(await iniciar.mutateAsync({ imovel_codigo: codigo, velocidade }));
    } catch (err) {
      toast.error(mensagemImobShotAI(err, "Não foi possível iniciar a edição."));
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-6 p-6">
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Imóvel</p>
          <ImovelCodigoPicker value={codigo} onChange={onCodigo} somenteSelecao disabled={iniciar.isPending} id="imobshotai-imovel" />
        </div>
        {codigo && velocidadeField}
        <Button onClick={handleIniciar} disabled={!codigo || !velocidade || iniciar.isPending}>
          {iniciar.isPending ? "Iniciando…" : "Continuar"}
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── 2 · Fotos ─────────────────────────────────────────────────────────────

function PassoFotos({
  iniciado,
  arquivos,
  setArquivos,
  limiteFotos,
  limiteBytes,
  onContinuar,
}: {
  iniciado: IniciarLoteResposta;
  arquivos: File[];
  setArquivos: React.Dispatch<React.SetStateAction<File[]>>;
  limiteFotos: number;
  limiteBytes: number;
  onContinuar: () => void;
}) {
  const loteId = iniciado.lote.id;
  const upload = useUploadFotos();
  const vista = useLoteVista();
  const progresso = useImobLoteProgresso(loteId);
  const ocupado = upload.isPending || vista.isPending;
  const excede = arquivos.length > limiteFotos || arquivos.some((f) => f.size > limiteBytes);

  async function enviar() {
    try {
      for (const bloco of emBlocos(arquivos, MAX_ARQUIVOS_POR_REQUISICAO)) {
        await upload.mutateAsync({ loteId, files: bloco });
      }
      setArquivos([]);
      toast.success("Fotos enviadas.");
    } catch (err) {
      toast.error(mensagemImobShotAI(err, "Não foi possível enviar as fotos."));
    }
  }

  async function puxarDoVista() {
    try {
      await vista.mutateAsync({ loteId, body: { codigo: iniciado.card.imovel.codigo } });
      toast.success("Fotos do Vista importadas.");
    } catch (err) {
      toast.error(mensagemImobShotAI(err, "Não foi possível puxar as fotos do Vista."));
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-6 p-6">
        <p className="text-sm text-muted-foreground">
          Imóvel <span className="font-medium tabular-nums text-foreground">{iniciado.card.imovel.codigo}</span>
        </p>
        <UploadFotosField
          arquivos={arquivos}
          onAdicionar={(files) => files && setArquivos((prev) => [...prev, ...Array.from(files)])}
          onRemover={(i) => setArquivos((prev) => prev.filter((_, idx) => idx !== i))}
          limiteFotos={limiteFotos}
          limiteBytes={limiteBytes}
          disabled={ocupado}
        />
        <div className="flex flex-wrap gap-2">
          <Button onClick={enviar} disabled={arquivos.length === 0 || excede || ocupado}>
            <Upload className="h-4 w-4" />
            {upload.isPending ? "Enviando…" : "Enviar fotos"}
          </Button>
          <Button variant="outline" onClick={puxarDoVista} disabled={ocupado}>
            {vista.isPending ? "Buscando no Vista…" : "Puxar fotos do Vista"}
          </Button>
        </div>
        <p className="text-sm" role="status" data-testid="imobshotai-total-fotos">
          {progresso.totalFotos} foto(s) neste lote.
        </p>
        <Button onClick={onContinuar} disabled={progresso.totalFotos === 0 || ocupado}>
          Continuar
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── 3 · Estilo ────────────────────────────────────────────────────────────

function PassoEstilo({
  iniciado,
  onVoltar,
  onContinuar,
}: {
  iniciado: IniciarLoteResposta;
  onVoltar: () => void;
  onContinuar: () => void;
}) {
  const guia = useGuiaEfetivo({ pageSize: 1 });
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <p className="text-sm">
          Velocidade deste lote:{" "}
          <span className="font-medium">{VELOCIDADE_LABEL[iniciado.lote.velocidade] ?? iniciado.lote.velocidade}</span>
        </p>
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Guia de estilo da organização</p>
          {guia.error ? (
            <p role="alert" className="text-sm text-destructive">
              Não foi possível carregar o guia de estilo.
            </p>
          ) : guia.showSkeleton ? (
            <Skeleton className="h-24 w-full" />
          ) : guia.atual ? (
            <pre
              className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-xs"
              data-testid="imobshotai-guia"
            >
              {guia.atual.texto}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">Nenhum guia de estilo ativo — as fotos serão editadas com o padrão do modelo.</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onVoltar}>
            Voltar
          </Button>
          <Button onClick={onContinuar}>Continuar</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── 4 · Enviar ────────────────────────────────────────────────────────────

function PassoEnviar({ iniciado, onRevisar }: { iniciado: IniciarLoteResposta; onRevisar: () => void }) {
  const [submetido, setSubmetido] = useState(false);
  const submeter = useSubmeterLoteImob();
  const progresso = useImobLoteProgresso(iniciado.lote.id, { enabled: submetido });

  async function enviar() {
    try {
      await submeter.mutateAsync(iniciado.lote.id);
      setSubmetido(true);
    } catch (err) {
      toast.error(mensagemImobShotAI(err, "Não foi possível enviar o lote para edição."));
    }
  }

  const concluido = submetido && !progresso.showSkeleton && progresso.totalFotos > 0 && progresso.emAndamento === 0;

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        {!submetido ? (
          <Button onClick={enviar} disabled={submeter.isPending}>
            {submeter.isPending ? "Enviando…" : "Enviar para edição"}
          </Button>
        ) : progresso.error && !progresso.lote ? (
          <p role="alert" className="text-sm text-destructive">
            Não foi possível acompanhar o progresso.{" "}
            <button type="button" className="underline" onClick={() => progresso.refetch()}>
              Tentar novamente
            </button>
          </p>
        ) : (
          <div role="status" aria-live="polite" data-testid="imobshotai-progresso">
            {concluido ? (
              <p className="flex items-center gap-2 text-sm font-medium">
                <Check className="h-4 w-4" /> Edição concluída para {progresso.totalFotos} foto(s).
              </p>
            ) : (
              <p className="text-sm">
                Editando… {progresso.totalFotos - progresso.emAndamento} de {progresso.totalFotos} foto(s) prontas.
              </p>
            )}
          </div>
        )}
        {submetido && (
          <Button onClick={onRevisar} disabled={!concluido}>
            Ir para a revisão
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ─── 5 · Revisão ───────────────────────────────────────────────────────────

function PassoRevisao({ iniciado, onConcluir }: { iniciado: IniciarLoteResposta; onConcluir: () => void }) {
  const admin = useIsOrgAdmin();
  const refrescar = useRefrescarCards();
  return (
    <div className="space-y-4">
      <RevisaoLote loteId={iniciado.lote.id} podeDecidir={admin} onDecisaoSalva={refrescar} />
      <div className="flex justify-end">
        <Button onClick={onConcluir}>Concluir</Button>
      </div>
    </div>
  );
}

// ─── 6 · Pronto ────────────────────────────────────────────────────────────

function PassoPronto({ iniciado }: { iniciado: IniciarLoteResposta }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <Check className="h-10 w-10 text-success" />
        <p className="font-medium">Pronto! As fotos de {iniciado.card.imovel.codigo} estão no ImobShotAI.</p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button asChild>
            <Link to={`/imobshotai/imoveis/${iniciado.card.id}`}>Ver o imóvel</Link>
          </Button>
          <Button variant="outline" disabled title="Em breve">
            Criar vídeo (em breve)
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function FormSkeleton() {
  return (
    <Card data-testid="imobshotai-funil-loading">
      <CardContent className="flex flex-col gap-4 p-6">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-9 w-32" />
      </CardContent>
    </Card>
  );
}

function ErroCapacidades({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center" role="alert">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar as permissões para editar fotos.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
