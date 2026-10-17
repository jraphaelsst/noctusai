/**
 * Shared roteiro editing surface (contract §7.8): tabs Roteiro / Fontes da
 * Pesquisa (the latter hidden while `fontes` is NULL), Nome (optional),
 * markdown textarea, Copiar Roteiro, and the optimistic-lock save (#37, 409).
 */
import { useEffect, useRef, useState } from "react";
import { Copy, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSalvarRoteiro } from "@/hooks/geracao/useRoteiros";
import type { Roteiro } from "@/types/geracao";
import { ESTRUTURA_ROTULO } from "../labels";

export const NOME_MAX = 160;
export const CONTEUDO_MAX = 30_000;
export const MSG_CONFLITO = "O roteiro mudou; recarregue";
/** Where a roteiro lives once generated — every roteiro is persisted server-side as it is created. */
export const MSG_SALVO = "Roteiro salvo em Headlines › Roteiros.";
/** Same footprint as the funil card (`CardHubDialog`): the roteiro is long-form text. */
export const MODAL_ROTEIRO_GRANDE =
  "h-[90vh] w-[90vw] max-w-[90vw] overflow-y-auto max-sm:h-[100dvh] max-sm:w-screen max-sm:max-w-none";

function statusDe(e: unknown): number | null {
  const s = (e as { status?: unknown } | null)?.status;
  if (typeof s === "number") return s;
  const m = e instanceof Error ? /^\[(\d+)\]/.exec(e.message) : null;
  return m ? Number(m[1]) : null;
}

/** The server values the local edit state was seeded from (or last reconciled with). */
interface Base {
  id: string;
  versao: number;
  nome: string;
  conteudo: string;
}

/**
 * Local edit state for one roteiro, reconciled against the polled server row.
 *
 * The local `nome`/`conteudo` remember the server BASELINE they came from. On
 * every server change (generation finishing, a reprocess, another tab saving,
 * our own save) each field is reconciled on its own:
 *   - untouched locally (local === baseline), or already equal to the server
 *     → adopt the server value;
 *   - typed locally AND changed on the server → keep the typed text and raise
 *     `conflito` (the same "O roteiro mudou; recarregue" path a 409 takes).
 * The save sends `expected_versao` = the baseline's versao, so a save made over
 * an unreconciled server change is refused (409) instead of overwriting it.
 *
 * 2026-10-13 regression this closes: re-seeding only on id/versao meant an
 * editor mounted while the roteiro was still `criando` (conteudo null, versao 1)
 * kept "" after the worker wrote the text at the same versao — the textarea
 * showed 0 chars and "Atualizar" would have PATCHed "" over the roteiro.
 */
