/**
 * Shared roteiro editing surface (contract §7.8): tabs Roteiro / Fontes da
 * Pesquisa (the latter hidden while `fontes` is NULL), Nome (optional),
 * markdown textarea, Copiar Roteiro, and the optimistic-lock save (#37, 409).
 */
import { useEffect, useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSalvarRoteiro } from "@/hooks/geracao/useRoteiros";
import type { Roteiro } from "@/types/geracao";

export const NOME_MAX = 160;
export const CONTEUDO_MAX = 30_000;
export const MSG_CONFLITO = "O roteiro mudou; recarregue";

function statusDe(e: unknown): number | null {
  const s = (e as { status?: unknown } | null)?.status;
  if (typeof s === "number") return s;
  const m = e instanceof Error ? /^\[(\d+)\]/.exec(e.message) : null;
  return m ? Number(m[1]) : null;
}

export function useEdicaoRoteiro(roteiro: Roteiro | undefined, onSalvo?: (r: Roteiro) => void) {
  const salvar = useSalvarRoteiro();
  const [nome, setNome] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [conflito, setConflito] = useState(false);

  // Re-seed only when the server row really changed (id / versao) — polling must not clobber typing.
  useEffect(() => {
    if (!roteiro) return;
    setNome(roteiro.nome);
    setConteudo(roteiro.conteudo ?? "");
    setConflito(false);
  }, [roteiro?.id, roteiro?.versao]); // eslint-disable-line react-hooks/exhaustive-deps

  const nomeLimpo = nome.trim();
  const alterou = !!roteiro && (nomeLimpo !== roteiro.nome || conteudo !== (roteiro.conteudo ?? ""));
  const valido = nomeLimpo.length > 0 && nomeLimpo.length <= NOME_MAX && conteudo.length <= CONTEUDO_MAX;

  async function salvarAgora(): Promise<Roteiro | null> {
    if (!roteiro || !alterou || !valido) return null;
    try {
      const r = await salvar.mutateAsync({
        id: roteiro.id,
        nome: nomeLimpo !== roteiro.nome ? nomeLimpo : undefined,
        conteudo: conteudo !== (roteiro.conteudo ?? "") ? conteudo : undefined,
        expected_versao: roteiro.versao,
      });
      toast.success("Roteiro atualizado.");
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
            <Button type="button" size="sm" variant="outline" onClick={onRecarregar}>
              Recarregar
            </Button>
          )}
        </div>
      )}
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
              className="font-mono text-sm"
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
