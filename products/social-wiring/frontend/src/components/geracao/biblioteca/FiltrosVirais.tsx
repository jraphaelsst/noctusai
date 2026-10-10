/**
 * "Filtros de Virais" panel (contract §7.3): CoreStudio's fields minus Rede
 * Social and Core, plus the "Mostrar só virais" switch. Edits a local draft;
 * **Aplicar** commits it, **Limpar Filtros** resets to the defaults.
 */
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { MultiSelectPopover } from "@/pages/leads/components/MultiSelectPopover";
import { usePerfisMonitorados } from "@/hooks/geracao/useBiblioteca";
import { useTaxonomias } from "@/hooks/geracao/useTaxonomias";
import { FILTROS_VAZIOS, type BuscarEm, type FiltrosViral } from "./filtros";

interface Props {
  filtros: FiltrosViral;
  onAplicar: (f: FiltrosViral) => void;
  /** Picker mode hides fields that make no sense inside a modal. */
  compacto?: boolean;
}

const numOuNull = (v: string): number | null => {
  const n = Number(v);
  return v.trim() !== "" && Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
};

export function FiltrosVirais({ filtros, onAplicar, compacto = false }: Props) {
  const [rascunho, setRascunho] = useState<FiltrosViral>(filtros);
  useEffect(() => setRascunho(filtros), [filtros]);

  const taxQ = useTaxonomias();
  const perfisQ = usePerfisMonitorados();
  const tax = taxQ.data;
  const perfis = perfisQ.data ?? [];

  const set = <K extends keyof FiltrosViral>(k: K, v: FiltrosViral[K]) =>
    setRascunho((r) => ({ ...r, [k]: v }));
  const alternar = (k: "nichos" | "profissoes", v: string) => {
    const id = Number(v);
    setRascunho((r) => ({
      ...r,
      [k]: r[k].includes(id) ? r[k].filter((x) => x !== id) : [...r[k], id],
    }));
  };

  return (
    <form
      aria-label="Filtros de Virais"
      className="flex flex-col gap-4 rounded-lg border bg-card p-4"
      onSubmit={(e) => {
        e.preventDefault();
        onAplicar({ ...rascunho, page: 1 });
      }}
    >
      <h2 className="text-base font-semibold">Filtros de Virais</h2>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="bib-q">Buscar por palavras-chave</Label>
        <Input
          id="bib-q"
          placeholder="palavras separadas por vírgula"
          value={rascunho.q}
          onChange={(e) => set("q", e.target.value)}
        />
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          {(["gancho", "transcricao"] as BuscarEm[]).map((v) => (
            <label key={v} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="buscar-em"
                checked={rascunho.buscarEm === v}
                onChange={() => set("buscarEm", v)}
              />
              {v === "gancho" ? "Buscar nas headlines (gancho)" : "Buscar na transcrição"}
            </label>
          ))}
        </div>
      </div>

      {!compacto && (
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bib-de">De</Label>
            <Input
              id="bib-de"
              type="date"
              value={rascunho.dataDe}
              onChange={(e) => set("dataDe", e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bib-ate">Até</Label>
            <Input
              id="bib-ate"
              type="date"
              value={rascunho.dataAte}
              onChange={(e) => set("dataAte", e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        {(
          [
            ["viewsMin", "Visualizações mínimas"],
            ["likesMin", "Curtidas mínimas"],
            ["commentsMin", "Comentários mínimos"],
          ] as const
        ).map(([k, rotulo]) => (
          <div key={k} className="flex flex-col gap-1.5">
            <Label htmlFor={`bib-${k}`} className="text-xs">
              {rotulo}
            </Label>
            <Input
              id={`bib-${k}`}
              type="number"
              min={0}
              value={rascunho[k] ?? ""}
              onChange={(e) => set(k, numOuNull(e.target.value))}
            />
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="bib-perfil">Perfil</Label>
        <select
          id="bib-perfil"
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={rascunho.perfilId}
          onChange={(e) => set("perfilId", e.target.value)}
        >
          <option value="">Todos os perfis</option>
          {perfis.map((p) => (
            <option key={p.id} value={p.id}>
              @{p.handle}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="bib-formato">Formato de vídeo</Label>
        <select
          id="bib-formato"
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={rascunho.formatoId ?? ""}
          onChange={(e) => set("formatoId", e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Todos os formatos</option>
          {(tax?.formatos ?? []).map((f) => (
            <option key={f.id} value={f.id}>
              {f.nome}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap gap-2">
        <MultiSelectPopover
          label="Nichos"
          options={(tax?.nichos ?? []).map((n) => ({ value: String(n.id), label: n.nome }))}
          selected={rascunho.nichos.map(String)}
          onToggle={(v) => alternar("nichos", v)}
        />
        <MultiSelectPopover
          label="Profissões"
          options={(tax?.profissoes ?? []).map((n) => ({ value: String(n.id), label: n.nome }))}
          selected={rascunho.profissoes.map(String)}
          onToggle={(v) => alternar("profissoes", v)}
        />
      </div>

      {!compacto && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bib-codigo">ID do Viral</Label>
          <Input
            id="bib-codigo"
            type="number"
            min={0}
            value={rascunho.codigo ?? ""}
            onChange={(e) => set("codigo", numOuNull(e.target.value))}
          />
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="bib-so-virais">Mostrar só virais</Label>
        <Switch
          id="bib-so-virais"
          checked={rascunho.somenteVirais}
          onCheckedChange={(v) => set("somenteVirais", v)}
        />
      </div>

      <div className="flex gap-2">
        <Button type="submit">Aplicar</Button>
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            onAplicar({ ...FILTROS_VAZIOS, ordem: filtros.ordem, perfilId: "", verTodos: filtros.verTodos })
          }
        >
          Limpar Filtros
        </Button>
      </div>
    </form>
  );
}
