/**
 * One marca's editor — identidade visual (logo + paleta), tom de voz +
 * formalidade, termos proibidos, linhas editoriais, personas (Módulo 2).
 *
 * Moved from the old Central da Marca page (which edited `marcas[0]` only)
 * into the Clientes card, one panel PER marca — a cliente carries N marcas
 * (roadmap R9). Text fields save on blur (a PATCH per field, the same
 * behaviour the page had); list fields save on each add/remove.
 */
import { useState } from "react";
import { Button, Input } from "@noctusai/lib/design-system";
import { Plus, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import {
  useAtualizarMarca,
  useEnviarLogo,
  type CorPaleta,
  type LinhaEditorial,
  type Marca,
  type NivelFormalidade,
} from "@/hooks/useMarca";
import { describeError } from "@/lib/errors";

const FORMALIDADES: NivelFormalidade[] = ["informal", "neutro", "formal"];

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titulo}</h4>
      {children}
    </section>
  );
}

const TEXTAREA =
  "w-full rounded-md border border-border bg-background p-2 text-sm text-foreground";

export function MarcaPanel({ marca, onRemover }: { marca: Marca; onRemover?: () => void }) {
  const atualizar = useAtualizarMarca();

  /** Typed partial update — a renamed field fails at compile time. */
  function patch(campos: Partial<Marca>) {
    atualizar.mutate(
      { id: marca.id, ...campos },
      { onError: (e) => toast.error(describeError(e, "Não foi possível salvar a marca.")) },
    );
  }

  return (
    <div className="space-y-4" data-testid={`marca-panel-${marca.id}`}>
      <div className="flex items-end gap-2">
        <label className="min-w-0 flex-1 text-xs text-muted-foreground">
          Nome da marca
          <Input
            key={`nome-${marca.id}-${marca.nome}`}
            className="mt-1 max-sm:h-10"
            defaultValue={marca.nome}
            aria-label="Nome da marca"
            onBlur={(e) => {
              const nome = e.target.value.trim();
              if (nome && nome !== marca.nome) patch({ nome });
            }}
          />
        </label>
        {onRemover ? (
          <Button
            variant="ghost"
            size="icon"
            className="text-destructive max-sm:h-10 max-sm:w-10"
            aria-label={`Remover marca ${marca.nome}`}
            onClick={onRemover}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null}
      </div>

      <Secao titulo="Identidade visual">
        <LogoUploader marca={marca} />
      </Secao>

      <Secao titulo="Paleta">
        <PaletaEditor paleta={marca.paleta} onChange={(p) => patch({ paleta: p })} />
      </Secao>

      <Secao titulo="Tom de voz">
        <textarea
          key={`tom-${marca.id}`}
          defaultValue={marca.tom_de_voz ?? ""}
          onBlur={(e) => {
            if (e.target.value !== (marca.tom_de_voz ?? "")) patch({ tom_de_voz: e.target.value });
          }}
          rows={3}
          aria-label="Tom de voz"
          placeholder="Como a marca fala com o público…"
          className={TEXTAREA}
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Formalidade:</span>
          {FORMALIDADES.map((nivel) => (
            <Button
              key={nivel}
              size="sm"
              className="max-sm:h-10"
              variant={marca.nivel_formalidade === nivel ? "primary" : "outline"}
              aria-pressed={marca.nivel_formalidade === nivel}
              onClick={() => patch({ nivel_formalidade: nivel })}
            >
              {nivel}
            </Button>
          ))}
        </div>
      </Secao>

      <Secao titulo="Termos proibidos">
        <textarea
          key={`termos-${marca.id}`}
          defaultValue={marca.termos_proibidos ?? ""}
          onBlur={(e) => {
            if (e.target.value !== (marca.termos_proibidos ?? "")) patch({ termos_proibidos: e.target.value });
          }}
          rows={2}
          aria-label="Termos proibidos"
          placeholder="Palavras e expressões que a marca não usa…"
          className={TEXTAREA}
        />
      </Secao>

      <Secao titulo="Linhas editoriais">
        <ListaSimples
          itens={marca.linhas_editoriais.map((l) => l.nome)}
          placeholder="Institucional, Educacional, Comercial…"
          onChange={(nomes) => patch({ linhas_editoriais: nomes.map((nome): LinhaEditorial => ({ nome })) })}
        />
      </Secao>

      <Secao titulo="Personas">
        <ListaSimples
          itens={marca.personas.map((p) => p.nome)}
          placeholder="Nome da persona…"
          onChange={(nomes) =>
            // Keep what an existing persona already carries (dores, desejos,
            // demographics) — only names are edited here.
            patch({
              personas: nomes.map(
                (nome) => marca.personas.find((p) => p.nome === nome) ?? { nome, dores: [], desejos: [] },
              ),
            })
          }
        />
      </Secao>
    </div>
  );
}

/** Minimal add/remove chip list — linhas editoriais and personas. */
function ListaSimples({
  itens,
  placeholder,
  onChange,
}: {
  itens: string[];
  placeholder: string;
  onChange: (itens: string[]) => void;
}) {
  const [novo, setNovo] = useState("");
  function adicionar() {
    if (!novo.trim()) return;
    onChange([...itens, novo.trim()]);
    setNovo("");
  }
  return (
    <div>
      <div className="flex gap-2">
        <Input
          value={novo}
          placeholder={placeholder}
          onChange={(e) => setNovo(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              adicionar();
            }
          }}
          aria-label={placeholder}
          className="max-sm:h-10"
        />
        <Button type="button" className="max-sm:h-10" aria-label="Adicionar" disabled={!novo.trim()} onClick={adicionar}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-1">
        {itens.map((item, i) => (
          <li key={`${item}-${i}`}>
            <button
              type="button"
              onClick={() => onChange(itens.filter((_, idx) => idx !== i))}
              className="min-h-8 rounded border border-border px-2 py-1 text-xs text-foreground hover:bg-muted"
              title="Remover"
              aria-label={`Remover ${item}`}
            >
              {item} ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Logo upload. Accept list mirrors the backend's `_LOGO_MIMES`; the size
 * limit is stated up front. Backend limits stay authoritative.
 */
function LogoUploader({ marca }: { marca: Marca }) {
  const enviar = useEnviarLogo();
  return (
    <div className="flex flex-wrap items-center gap-3">
      {marca.logo_url ? (
        <img
          src={marca.logo_url}
          alt={`Logo de ${marca.nome}`}
          className="h-16 w-auto max-w-[160px] rounded border border-border bg-background object-contain p-1"
        />
      ) : (
        <p className="text-sm text-muted-foreground">Nenhum logo enviado.</p>
      )}
      <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-foreground hover:bg-accent sm:min-h-8">
        <Upload className="h-4 w-4" />
        {enviar.isPending ? "Enviando…" : marca.logo_url ? "Trocar logo" : "Enviar logo"}
        <input
          type="file"
          className="hidden"
          accept="image/png,image/svg+xml,image/jpeg,image/webp"
          disabled={enviar.isPending}
          onChange={(e) => {
            const arquivo = e.target.files?.[0];
            if (!arquivo) return;
            enviar.mutate({ marcaId: marca.id, arquivo });
            // Clear so re-picking the SAME file fires change again.
            e.target.value = "";
          }}
        />
      </label>
      <p className="w-full text-xs text-muted-foreground">PNG, SVG, JPEG ou WebP · até 2 MB.</p>
      {enviar.isError && (
        <p className="w-full text-sm text-destructive">
          {describeError(enviar.error, "Não foi possível enviar o logo. Verifique o formato e o tamanho.")}
        </p>
      )}
    </div>
  );
}

function PaletaEditor({ paleta, onChange }: { paleta: CorPaleta[]; onChange: (p: CorPaleta[]) => void }) {
  const [nome, setNome] = useState("");
  const [hex, setHex] = useState("#f97316");
  return (
    <div>
      <div className="flex flex-wrap items-end gap-2">
        <Input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="primária"
          aria-label="Nome da cor"
          className="min-w-[120px] flex-1 max-sm:h-10"
        />
        <input
          type="color"
          value={hex}
          onChange={(e) => setHex(e.target.value)}
          aria-label="Cor"
          className="h-10 w-14 rounded border border-border bg-card"
        />
        <Button
          type="button"
          className="max-sm:h-10"
          aria-label="Adicionar cor"
          disabled={!nome.trim()}
          onClick={() => {
            onChange([...paleta, { nome: nome.trim(), hex }]);
            setNome("");
          }}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-2">
        {paleta.map((cor, i) => (
          <li key={`${cor.nome}-${i}`} className="flex items-center gap-2 rounded border border-border py-1 pl-2 pr-1">
            <span className="h-5 w-5 rounded border border-border" style={{ backgroundColor: cor.hex }} />
            <span className="max-w-[8rem] truncate text-xs text-foreground">{cor.nome}</span>
            <code className="text-[11px] text-muted-foreground">{cor.hex}</code>
            <Button
              variant="ghost"
              size="icon"
              className="max-sm:h-10 max-sm:w-10"
              aria-label={`Remover ${cor.nome}`}
              onClick={() => onChange(paleta.filter((_, idx) => idx !== i))}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