export function useEdicaoRoteiro(roteiro: Roteiro | undefined, onSalvo?: (r: Roteiro) => void) {
  const salvar = useSalvarRoteiro();
  const [nome, setNome] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [conflito, setConflito] = useState(false);
  const base = useRef<Base | null>(null);

  function adotar(r: Roteiro) {
    base.current = { id: r.id, versao: r.versao, nome: r.nome, conteudo: r.conteudo ?? "" };
    setNome(r.nome);
    setConteudo(r.conteudo ?? "");
    setConflito(false);
  }

  useEffect(() => {
    if (!roteiro) return;
    const b = base.current;
    if (!b || b.id !== roteiro.id) {
      adotar(roteiro);
      return;
    }
    const servNome = roteiro.nome;
    const servConteudo = roteiro.conteudo ?? "";
    let divergiu = false;
    const prox: Base = { ...b };
    if (servNome !== b.nome) {
      if (nome === b.nome || nome.trim() === servNome) {
        prox.nome = servNome;
        setNome(servNome);
      } else divergiu = true;
    }
    if (servConteudo !== b.conteudo) {
      if (conteudo === b.conteudo || conteudo === servConteudo) {
        prox.conteudo = servConteudo;
        setConteudo(servConteudo);
      } else divergiu = true;
    }
    // The baseline only advances to the server's versao once nothing is left unreconciled;
    // an unresolved field keeps diverging on every pass, so `conflito` tracks it exactly.
    if (!divergiu) prox.versao = roteiro.versao;
    base.current = prox;
    setConflito(divergiu);
  }, [roteiro?.id, roteiro?.versao, roteiro?.nome, roteiro?.conteudo]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Drop the local edits and take the current server row (the conflict's "Recarregar"). */
  function recarregar() {
    if (roteiro) adotar(roteiro);
  }

  const nomeLimpo = nome.trim();
  const conteudoServidor = roteiro?.conteudo ?? "";
  const alterouConteudo = !!roteiro && conteudo !== conteudoServidor;
  const alterou = !!roteiro && (nomeLimpo !== roteiro.nome || alterouConteudo);
  // A completo roteiro never goes blank (the API answers 422): clearing it is data loss, not an edit.
  const valido =
    nomeLimpo.length > 0 &&
    nomeLimpo.length <= NOME_MAX &&
    conteudo.length <= CONTEUDO_MAX &&
    (!alterouConteudo || conteudo.trim().length > 0);

  async function salvarAgora(): Promise<Roteiro | null> {
    if (!roteiro || !alterou || !valido) return null;
    try {
      const r = await salvar.mutateAsync({
        id: roteiro.id,
        nome: nomeLimpo !== roteiro.nome ? nomeLimpo : undefined,
        conteudo: alterouConteudo ? conteudo : undefined,
        expected_versao: base.current?.id === roteiro.id ? base.current.versao : roteiro.versao,
      });
      toast.success(MSG_SALVO);
      onSalvo?.(r);
      return r;
    } catch (e) {
      if (statusDe(e) === 409) setConflito(true);
      else toast.error(e instanceof Error && e.message ? e.message.replace(/^\[\d+\]\s*/, "") : "Não foi possível salvar o roteiro.");
      return null;
    }
  }

  return {
    nome,
    setNome,
    conteudo,
    setConteudo,
    conflito,
    recarregar,
    alterou,
    valido,
    salvando: salvar.isPending,
    salvar: salvarAgora,
  };
}

interface CorpoProps {
  roteiro: Roteiro;
  edicao: ReturnType<typeof useEdicaoRoteiro>;
  mostrarNome?: boolean;
  onRecarregar?: () => void;
}

export function RoteiroCorpo({ roteiro, edicao, mostrarNome = true, onRecarregar }: CorpoProps) {
  const temFontes = roteiro.fontes != null;

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success("Copiado!");
    } catch {
      toast.error("Não foi possível copiar.");
    }
  }

  return (
    <div className="space-y-3">
      {edicao.conflito && (
        <div role="alert" className="flex items-center justify-between rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <span>{MSG_CONFLITO}</span>
          {onRecarregar && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                edicao.recarregar();
                onRecarregar();
              }}
            >
              Recarregar
            </Button>
          )}
        </div>
      )}
      <p className="text-xs text-muted-foreground" data-testid="roteiro-estrutura">
        Estrutura: <Badge variant="secondary">{ESTRUTURA_ROTULO[roteiro.estrutura]}</Badge>
      </p>
      <Tabs defaultValue="roteiro">
        {temFontes && (
          <TabsList>
            <TabsTrigger value="roteiro">Roteiro</TabsTrigger>
            <TabsTrigger value="fontes">Fontes da Pesquisa</TabsTrigger>
          </TabsList>
        )}
        <TabsContent value="roteiro" className="space-y-3">
          {mostrarNome && (
            <div className="space-y-1.5">
              <Label htmlFor={`roteiro-nome-${roteiro.id}`}>Nome</Label>
              <Input
                id={`roteiro-nome-${roteiro.id}`}
                value={edicao.nome}
                maxLength={NOME_MAX}
                onChange={(e) => edicao.setNome(e.target.value)}
              />
            </div>
          )}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor={`roteiro-conteudo-${roteiro.id}`}>Roteiro</Label>
              <Button type="button" size="sm" variant="outline" onClick={() => copiar(edicao.conteudo)}>
                <Copy className="mr-1 h-4 w-4" /> Copiar Roteiro
              </Button>
            </div>
            <Textarea
              id={`roteiro-conteudo-${roteiro.id}`}
              rows={14}
              className="min-h-[45vh] font-mono text-sm"
              value={edicao.conteudo}
              onChange={(e) => edicao.setConteudo(e.target.value)}
              aria-invalid={edicao.conteudo.length > CONTEUDO_MAX}
            />
            <p className="text-xs text-muted-foreground">
              {edicao.conteudo.length.toLocaleString("pt-BR")}/{CONTEUDO_MAX.toLocaleString("pt-BR")} caracteres
            </p>
          </div>
        </TabsContent>
        {temFontes && (
          <TabsContent value="fontes" className="space-y-2">
            <pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm">{roteiro.fontes}</pre>
            <Button type="button" size="sm" variant="outline" onClick={() => copiar(roteiro.fontes ?? "")}>
              <Copy className="mr-1 h-4 w-4" /> Copiar Fontes
            </Button>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

/**
 * "Salvar roteiro" (💾). The roteiro is already persisted when generated, so with
 * no local edit the click only confirms where it lives; with an edit it runs the
 * optimistic-lock save (#37). It never PATCHes an unedited text.
 */
export function SalvarRoteiroButton({ edicao }: { edicao: ReturnType<typeof useEdicaoRoteiro> }) {
  async function clicar() {
    if (edicao.alterou) await edicao.salvar();
    else toast.success(MSG_SALVO);
  }
  return (
    <Button disabled={edicao.salvando || (edicao.alterou && !edicao.valido)} onClick={() => void clicar()}>
      <Save className="mr-1 h-4 w-4" />
      {edicao.salvando ? "Salvando…" : "Salvar roteiro"}
    </Button>
  );
}
