/**
 * RoteiroEditorDialog — the ONE editor for a roteiro DRAFT (roteiro-ciclo
 * CONTRACT §5; mockup `02-roteiro-ciclo-de-vida`, rodada 2). It replaces the
 * create-only `CriarRoteiroDialog`.
 *
 * Every edit saves (`useRoteiroRascunho`): the draft is created on the first
 * imóvel or the date, then autosaved; closing never loses it, and the list
 * shows it with "Continuar editando". "Gerar roteiro" (confirmation first)
 * consolidates it — afterwards the card's Roteiros tab owns the gerado view.
 *
 * 🔴 RENDERED FROM THE SERVER'S `permissoes` — `gerar` / `motivo_gerar` /
 * `editar_imoveis` are never re-derived here.
 *
 * ACCESSIBILITY (WCAG 2.2 AA; NOTES F6/F7): reordering is ↑/↓ BUTTONS (the
 * first ↑ and the last ↓ are disabled with a reason in their label) plus an
 * `aria-live` announcement of the new position — no drag-only control (SC
 * 2.5.7). Saved/saving is a polite live region; "Não salvo" is an alert (SC
 * 4.1.3). The confirmations are Radix alert dialogs (focus in / trap / return).
 *
 * NOT the seed's `MultiSelectPopover` (`noc-organ-consume-check`, run first):
 * the imóvel search is a debounced live-fetch typeahead over an unbounded
 * result set whose picks are ORDERED; the only overlap is "a popover under a
 * field".
 *
 * Presentational-with-its-own-hook (the same seam the old dialog used): the
 * caller owns the toast on `onGerado`.
 */
import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Check, Loader2, Route, Search, Trash2, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useImoveisBusca } from "@/hooks/useCardHub";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useRoteiroRascunho } from "@/hooks/useRoteiroRascunho";
import { toastServerError } from "@/lib/erroServidor";
import { avisarFunilRecusado } from "@/lib/funilAviso";
import { dataVisitaBR, salvoHa } from "@/lib/roteiroLabels";
import type { ImovelVisita, Roteiro } from "@/types/cardHub";

import { HorarioVisita } from "./HorarioVisita";
import { enderecoDoImovel } from "./ImovelVisitaCard";

export interface RoteiroEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clienteId: string;
  /** The atendimento the roteiro belongs to (omit and pass `atendimentoOpcoes` when it is ambiguous). */
  atendimentoId?: string | null;
  /** More than one open atendimento ⇒ the user must say which one (else 409 `AmbiguousAtendimento`). */
  atendimentoOpcoes?: { id: string; titulo: string }[];
  /** "Continuar editando": reopen this draft. Absent ⇒ a new draft. */
  roteiroId?: string | null;
  /** The imóveis the draft opens with (interest list → "Gerar roteiro"); created at once, in order. */
  inicial?: ImovelVisita[];
  /** After R8 succeeded — the caller may navigate / toast. The editor closes itself. */
  onGerado?: (roteiro: Roteiro) => void;
}

/** The dialog mounts its engine only while open: a fresh draft state per open. */
export function RoteiroEditorDialog(props: RoteiroEditorDialogProps) {
  if (!props.open) return null;
  return <Editor {...props} />;
}

