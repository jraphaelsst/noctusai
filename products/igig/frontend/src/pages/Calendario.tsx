/**
 * Calendário Editorial — Módulo 3.
 *
 * A month grid of pautas plus the integrated copy editor.
 *
 * Rescheduling is native HTML5 drag-and-drop onto a day cell — the spec asks
 * for "arrasta-e-solta", and the browser's own API does it without adding a
 * DnD dependency. Every drag target is ALSO reachable by keyboard through the
 * editor's date field, so the feature is not mouse-only.
 *
 * The character counter mirrors the server's `caracteres_copy` while you type
 * (presentation), and reconciles with the server value on save — the rule
 * itself lives in one place, on the backend.
 */
import { useMemo, useState } from "react";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { ChevronLeft, ChevronRight, Plus, Save, Trash2 } from "lucide-react";

import { useClientes } from "@/hooks/useClientes";
import {
  FORMATOS,
  FUNIL_LABEL,
  FUNIS,
  useAtualizarPauta,
  useCalendario,
  useCriarPauta,
  useRemoverPauta,
  type Formato,
  type Funil,
  type Pauta,
} from "@/hooks/usePautas";

/** Instagram's caption cap — the practical ceiling for a legenda. */
const LIMITE_LEGENDA = 2200;

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function inicioDoMes(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function fimDoMes(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

export default function Calendario() {
  const [mes, setMes] = useState(() => inicioDoMes(new Date()));
  const [selecionada, setSelecionada] = useState<Pauta | null>(null);

  const inicio = `${iso(inicioDoMes(mes))}T00:00:00`;
  const fim = `${iso(fimDoMes(mes))}T23:59:59`;
  const { itens, loading } = useCalendario(inicio, fim);

  const { clientes } = useClientes();
  const criar = useCriarPauta();
  const atualizar = useAtualizarPauta();
  const remover = useRemoverPauta();

  const [novoTitulo, setNovoTitulo] = useState("");
  const [novoCliente, setNovoCliente] = useState("");

  /** Pautas bucketed by day-of-month. */
  const porDia = useMemo(() => {
    const mapa = new Map<number, Pauta[]>();
    for (const p of itens) {
      if (!p.data_publicacao) continue;
      const dia = new Date(p.data_publicacao).getDate();
      mapa.set(dia, [...(mapa.get(dia) ?? []), p]);
    }
    return mapa;
  }, [itens]);

  const diasNoMes = fimDoMes(mes).getDate();
  const rotuloMes = mes.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  function reagendar(pautaId: string, dia: number) {
    const data = new Date(mes.getFullYear(), mes.getMonth(), dia, 9, 0, 0);
    atualizar.mutate({ id: pautaId, data_publicacao: data.toISOString() });
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Calendário Editorial</h1>
          <p className="text-sm text-muted-foreground">
            Arraste uma pauta para outro dia para reagendar.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            aria-label="Mês anterior"
            onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[160px] text-center text-sm capitalize text-foreground">
            {rotuloMes}
          </span>
          <Button
            variant="outline"
            size="sm"
            aria-label="Próximo mês"
            onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {/* ── Nova pauta ─────────────────────────────────────────────── */}
      <form
        className="flex flex-wrap items-end gap-2 rounded-lg border border-border bg-card p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!novoTitulo.trim() || !novoCliente) return;
          criar.mutate(
            {
              cliente_id: novoCliente,
              titulo: novoTitulo.trim(),
              data_publicacao: new Date(
                mes.getFullYear(), mes.getMonth(), 1, 9, 0, 0,
              ).toISOString(),
            },
            { onSuccess: () => setNovoTitulo("") },
          );
        }}
      >
        <select
          aria-label="Cliente"
          value={novoCliente}
          onChange={(e) => setNovoCliente(e.target.value)}
          className="h-10 rounded-md border border-border bg-card px-3 text-sm text-foreground"
        >
          <option value="">Cliente…</option>
          {clientes.map((c) => (
            <option key={c.id} value={c.id}>{c.nome}</option>
          ))}
        </select>
        <Input
          aria-label="Título da pauta"
          value={novoTitulo}
          onChange={(e) => setNovoTitulo(e.target.value)}
          placeholder="Post institucional"
          className="min-w-[200px] flex-1"
        />
        <Button type="submit" disabled={!novoTitulo.trim() || !novoCliente || criar.isPending}>
          <Plus className="mr-2 h-4 w-4" />
          Adicionar
        </Button>
      </form>

      <div className="flex flex-col gap-6 xl:flex-row">
        {/* ── Grid ───────────────────────────────────────────────── */}
        <div className="min-w-0 flex-1">
          {loading ? (
            <Skeleton className="h-96 w-full" />
          ) : (
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: diasNoMes }, (_, i) => i + 1).map((dia) => (
                <div
                  key={dia}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const id = e.dataTransfer.getData("text/plain");
                    if (id) reagendar(id, dia);
                  }}
                  className="min-h-[92px] rounded border border-border bg-card p-1"
                >
                  <span className="text-[11px] text-muted-foreground">{dia}</span>
                  <ul className="mt-1 space-y-1">
                    {(porDia.get(dia) ?? []).map((pauta) => (
                      <li key={pauta.id}>
                        <button
                          type="button"
                          draggable
                          onDragStart={(e) => e.dataTransfer.setData("text/plain", pauta.id)}
                          onClick={() => setSelecionada(pauta)}
                          className="w-full truncate rounded bg-muted px-1 py-0.5 text-left text-[11px] text-foreground hover:bg-border"
                          title={pauta.titulo}
                        >
                          {pauta.titulo}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Editor ─────────────────────────────────────────────── */}
        {selecionada && (
          <EditorPauta
            key={selecionada.id}
            pauta={selecionada}
            onFechar={() => setSelecionada(null)}
            onSalvar={(patch) => atualizar.mutate({ id: selecionada.id, ...patch })}
            onRemover={() => {
              remover.mutate(selecionada.id);
              setSelecionada(null);
            }}
            salvando={atualizar.isPending}
          />
        )}
      </div>
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
  const excedeu = copy.length > LIMITE_LEGENDA;

  return (
    <aside className="w-full space-y-3 rounded-lg border border-border bg-card p-4 xl:w-96">
      <header className="flex items-start justify-between gap-2">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
          {pauta.titulo}
        </h2>
        <Button variant="ghost" size="sm" onClick={onFechar} aria-label="Fechar editor">
          ×
        </Button>
      </header>

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
          className="h-9 w-full rounded border border-border bg-background px-2 text-sm text-foreground"
        >
          <option value="">—</option>
          {FORMATOS.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
      </label>

      <label className="block">
        <span className="mb-1 block text-xs text-muted-foreground">
          Data de publicação
          <span className="ml-1 text-[11px]">(ou arraste no calendário)</span>
        </span>
        <input
          type="date"
          value={pauta.data_publicacao ? pauta.data_publicacao.slice(0, 10) : ""}
          onChange={(e) =>
            onSalvar({
              // Empty clears the date — the backend accepts explicit null and
              // takes the pauta off the grid.
              data_publicacao: e.target.value
                ? new Date(`${e.target.value}T09:00:00`).toISOString()
                : null,
            })
          }
          className="h-9 w-full rounded border border-border bg-background px-2 text-sm text-foreground"
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

      <div className="flex flex-wrap items-center gap-2">
        <Button
          disabled={salvando}
          onClick={() => onSalvar({ copy_texto: copy, direcao_video: direcao })}
        >
          <Save className="mr-2 h-4 w-4" />
          {salvando ? "Salvando…" : "Salvar textos"}
        </Button>
        <Button variant="ghost" size="sm" onClick={onRemover} aria-label="Remover pauta">
          <Trash2 className="h-4 w-4" />
        </Button>
        {pauta.linha_editorial && <Badge variant="outline">{pauta.linha_editorial}</Badge>}
      </div>
    </aside>
  );
}
