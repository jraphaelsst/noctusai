/**
 * `<CalendarioMes clienteId?/>` — the editorial calendar, reusable.
 *
 * Mounted by the Calendário page (every cliente) and by the Clientes card's
 * Calendário tab (slice F, one cliente — roadmap R9). Owns its own CRUD: new
 * pauta, the copy editor, peças, reschedule, delete.
 *
 * TWO LAYOUTS, ONE DATA SET (R0 mobile-first):
 *  - <640px an AGENDA list — only the days that have pautas, in order. A
 *    7-column month grid at 390px is ~50px per day: unreadable, untappable.
 *  - ≥640px the month GRID with weekday headers and the leading offset (smoke
 *    finding 6: day 1 used to sit in the first column whatever its weekday).
 *    Rescheduling there is native HTML5 drag-and-drop onto a day cell; the
 *    editor's date field does the same everywhere (touch, keyboard).
 *
 * Pautas generated from an accepted orçamento (`gerada_automaticamente`) carry
 * an "auto" badge so contract-planned content is distinguishable from
 * hand-planned content.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Dialog,
  DialogBody,
  DialogHeader,
  Input,
  Skeleton,
} from "@noctusai/lib/design-system";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  FileImage,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import { useClientes } from "@/hooks/useClientes";
import {
  FORMATOS,
  FUNIL_LABEL,
  FUNIS,
  useAtualizarPauta,
  useCalendario,
  useCriarPauta,
  useEnviarPeca,
  usePecas,
  useRemoverPauta,
  type Formato,
  type Funil,
  type Pauta,
} from "@/hooks/usePautas";
import { SHEET_MOBILE } from "@/lib/mobileSheet";
import { celulasDoMes, DIAS_SEMANA_CURTOS, isoLocal } from "./grade";

/** Instagram's caption cap — the practical ceiling for a legenda. */
const LIMITE_LEGENDA = 2200;

export interface CalendarioMesProps {
  /** Show (and create) only this cliente's pautas. */
  clienteId?: string;
  className?: string;
}

function mensagemDe(erro: unknown, padrao: string): string {
  return erro instanceof Error && erro.message ? erro.message : padrao;
}

/** Publication moment for a picked day — 09:00 local, the agency's default slot. */
function publicacaoNoDia(ano: number, mes: number, dia: number): string {
  return new Date(ano, mes, dia, 9, 0, 0).toISOString();
}

function SeloAuto({ compacto = false }: { compacto?: boolean }) {
  return compacto ? (
    <Sparkles className="h-3 w-3 shrink-0 text-primary" aria-label="Gerada do orçamento" />
  ) : (
    <Badge variant="outline" className="gap-1 px-1.5 py-0 text-[10px]">
      <Sparkles className="h-3 w-3" />
      auto
    </Badge>
  );
}

