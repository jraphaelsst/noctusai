/**
 * Central da Marca — Módulo 2.
 *
 * One screen per client covering the four spec surfaces (identidade visual,
 * tom de voz, linhas editoriais, personas) plus the Cofre de Acessos, with the
 * live RepertorioSidebar alongside so you see exactly what the creative team
 * will see while working a tarefa.
 *
 * The Cofre section is written defensively on purpose: passwords are entered
 * but never rendered back, revealing one is an explicit per-record action, and
 * a revealed value is held in local state that clears on the next action
 * rather than living in the query cache.
 */
import { useState } from "react";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { Eye, KeyRound, Plus, Save, Trash2 } from "lucide-react";

import { RepertorioSidebar } from "@/components/RepertorioSidebar";
import { useClientes } from "@/hooks/useClientes";
import {
  useAcessos,
  useAtualizarMarca,
  useCriarAcesso,
  useCriarMarca,
  useMarcas,
  useRemoverAcesso,
  useRevelarSenha,
  type CorPaleta,
  type LinhaEditorial,
  type Marca as MarcaTipo,
  type NivelFormalidade,
} from "@/hooks/useMarca";

const FORMALIDADES: NivelFormalidade[] = ["informal", "neutro", "formal"];

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">{titulo}</h2>
      {children}
    </section>
  );
}