function Editor({
  onOpenChange,
  clienteId,
  atendimentoId,
  atendimentoOpcoes,
  roteiroId: roteiroIdInicial,
  inicial,
  onGerado,
}: RoteiroEditorDialogProps) {
  const precisaAtendimento = !atendimentoId && (atendimentoOpcoes?.length ?? 0) > 1;
  const [atendimentoEscolhido, setAtendimentoEscolhido] = useState("");
  const atendimentoResolvido = atendimentoId ?? (atendimentoEscolhido || null);
  const podeCriar = !precisaAtendimento || atendimentoEscolhido !== "";

  const r = useRoteiroRascunho({
    clienteId,
    roteiroId: roteiroIdInicial,
    atendimentoId: atendimentoResolvido,
    podeCriar,
    inicial,
  });
  const { roteiro, campos, estado } = r;
  const permissoes = roteiro?.permissoes;
  const visitas = roteiro?.visitas ?? [];
  // `editar_imoveis` is the server's word; before the draft exists the list is empty and editable.
  const editaImoveis = permissoes ? permissoes.editar_imoveis : true;

  const [confirmaGerar, setConfirmaGerar] = useState(false);
  const [confirmaExcluir, setConfirmaExcluir] = useState(false);
  const [guardaFechar, setGuardaFechar] = useState(false);

  async function fechar() {
    // Flush any debounced edit first: closing never loses a draft.
    await r.aguardar();
    if (r.temFalha()) {
      setGuardaFechar(true);
      return;
    }
    onOpenChange(false);
  }

  async function gerar() {
    try {
      const gerado = await r.gerar();
      setConfirmaGerar(false);
      toast.success("Roteiro gerado.");
      avisarFunilRecusado(gerado.funil);
      onGerado?.(gerado);
      onOpenChange(false);
    } catch (err) {
      setConfirmaGerar(false);
      toastServerError(err, "Não foi possível gerar o roteiro.");
    }
  }

  async function excluir() {
    try {
      await r.excluir();
      setConfirmaExcluir(false);
      onOpenChange(false);
    } catch (err) {
      setConfirmaExcluir(false);
      toastServerError(err, "Não foi possível excluir o rascunho.");
    }
  }

  const salvo = estado.tipo === "salvo";
  const podeGerar = !!permissoes?.gerar && salvo && !r.gerando;
  const dataInvalida = !!roteiro && !campos.data && !!permissoes?.motivo_gerar;

  return (
    <>
      <Dialog open onOpenChange={(aberto) => !aberto && void fechar()}>
        <DialogContent
          className="max-h-[92vh] max-w-2xl overflow-y-auto"
          data-testid="roteiro-editor"
        >
          <DialogHeader>
            <DialogTitle>{roteiro?.titulo || "Roteiro"}</DialogTitle>
            <DialogDescription>
              Tudo é salvo automaticamente. Você pode fechar e continuar depois. Quando a lista
              estiver pronta, clique em “Gerar roteiro”.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="rounded-full bg-warning-light px-2 py-0.5 text-xs font-medium text-warning-foreground"
                data-testid="roteiro-status-chip"
              >
                Rascunho
              </span>
              <IndicadorSalvamento estado={estado} existe={!!roteiro} />
            </div>
            {roteiro && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setConfirmaExcluir(true)}
                aria-label="Excluir rascunho"
                data-testid="roteiro-excluir-rascunho"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>

          {estado.tipo === "erro" && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/50 bg-danger-light p-3 text-sm"
              data-testid="roteiro-erro-banner"
            >
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
              <div className="space-y-2">
                <p>
                  <b>Sua última alteração não foi salva.</b> {estado.mensagem} O que você digitou
                  continua aqui.
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={r.tentarDeNovo}
                  data-testid="roteiro-tentar-de-novo"
                >
                  Tentar de novo
                </Button>
              </div>
            </div>
          )}

          {r.carregando ? (
            <div className="space-y-2" data-testid="roteiro-editor-carregando">
              <div className="h-10 animate-pulse rounded-md bg-muted" />
              <div className="h-20 animate-pulse rounded-lg bg-muted" />
            </div>
          ) : r.naoEncontrado || r.erroAoCarregar ? (
            <p className="text-sm text-destructive" role="alert" data-testid="roteiro-editor-indisponivel">
              {r.naoEncontrado
                ? "Este rascunho não existe mais. Feche e crie um novo roteiro."
                : "Não foi possível carregar o rascunho. Feche e tente de novo."}
            </p>
          ) : (
            <div className="space-y-4">
              {precisaAtendimento && (
                <div>
                  <label
                    className="mb-1 block text-xs font-medium text-muted-foreground"
                    htmlFor="roteiro-atendimento"
                  >
                    Atendimento *
                  </label>
                  <select
                    id="roteiro-atendimento"
                    value={atendimentoEscolhido}
                    onChange={(e) => setAtendimentoEscolhido(e.target.value)}
                    disabled={!!roteiro}
                    className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                    data-testid="roteiro-atendimento"
                  >
                    <option value="">Selecione…</option>
                    {atendimentoOpcoes?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.titulo}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label
                    className="mb-1 block text-xs font-medium text-muted-foreground"
                    htmlFor="roteiro-data-visita"
                  >
                    Data da visita *
                  </label>
                  <Input
                    id="roteiro-data-visita"
                    type="date"
                    required
                    value={campos.data}
                    onChange={(e) => r.editarCampo("data", e.target.value)}
                    aria-invalid={dataInvalida || undefined}
                    aria-describedby={dataInvalida ? "roteiro-motivo-gerar" : undefined}
                    data-testid="roteiro-data-visita"
                  />
                </div>
                <div>
                  <label
                    className="mb-1 block text-xs font-medium text-muted-foreground"
                    htmlFor="roteiro-hora-visita"
                  >
                    Horário (opcional)
                  </label>
                  <Input
                    id="roteiro-hora-visita"
                    type="time"
                    value={campos.hora}
                    onChange={(e) => r.editarCampo("hora", e.target.value)}
                    data-testid="roteiro-hora-visita"
                  />
                </div>
                <div className="min-w-[180px] flex-1">
                  <label
                    className="mb-1 block text-xs font-medium text-muted-foreground"
                    htmlFor="roteiro-titulo"
                  >
                    Título (opcional)
                  </label>
                  <Input
                    id="roteiro-titulo"
                    value={campos.titulo}
                    onChange={(e) => r.editarCampo("titulo", e.target.value)}
                    placeholder="Terça de manhã"
                    data-testid="roteiro-titulo"
                  />
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">
                    Imóveis <span className="font-normal text-muted-foreground">({visitas.length})</span>
                  </h3>
                  {visitas.length > 1 && editaImoveis && (
                    <span className="text-xs text-muted-foreground">
                      Use as setas para mudar a ordem
                    </span>
                  )}
                </div>

                {/* F6 — the ↑/↓ buttons ARE the reorder control; this region says where it landed. */}
                <p className="sr-only" aria-live="polite" data-testid="roteiro-ordem-live">
                  {r.anuncio}
                </p>

                {visitas.length === 0 ? (
                  <p
                    className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground"
                    data-testid="roteiro-lista-vazia"
                  >
                    Nenhum imóvel adicionado ainda.
                  </p>
                ) : (
                  <ol
                    className="divide-y rounded-lg border"
                    aria-label="Imóveis do roteiro (rascunho)"
                    data-testid="roteiro-lista"
                  >
                    {visitas.map((v, i) => (
                      <LinhaImovel
                        key={v.id}
                        codigo={v.codigo}
                        imovel={v.imovel}
                        posicao={i + 1}
                        total={visitas.length}
                        editavel={editaImoveis}
                        horario={v.horario}
                        onHorario={(valor) => r.horario(v.id, v.codigo, valor)}
                        onMover={(delta) => r.mover(v.id, delta)}
                        onRemover={() => r.remover(v.id, v.codigo)}
                        id={v.id}
                      />
                    ))}
                  </ol>
                )}

                {editaImoveis && (
                  <BuscaImovel
                    desabilitada={!podeCriar}
                    jaNoRoteiro={visitas.map((v) => v.codigo.toUpperCase())}
                    onAdicionar={(codigo) => r.adicionar(codigo)}
                  />
                )}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
            <p
              id="roteiro-motivo-gerar"
              className={
                estado.tipo === "erro" || (permissoes && !permissoes.gerar)
                  ? "text-xs text-destructive"
                  : "text-xs text-muted-foreground"
              }
              data-testid="roteiro-gerar-motivo"
            >
              {estado.tipo === "erro"
                ? "Salve antes de gerar."
                : !roteiro
                  ? "Adicione um imóvel ou informe a data da visita para criar o rascunho."
                  : permissoes && !permissoes.gerar
                    ? (permissoes.motivo_gerar ?? "Este roteiro ainda não pode ser gerado.")
                    : `Pronto para gerar: ${visitas.length} ${visitas.length === 1 ? "imóvel" : "imóveis"}.`}
            </p>
            <Button
              onClick={() => setConfirmaGerar(true)}
              disabled={!podeGerar}
              aria-describedby="roteiro-motivo-gerar"
              data-testid="roteiro-gerar-roteiro"
            >
              {r.gerando ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Route className="mr-2 h-4 w-4" />
              )}
              Gerar roteiro
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmaGerar} onOpenChange={setConfirmaGerar}>
        <AlertDialogContent data-testid="roteiro-confirmar-gerar">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {campos.data
                ? `Gerar o roteiro de ${dataVisitaBR(campos.data)}?`
                : "Gerar o roteiro?"}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  Depois de gerado, <b>não será possível adicionar nem remover imóveis</b> (
                  {visitas.length} {visitas.length === 1 ? "imóvel" : "imóveis"}, nesta ordem).
                </p>
                <p>
                  Horários, resultados, cancelamentos e observações continuam editáveis. Só um
                  gestor pode reabrir, e só antes do primeiro resultado.
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="outline" onClick={() => setConfirmaGerar(false)}>
              Continuar editando
            </Button>
            <Button onClick={() => void gerar()} disabled={r.gerando} data-testid="roteiro-confirmar-gerar-ok">
              {r.gerando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Gerar roteiro
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={guardaFechar} onOpenChange={setGuardaFechar}>
        <AlertDialogContent data-testid="roteiro-guarda-fechar">
          <AlertDialogHeader>
            <AlertDialogTitle>Há uma alteração que não foi salva</AlertDialogTitle>
            <AlertDialogDescription>
              A última alteração ainda não chegou ao servidor. Se fechar agora, essa alteração se
              perde; o resto do rascunho já está salvo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setGuardaFechar(false);
                onOpenChange(false);
              }}
              data-testid="roteiro-fechar-mesmo-assim"
            >
              Fechar mesmo assim
            </Button>
            <Button
              onClick={() => {
                setGuardaFechar(false);
                r.tentarDeNovo();
              }}
              data-testid="roteiro-guarda-tentar"
            >
              Tentar salvar de novo
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmaExcluir} onOpenChange={setConfirmaExcluir}>
        <AlertDialogContent data-testid="roteiro-confirmar-excluir">
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir este rascunho?</AlertDialogTitle>
            <AlertDialogDescription>
              O rascunho e a lista de imóveis serão removidos. Isso não pode ser desfeito.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="outline" onClick={() => setConfirmaExcluir(false)}>
              Manter rascunho
            </Button>
            <Button variant="destructive" onClick={() => void excluir()}>
              Excluir
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/** Saving / saved / unsaved — the polite live region and the alert never overlap. */
function IndicadorSalvamento({
  estado,
  existe,
}: {
  estado: ReturnType<typeof useRoteiroRascunho>["estado"];
  /** The draft exists on the server — "Salvo" even when the time of the last save is unknown. */
  existe: boolean;
}) {
  const [agora, setAgora] = useState(() => Date.now());
  const em = estado.tipo === "salvo" ? estado.em : null;
  useEffect(() => {
    if (em === null) return;
    setAgora(Date.now());
    // poll-budget: 5s; 0 calls/tick (relative "salvo há" clock); worst 0/day per open tab; hidden=runs
    const t = setInterval(() => setAgora(Date.now()), 5000);
    return () => clearInterval(t);
  }, [em]);

  if (estado.tipo === "erro") {
    return (
      <span
        role="alert"
        className="inline-flex items-center gap-1 text-xs font-semibold text-destructive"
        data-testid="roteiro-salvamento"
      >
        <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
        Não salvo
      </span>
    );
  }
  return (
    <span
      aria-live="polite"
      className="inline-flex items-center gap-1 text-xs text-muted-foreground"
      data-testid="roteiro-salvamento"
    >
      {estado.tipo === "salvando" ? (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          Salvando…
        </>
      ) : em !== null ? (
        <>
          <Check className="h-3.5 w-3.5" aria-hidden />
          {salvoHa(em, agora)}
        </>
      ) : existe ? (
        <>
          <Check className="h-3.5 w-3.5" aria-hidden />
          Salvo
        </>
      ) : (
        "Ainda não salvo"
      )}
    </span>
  );
}

function LinhaImovel({
  id,
  codigo,
  imovel,
  posicao,
  total,
  editavel,
  horario,
  onHorario,
  onMover,
  onRemover,
}: {
  id: string;
  codigo: string;
  imovel: ImovelVisita | null;
  posicao: number;
  total: number;
  editavel: boolean;
  horario: string | null;
  onHorario: (valor: string | null) => void;
  onMover: (delta: -1 | 1) => void;
  onRemover: () => void;
}) {
  const primeiro = posicao === 1;
  const ultimo = posicao === total;
  const endereco = imovel ? enderecoDoImovel(imovel) : null;
  return (
    <li className="flex items-center gap-3 px-3 py-2" data-testid={`roteiro-linha-${codigo}`}>
      {editavel && (
        <div className="flex flex-col gap-0.5">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-6 w-7"
            disabled={primeiro}
            onClick={() => onMover(-1)}
            aria-label={
              primeiro ? `Mover ${codigo} para cima (já é o 1º)` : `Mover ${codigo} para cima`
            }
            data-testid={`roteiro-subir-${codigo}`}
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-6 w-7"
            disabled={ultimo}
            onClick={() => onMover(1)}
            aria-label={
              ultimo ? `Mover ${codigo} para baixo (já é o último)` : `Mover ${codigo} para baixo`
            }
            data-testid={`roteiro-descer-${codigo}`}
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
      <span
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground"
        aria-hidden
      >
        {posicao}
      </span>
      <div className="min-w-0 flex-1" data-testid={`roteiro-visita-${id}`}>
        <p className="truncate text-sm">
          <b>{codigo}</b>
          {imovel?.titulo ? ` · ${imovel.titulo}` : ""}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {[endereco ?? imovel?.empreendimento].filter(Boolean).join(" ") || "—"}
        </p>
      </div>
      <HorarioVisita codigo={codigo} horario={horario} onSalvar={onHorario} />
      {editavel && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={onRemover}
          aria-label={`Remover ${codigo} do roteiro`}
          data-testid={`roteiro-remover-${codigo}`}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      )}
    </li>
  );
}

/** The live imóvel search (`GET /api/imoveis/busca`, registry ∪ mirror) — see `useImoveisBusca`. */
function BuscaImovel({
  desabilitada,
  jaNoRoteiro,
  onAdicionar,
}: {
  desabilitada: boolean;
  jaNoRoteiro: string[];
  onAdicionar: (codigo: string) => void;
}) {
  const [termo, setTermo] = useState("");
  const termoDebounced = useDebouncedValue(termo, 250);
  const busca = useImoveisBusca(termoDebounced);
  const ja = useMemo(() => new Set(jaNoRoteiro), [jaNoRoteiro]);

  // 🔴 `isPending || isFetching`, never `isLoading` (v5's is false during a
  // background refetch). `keepPreviousData` keeps the last term's rows on
  // screen, so `resultados` is only truly empty when nothing matched yet.
  const buscando = busca.isPending || busca.isFetching;
  const termoUtil = termoDebounced.trim().length >= 2;
  const resultados = busca.data?.items ?? [];

  function adicionar(codigo: string) {
    if (ja.has(codigo.toUpperCase())) return;
    onAdicionar(codigo);
    // The field clears: a corretor adding three imóveis types three refs in a row.
    setTermo("");
  }

  return (
    <div className="relative mt-3">
      <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="roteiro-busca">
        Adicionar imóvel
      </label>
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
        <Input
          id="roteiro-busca"
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          placeholder="Buscar imóvel por código, bairro ou condomínio"
          className="pl-8"
          autoComplete="off"
          disabled={desabilitada}
          data-testid="roteiro-busca"
        />
      </div>
      {desabilitada && (
        <p className="mt-1 text-xs text-muted-foreground">Escolha o atendimento primeiro.</p>
      )}

      {termo.trim().length > 0 && (
        <div
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border bg-popover shadow-md"
          data-testid="roteiro-busca-popover"
        >
          {!termoUtil ? (
            <p className="px-3 py-2 text-sm text-muted-foreground">Digite ao menos 2 caracteres.</p>
          ) : busca.isError ? (
            <p className="px-3 py-2 text-sm text-destructive" data-testid="roteiro-busca-erro">
              Não foi possível buscar os imóveis.
            </p>
          ) : resultados.length === 0 ? (
            buscando ? (
              <p
                className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
                data-testid="roteiro-busca-carregando"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando...
              </p>
            ) : (
              <p className="px-3 py-2 text-sm text-muted-foreground" data-testid="roteiro-busca-vazio">
                Nenhum imóvel encontrado para “{termoDebounced.trim()}”.
              </p>
            )
          ) : (
            <>
              {buscando && (
                <p
                  className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground"
                  data-testid="roteiro-busca-carregando"
                >
                  <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
                </p>
              )}
              <ul>
                {resultados.map((row) => {
                  const jaEsta = ja.has(row.codigo.toUpperCase());
                  return (
                    <li key={row.codigo}>
                      <button
                        type="button"
                        disabled={jaEsta}
                        onClick={() => adicionar(row.codigo)}
                        className="flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid={`roteiro-busca-item-${row.codigo}`}
                      >
                        <span className="font-semibold">{row.codigo}</span>
                        <span className="truncate text-muted-foreground">
                          {[row.empreendimento ?? row.titulo, row.bairro].filter(Boolean).join(" · ")}
                        </span>
                        {jaEsta && <span className="ml-auto shrink-0 text-xs">já no roteiro</span>}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