export function CalendarioMes({ clienteId, className }: CalendarioMesProps) {
  const [mes, setMes] = useState(() => {
    const hoje = new Date();
    return new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  });
  const [selecionadaId, setSelecionadaId] = useState<string | null>(null);

  const ano = mes.getFullYear();
  const m = mes.getMonth();
  const inicio = `${isoLocal(new Date(ano, m, 1))}T00:00:00`;
  const fim = `${isoLocal(new Date(ano, m + 1, 0))}T23:59:59`;
  const { itens, loading, error } = useCalendario(inicio, fim, clienteId);

  const { clientes } = useClientes();
  const criar = useCriarPauta();
  const atualizar = useAtualizarPauta();
  const remover = useRemoverPauta();

  const [novoTitulo, setNovoTitulo] = useState("");
  const [novoCliente, setNovoCliente] = useState("");
  const [novaData, setNovaData] = useState("");

  /** Pautas bucketed by day-of-month (local time). */
  const porDia = useMemo(() => {
    const mapa = new Map<number, Pauta[]>();
    for (const p of itens) {
      if (!p.data_publicacao) continue;
      const dia = new Date(p.data_publicacao).getDate();
      mapa.set(dia, [...(mapa.get(dia) ?? []), p]);
    }
    return mapa;
  }, [itens]);

  const celulas = useMemo(() => celulasDoMes(ano, m), [ano, m]);
  const diasComPauta = useMemo(() => [...porDia.keys()].sort((a, b) => a - b), [porDia]);
  const hoje = new Date();
  const ehHoje = (dia: number) =>
    hoje.getFullYear() === ano && hoje.getMonth() === m && hoje.getDate() === dia;

  // The open pauta is looked up by id in the CURRENT data, so the editor
  // reflects a save (or a reschedule out of the month) instead of a snapshot.
  const selecionada = itens.find((p) => p.id === selecionadaId) ?? null;
  const rotuloMes = mes.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  const clienteAlvo = clienteId ?? novoCliente;

  function reagendar(pautaId: string, dia: number) {
    atualizar.mutate(
      { id: pautaId, data_publicacao: publicacaoNoDia(ano, m, dia) },
      { onError: (e) => toast.error(mensagemDe(e, "Não foi possível reagendar.")) },
    );
  }

  function criarPauta(e: React.FormEvent) {
    e.preventDefault();
    const titulo = novoTitulo.trim();
    if (!titulo || !clienteAlvo) return;
    const data = novaData
      ? new Date(`${novaData}T09:00:00`).toISOString()
      : publicacaoNoDia(ano, m, 1);
    criar.mutate(
      { cliente_id: clienteAlvo, titulo, data_publicacao: data },
      {
        onSuccess: () => {
          setNovoTitulo("");
          setNovaData("");
        },
        onError: (erro) => toast.error(mensagemDe(erro, "Não foi possível criar a pauta.")),
      },
    );
  }

  const chip = (pauta: Pauta) => (
    <button
      type="button"
      draggable
      onDragStart={(e) => e.dataTransfer.setData("text/plain", pauta.id)}
      onClick={() => setSelecionadaId(pauta.id)}
      className="flex w-full items-center gap-1 truncate rounded bg-muted px-1 py-0.5 text-left text-[11px] text-foreground hover:bg-border"
      title={pauta.titulo}
    >
      {pauta.gerada_automaticamente && <SeloAuto compacto />}
      <span className="min-w-0 truncate">{pauta.titulo}</span>
    </button>
  );

  return (
    <div className={`min-w-0 space-y-4 ${className ?? ""}`} data-testid="calendario-mes">
      {/* ── Month navigation ─────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-2 sm:justify-end">
        <Button
          variant="outline"
          size="sm"
          className="min-h-10"
          aria-label="Mês anterior"
          onClick={() => setMes(new Date(ano, m - 1, 1))}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-[160px] text-center text-sm capitalize text-foreground">
          {rotuloMes}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="min-h-10"
          aria-label="Próximo mês"
          onClick={() => setMes(new Date(ano, m + 1, 1))}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* ── Nova pauta ───────────────────────────────────────────── */}
      <form
        className="grid grid-cols-1 gap-2 rounded-lg border border-border bg-card p-3 sm:flex sm:flex-wrap sm:items-end sm:p-4"
        onSubmit={criarPauta}
      >
        {!clienteId && (
          <select
            aria-label="Cliente"
            value={novoCliente}
            onChange={(e) => setNovoCliente(e.target.value)}
            className="h-11 rounded-md border border-border bg-card px-3 text-sm text-foreground"
          >
            <option value="">Cliente…</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>{c.nome}</option>
            ))}
          </select>
        )}
        <Input
          aria-label="Título da pauta"
          value={novoTitulo}
          onChange={(e) => setNovoTitulo(e.target.value)}
          placeholder="Post institucional"
          className="h-11 min-w-0 sm:min-w-[200px] sm:flex-1"
        />
        <Input
          aria-label="Data de publicação"
          type="date"
          value={novaData}
          onChange={(e) => setNovaData(e.target.value)}
          className="h-11 sm:w-44"
        />
        <Button
          type="submit"
          className="min-h-11"
          disabled={!novoTitulo.trim() || !clienteAlvo || criar.isPending}
        >
          <Plus className="mr-2 h-4 w-4" />
          Adicionar
        </Button>
      </form>

      {error ? (
        <p className="rounded-lg border border-border bg-card p-4 text-sm text-destructive">
          Não foi possível carregar o calendário.
        </p>
      ) : loading ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <>
          {/* ── Agenda (phones) ──────────────────────────────────── */}
          <div className="sm:hidden" data-testid="calendario-agenda">
            {diasComPauta.length === 0 ? (
              <p className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
                <CalendarDays className="mr-2 inline h-4 w-4" />
                Nenhuma pauta agendada em {rotuloMes}.
              </p>
            ) : (
              <ol className="space-y-3">
                {diasComPauta.map((dia) => {
                  const data = new Date(ano, m, dia);
                  return (
                    <li key={dia} className="rounded-lg border border-border bg-card p-3">
                      <p
                        className={`mb-2 text-xs font-semibold capitalize ${
                          ehHoje(dia) ? "text-primary" : "text-muted-foreground"
                        }`}
                      >
                        {data.toLocaleDateString("pt-BR", {
                          weekday: "long",
                          day: "2-digit",
                          month: "2-digit",
                        })}
                        {ehHoje(dia) && " · hoje"}
                      </p>
                      <ul className="space-y-2">
                        {(porDia.get(dia) ?? []).map((pauta) => (
                          <li key={pauta.id}>
                            <button
                              type="button"
                              onClick={() => setSelecionadaId(pauta.id)}
                              className="flex min-h-11 w-full items-center gap-2 rounded-md bg-muted px-3 py-2 text-left text-sm text-foreground"
                            >
                              <span className="min-w-0 flex-1 truncate">{pauta.titulo}</span>
                              {pauta.formato && (
                                <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                                  {pauta.formato}
                                </Badge>
                              )}
                              {pauta.gerada_automaticamente && <SeloAuto />}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>

          {/* ── Month grid (≥640px) ──────────────────────────────── */}
          <div className="hidden sm:block" data-testid="calendario-grade">
            <div className="grid grid-cols-7 gap-1 pb-1" role="row">
              {DIAS_SEMANA_CURTOS.map((d) => (
                <div
                  key={d}
                  role="columnheader"
                  className="text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {celulas.map((dia, i) =>
                dia === null ? (
                  <div key={`vazio-${i}`} aria-hidden className="min-h-[92px] rounded bg-muted/30" />
                ) : (
                  <div
                    key={dia}
                    data-dia={dia}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const id = e.dataTransfer.getData("text/plain");
                      if (id) reagendar(id, dia);
                    }}
                    className={`min-h-[92px] min-w-0 rounded border bg-card p-1 ${
                      ehHoje(dia) ? "border-primary" : "border-border"
                    }`}
                  >
                    <span
                      className={`text-[11px] ${ehHoje(dia) ? "font-semibold text-primary" : "text-muted-foreground"}`}
                    >
                      {dia}
                    </span>
                    <ul className="mt-1 space-y-1">
                      {(porDia.get(dia) ?? []).map((pauta) => (
                        <li key={pauta.id}>{chip(pauta)}</li>
                      ))}
                    </ul>
                  </div>
                ),
              )}
            </div>
            {itens.length === 0 && (
              <p className="mt-3 text-sm text-muted-foreground">
                Nenhuma pauta agendada neste mês.
              </p>
            )}
          </div>
        </>
      )}

      {/* ── Editor ─────────────────────────────────────────────────── */}
      <Dialog
        open={selecionada !== null}
        onClose={() => setSelecionadaId(null)}
        title={selecionada?.titulo}
        className={`sm:max-w-lg ${SHEET_MOBILE}`}
      >
        {selecionada && (
          <EditorPauta
            key={selecionada.id}
            pauta={selecionada}
            onFechar={() => setSelecionadaId(null)}
            onSalvar={(patch) =>
              atualizar.mutate(
                { id: selecionada.id, ...patch },
                { onError: (e) => toast.error(mensagemDe(e, "Não foi possível salvar.")) },
              )
            }
            onRemover={() => {
              remover.mutate(selecionada.id, {
                onError: (e) => toast.error(mensagemDe(e, "Não foi possível remover.")),
              });
              setSelecionadaId(null);
            }}
            salvando={atualizar.isPending}
          />
        )}
      </Dialog>
    </div>
  );
}

function EditorPauta({
  pauta,
  onFechar,
  onSalvar,
  onRemover,
  salvando,
}: {
  pauta: Pauta;
  onFechar: () => void;
  onSalvar: (patch: Partial<Pauta>) => void;
  onRemover: () => void;
  salvando: boolean;
}) {
  const [copy, setCopy] = useState(pauta.copy_texto ?? "");
  const [direcao, setDirecao] = useState(pauta.direcao_video ?? "");
  const [confirmandoRemocao, setConfirmandoRemocao] = useState(false);
  const excedeu = copy.length > LIMITE_LEGENDA;

  return (
    <>
      <DialogHeader>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-foreground">
            {pauta.titulo}
          </h2>
          {pauta.gerada_automaticamente && <SeloAuto />}
        </div>
        <Button variant="ghost" size="sm" onClick={onFechar} aria-label="Fechar editor">
          ×
        </Button>
      </DialogHeader>
      <DialogBody className="space-y-3 max-sm:max-h-none">
        {pauta.gerada_automaticamente && (
          <p className="text-xs text-muted-foreground">
            Gerada automaticamente a partir de um orçamento aceito.
          </p>
        )}
        <div className="flex flex-wrap gap-1">
          {FUNIS.map((f: Funil) => (
            <Button
              key={f}
              size="sm"
              variant={pauta.funil === f ? "primary" : "outline"}
              onClick={() => onSalvar({ funil: f })}
            >
              {FUNIL_LABEL[f]}
            </Button>
          ))}
        </div>

        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">Formato</span>
          <select
            value={pauta.formato ?? ""}
            onChange={(e) => onSalvar({ formato: (e.target.value || null) as Formato | null })}
            className="h-11 w-full rounded border border-border bg-background px-2 text-sm text-foreground"
          >
            <option value="">—</option>
            {FORMATOS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">Data de publicação</span>
          <input
            type="date"
            value={pauta.data_publicacao ? isoLocal(new Date(pauta.data_publicacao)) : ""}
            onChange={(e) =>
              onSalvar({
                // Empty clears the date — the backend accepts explicit null and
                // takes the pauta off the grid.
                data_publicacao: e.target.value
                  ? new Date(`${e.target.value}T09:00:00`).toISOString()
                  : null,
              })
            }
            className="h-11 w-full rounded border border-border bg-background px-2 text-sm text-foreground"
          />
        </label>

        <label className="block">
          <span className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
            Legenda
            <span className={excedeu ? "text-destructive" : undefined}>
              {copy.length} / {LIMITE_LEGENDA}
            </span>
          </span>
          <textarea
            value={copy}
            onChange={(e) => setCopy(e.target.value)}
            rows={8}
            className="w-full rounded border border-border bg-background p-2 text-sm text-foreground"
            placeholder="Escreva a legenda…"
          />
        </label>
        {excedeu && (
          <p className="text-xs text-destructive">
            Acima do limite de {LIMITE_LEGENDA} caracteres do Instagram.
          </p>
        )}

        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">
            Anotações de direção de vídeo
          </span>
          <textarea
            value={direcao}
            onChange={(e) => setDirecao(e.target.value)}
            rows={3}
            className="w-full rounded border border-border bg-background p-2 text-sm text-foreground"
            placeholder="Cortes, trilha, enquadramento…"
          />
        </label>

        {/* Peças — the visual the client reviews beside the legenda in the
            approval portal. */}
        <PecasDaPauta pauta={pauta} />

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button
            className="min-h-11"
            disabled={salvando}
            onClick={() => onSalvar({ copy_texto: copy, direcao_video: direcao })}
          >
            <Save className="mr-2 h-4 w-4" />
            {salvando ? "Salvando…" : "Salvar textos"}
          </Button>
          {confirmandoRemocao ? (
            <>
              <Button variant="destructive" size="sm" onClick={onRemover}>
                Confirmar remoção
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmandoRemocao(false)}>
                Cancelar
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmandoRemocao(true)}
              aria-label="Remover pauta"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
          {pauta.linha_editorial && <Badge variant="outline">{pauta.linha_editorial}</Badge>}
        </div>
      </DialogBody>
    </>
  );
}

/** Upload + list the visual assets attached to a pauta. */
function PecasDaPauta({ pauta }: { pauta: Pauta }) {
  const { pecas, loading } = usePecas(pauta.id);
  const enviar = useEnviarPeca();

  return (
    <div className="space-y-2 rounded border border-border p-3">
      <p className="text-xs font-medium text-muted-foreground">Peças</p>

      {loading ? (
        <Skeleton className="h-8 w-full" />
      ) : pecas.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Nenhuma peça enviada. O cliente aprova a arte junto com a legenda.
        </p>
      ) : (
        <ul className="space-y-1 text-xs text-foreground">
          {pecas.map((p) => (
            <li key={p.id} className="flex items-center gap-2">
              <FileImage className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="min-w-0 truncate">{p.nome_arquivo ?? p.storage_key}</span>
            </li>
          ))}
        </ul>
      )}

      <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-accent">
        <Upload className="h-3 w-3" />
        {enviar.isPending ? "Enviando…" : "Enviar peça"}
        <input
          type="file"
          className="hidden"
          disabled={enviar.isPending}
          onChange={(e) => {
            const arquivo = e.target.files?.[0];
            if (!arquivo) return;
            enviar.mutate({ pautaId: pauta.id, arquivo });
            e.target.value = ""; // re-picking the same file must fire again
          }}
        />
      </label>

      {enviar.isError && (
        <p className="text-xs text-destructive">Não foi possível enviar a peça.</p>
      )}
    </div>
  );
}

export default CalendarioMes;