export default function Marca() {
  const { clientes, loading: carregandoClientes } = useClientes();
  const [clienteId, setClienteId] = useState<string>("");
  const clienteAtual = clientes.find((c) => c.id === clienteId);

  const { marcas, loading: carregandoMarcas } = useMarcas(clienteId || undefined);
  const marca = marcas[0] ?? null;

  const criarMarca = useCriarMarca();
  const atualizarMarca = useAtualizarMarca();

  // ── Cofre ────────────────────────────────────────────────────────
  const { acessos, loading: carregandoAcessos } = useAcessos(clienteId || undefined);
  const criarAcesso = useCriarAcesso();
  const removerAcesso = useRemoverAcesso();
  const revelar = useRevelarSenha();
  const [reveladas, setReveladas] = useState<Record<string, string>>({});
  const [novoAcesso, setNovoAcesso] = useState({ rotulo: "", usuario: "", senha: "", url: "" });

  function handleRevelar(id: string) {
    revelar.mutate(id, {
      // Held locally, not in the query cache — a decrypted credential should
      // not survive in memory past the interaction that asked for it.
      onSuccess: (r) => setReveladas((atual) => ({ ...atual, [id]: r.senha })),
    });
  }

  /** Typed partial update — no cast, so a renamed field fails at compile time. */
  function patch(campos: Partial<MarcaTipo>) {
    if (!marca) return;
    atualizarMarca.mutate({ id: marca.id, ...campos });
  }

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Central da Marca</h1>
        <p className="text-sm text-muted-foreground">
          Identidade, tom de voz, linhas editoriais, personas e acessos de cada cliente.
        </p>
      </header>

      <label className="block max-w-sm">
        <span className="mb-1 block text-xs text-muted-foreground">Cliente</span>
        <select
          value={clienteId}
          onChange={(e) => {
            setClienteId(e.target.value);
            setReveladas({});
          }}
          disabled={carregandoClientes}
          className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground"
        >
          <option value="">Selecione um cliente…</option>
          {clientes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
        </select>
      </label>

      {!clienteId ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          Escolha um cliente para ver e editar seu repertório.
        </p>
      ) : (
        <div className="flex flex-col gap-6 lg:flex-row">
          <div className="min-w-0 flex-1 space-y-4">
            {carregandoMarcas ? (
              <Skeleton className="h-40 w-full" />
            ) : !marca ? (
              <Secao titulo="Nenhuma marca cadastrada">
                <Button
                  disabled={criarMarca.isPending}
                  onClick={() =>
                    criarMarca.mutate({
                      cliente_id: clienteId,
                      nome: clienteAtual?.nome ?? "Nova marca",
                    })
                  }
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Criar marca para {clienteAtual?.nome}
                </Button>
              </Secao>
            ) : (
              <>
                <Secao titulo="Tom de voz">
                  <textarea
                    defaultValue={marca.tom_de_voz ?? ""}
                    onBlur={(e) => patch({ tom_de_voz: e.target.value })}
                    rows={3}
                    placeholder="Como a marca fala com o público…"
                    className="w-full rounded-md border border-border bg-background p-2 text-sm text-foreground"
                  />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-muted-foreground">Formalidade:</span>
                    {FORMALIDADES.map((nivel) => (
                      <Button
                        key={nivel}
                        size="sm"
                        variant={marca.nivel_formalidade === nivel ? "primary" : "outline"}
                        onClick={() => patch({ nivel_formalidade: nivel })}
                      >
                        {nivel}
                      </Button>
                    ))}
                  </div>
                </Secao>

                <Secao titulo="Termos proibidos">
                  <textarea
                    defaultValue={marca.termos_proibidos ?? ""}
                    onBlur={(e) => patch({ termos_proibidos: e.target.value })}
                    rows={2}
                    placeholder="Palavras e expressões que a marca não usa…"
                    className="w-full rounded-md border border-border bg-background p-2 text-sm text-foreground"
                  />
                </Secao>

                <Secao titulo="Paleta">
                  <PaletaEditor
                    paleta={marca.paleta}
                    onChange={(p: CorPaleta[]) => patch({ paleta: p })}
                  />
                </Secao>

                <Secao titulo="Linhas editoriais">
                  <ListaSimples
                    itens={marca.linhas_editoriais.map((l) => l.nome)}
                    placeholder="Institucional, Educacional, Comercial…"
                    onChange={(nomes) =>
                      patch({
                        linhas_editoriais: nomes.map((nome): LinhaEditorial => ({ nome })),
                      })
                    }
                  />
                </Secao>

                <Secao titulo="Personas">
                  <ListaSimples
                    itens={marca.personas.map((p) => p.nome)}
                    placeholder="Nome da persona…"
                    onChange={(nomes) =>
                      patch({
                        personas: nomes.map((nome) => ({ nome, dores: [], desejos: [] })),
                      })
                    }
                  />
                  <p className="mt-2 text-xs text-muted-foreground">
                    Dores, desejos e dados demográficos por persona: próxima iteração.
                  </p>
                </Secao>
              </>
            )}

            {/* ── Cofre de Acessos ─────────────────────────────── */}
            <Secao titulo="Cofre de Acessos">
              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!novoAcesso.rotulo.trim()) return;
                  criarAcesso.mutate(
                    { cliente_id: clienteId, ...novoAcesso },
                    { onSuccess: () => setNovoAcesso({ rotulo: "", usuario: "", senha: "", url: "" }) },
                  );
                }}
              >
                <Input
                  aria-label="Rótulo"
                  placeholder="Meta Business"
                  value={novoAcesso.rotulo}
                  onChange={(e) => setNovoAcesso((a) => ({ ...a, rotulo: e.target.value }))}
                  className="min-w-[140px] flex-1"
                />
                <Input
                  aria-label="Usuário"
                  placeholder="usuário"
                  value={novoAcesso.usuario}
                  onChange={(e) => setNovoAcesso((a) => ({ ...a, usuario: e.target.value }))}
                  className="min-w-[120px] flex-1"
                />
                <Input
                  aria-label="Senha"
                  type="password"
                  placeholder="senha"
                  value={novoAcesso.senha}
                  onChange={(e) => setNovoAcesso((a) => ({ ...a, senha: e.target.value }))}
                  className="min-w-[120px] flex-1"
                />
                <Button type="submit" disabled={!novoAcesso.rotulo.trim() || criarAcesso.isPending}>
                  <Save className="mr-2 h-4 w-4" />
                  Guardar
                </Button>
              </form>

              {criarAcesso.isError && (
                <p className="mt-2 text-sm text-destructive">
                  Não foi possível guardar. Se o cofre não estiver configurado
                  (IGIG_COFRE_KEY), a senha é recusada em vez de ser gravada em texto puro.
                </p>
              )}

              {carregandoAcessos ? (
                <Skeleton className="mt-3 h-16 w-full" />
              ) : acessos.length === 0 ? (
                <p className="mt-3 text-sm text-muted-foreground">Nenhum acesso guardado.</p>
              ) : (
                <ul className="mt-3 divide-y divide-border">
                  {acessos.map((acesso) => (
                    <li key={acesso.id} className="flex flex-wrap items-center gap-2 py-2">
                      <KeyRound className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-foreground">{acesso.rotulo}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {acesso.usuario || "sem usuário"}
                        </p>
                      </div>
                      {acesso.tem_senha ? (
                        reveladas[acesso.id] ? (
                          <code className="rounded bg-muted px-2 py-1 text-xs text-foreground">
                            {reveladas[acesso.id]}
                          </code>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={revelar.isPending}
                            onClick={() => handleRevelar(acesso.id)}
                          >
                            <Eye className="mr-2 h-3 w-3" />
                            Revelar
                          </Button>
                        )
                      ) : (
                        <Badge variant="muted">sem senha</Badge>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remover ${acesso.rotulo}`}
                        onClick={() => removerAcesso.mutate(acesso.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}

              {revelar.isError && (
                <p className="mt-2 text-sm text-destructive">
                  Não foi possível revelar. Apenas administradores podem ler senhas.
                </p>
              )}
            </Secao>
          </div>

          {/* Live preview of exactly what the creative team sees on a tarefa. */}
          <RepertorioSidebar clienteId={clienteId} />
        </div>
      )}
    </div>
  );
}

/** Minimal add/remove list — shared by linhas editoriais and personas. */
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
  return (
    <div>
      <div className="flex gap-2">
        <Input
          value={novo}
          placeholder={placeholder}
          onChange={(e) => setNovo(e.target.value)}
          aria-label={placeholder}
        />
        <Button
          type="button"
          disabled={!novo.trim()}
          onClick={() => {
            onChange([...itens, novo.trim()]);
            setNovo("");
          }}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-1">
        {itens.map((item, i) => (
          <li key={`${item}-${i}`}>
            <button
              type="button"
              onClick={() => onChange(itens.filter((_, idx) => idx !== i))}
              className="rounded border border-border px-2 py-0.5 text-xs text-foreground hover:bg-muted"
              title="Remover"
            >
              {item} ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Palette editor. `hex` is validated server-side too — this is convenience. */
function PaletaEditor({
  paleta,
  onChange,
}: {
  paleta: CorPaleta[];
  onChange: (p: CorPaleta[]) => void;
}) {
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
          className="min-w-[120px] flex-1"
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
          disabled={!nome.trim()}
          onClick={() => {
            onChange([...paleta, { nome: nome.trim(), hex }]);
            setNome("");
          }}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ul className="mt-2 space-y-1">
        {paleta.map((cor, i) => (
          <li key={`${cor.nome}-${i}`} className="flex items-center gap-2">
            <span
              className="h-5 w-5 rounded border border-border"
              style={{ backgroundColor: cor.hex }}
            />
            <span className="flex-1 truncate text-xs text-foreground">{cor.nome}</span>
            <code className="text-[11px] text-muted-foreground">{cor.hex}</code>
            <Button
              variant="ghost"
              size="sm"
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
