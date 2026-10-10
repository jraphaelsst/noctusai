/**
 * Gerar headlines sobre Assuntos virais (contract §7.7, §4.4 #20 `form_viral`).
 * Step 1 "Selecionar Assunto": approved viral topics (≤ 5) and/or a free subject.
 * Step 2 "Tom de Comunicação": 6 radios → Gerar Headlines.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { usePerfisMonitorados } from "@/hooks/geracao/useBiblioteca";
import { useCriarLote, type LoteCreate } from "@/hooks/geracao/useHeadlines";
import { useTaxonomias } from "@/hooks/geracao/useTaxonomias";
import { useAssuntosVirais } from "@/hooks/useAssuntosVirais";
import type { HeadlineLote } from "@/types/geracao";
import { alternarEm, mensagemErro } from "./lote";

const ASSUNTO_MAX = 300;
const ASSUNTOS_MAX = 5;

interface Props {
  marcaId: string | null;
  bloqueado?: boolean;
  onCriado: (lote: HeadlineLote) => void;
}

export function FormViral({ marcaId, bloqueado, onCriado }: Props) {
  const assuntosQ = useAssuntosVirais(marcaId, "approved");
  const taxQ = useTaxonomias();
  const perfisQ = usePerfisMonitorados();
  const criar = useCriarLote();

  const [passo, setPasso] = useState<1 | 2>(1);
  const [assuntoIds, setAssuntoIds] = useState<string[]>([]);
  const [livre, setLivre] = useState("");
  const [tom, setTom] = useState<number | null>(null);
  const [refTipo, setRefTipo] = useState<"" | "perfil" | "formato">("");
  const [perfilIds, setPerfilIds] = useState<string[]>([]);
  const [formatoIds, setFormatoIds] = useState<number[]>([]);

  const livreLimpo = livre.trim();
  const temAssunto = assuntoIds.length > 0 || livreLimpo.length > 0;
  const podeGerar = !!marcaId && temAssunto && !criar.isPending && !bloqueado;
  const perfis = (perfisQ.data ?? []).filter((p) => p.status === "ativo" || p.virais > 0);

  async function gerar() {
    if (!podeGerar || !marcaId) return;
    const body: LoteCreate = {
      marca_id: marcaId,
      origem: "form_viral",
      ...(assuntoIds.length ? { assunto_ids: assuntoIds } : {}),
      ...(livreLimpo ? { assunto_livre: livreLimpo } : {}),
      ...(tom != null ? { tom } : {}),
      ...(refTipo === "perfil" && perfilIds.length
        ? { referencia: { tipo: "perfil" as const, perfil_ids: perfilIds } }
        : refTipo === "formato" && formatoIds.length
          ? { referencia: { tipo: "formato" as const, formato_ids: formatoIds } }
          : {}),
      criatividade: "equilibrado",
    };
    try {
      onCriado(await criar.mutateAsync(body));
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível gerar as headlines."));
    }
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (passo === 1) setPasso(2);
        else void gerar();
      }}
    >
      {passo === 1 ? (
        <>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Assuntos Virais:</legend>
            {assuntosQ.showSkeleton && <Skeleton className="h-16 w-full" />}
            {assuntosQ.isError && !assuntosQ.data && (
              <p role="alert" className="text-sm text-destructive">
                Não foi possível carregar os assuntos virais.{" "}
                <button type="button" className="underline" onClick={() => assuntosQ.refetch()}>
                  Tentar novamente
                </button>
              </p>
            )}
            {assuntosQ.data && assuntosQ.items.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Nenhum assunto viral disponível no momento. Digite abaixo um assunto personalizado…
              </p>
            )}
            {assuntosQ.items.map((a) => (
              <label key={a.id} className="flex items-start gap-2 text-sm">
                <Checkbox
                  checked={assuntoIds.includes(a.id)}
                  disabled={!assuntoIds.includes(a.id) && assuntoIds.length >= ASSUNTOS_MAX}
                  onCheckedChange={() => setAssuntoIds((s) => alternarEm(s, a.id, ASSUNTOS_MAX))}
                  aria-label={a.topic}
                />
                <span>{a.topic}</span>
              </label>
            ))}
            <p className="text-xs text-muted-foreground">Até {ASSUNTOS_MAX} assuntos.</p>
          </fieldset>

          <div className="space-y-1.5">
            <Label htmlFor="hl-livre">Sobre o que você deseja falar:</Label>
            <Input
              id="hl-livre"
              maxLength={ASSUNTO_MAX}
              placeholder="Digite um assunto personalizado"
              value={livre}
              onChange={(e) => setLivre(e.target.value)}
            />
          </div>

          <fieldset className="space-y-2 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Opções Avançadas</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              {(
                [
                  ["perfil", "Use perfis como referência"],
                  ["formato", "Formato de Roteiro"],
                ] as const
              ).map(([v, rotulo]) => (
                <label key={v} className="flex items-center gap-2">
                  <input type="radio" name="hlv-ref" checked={refTipo === v} onChange={() => setRefTipo(v)} />
                  {rotulo}
                </label>
              ))}
              {refTipo && (
                <button type="button" className="text-xs underline" onClick={() => setRefTipo("")}>
                  Limpar
                </button>
              )}
            </div>
            {refTipo === "perfil" &&
              perfis.map((p) => (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={perfilIds.includes(p.id)}
                    disabled={!perfilIds.includes(p.id) && perfilIds.length >= 2}
                    onCheckedChange={() => setPerfilIds((s) => alternarEm(s, p.id, 2))}
                    aria-label={`@${p.handle}`}
                  />
                  @{p.handle}
                </label>
              ))}
            {refTipo === "formato" &&
              taxQ.data?.formatos.map((f) => (
                <label key={f.id} className="flex items-center gap-2 text-sm" title={f.definicao}>
                  <Checkbox
                    checked={formatoIds.includes(f.id)}
                    disabled={!formatoIds.includes(f.id) && formatoIds.length >= 3}
                    onCheckedChange={() => setFormatoIds((s) => alternarEm(s, f.id, 3))}
                    aria-label={f.nome}
                  />
                  {f.nome}
                </label>
              ))}
          </fieldset>

          <Button type="submit" disabled={!temAssunto}>
            Selecionar Assunto
          </Button>
        </>
      ) : (
        <>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Tom de Comunicação:</legend>
            {taxQ.showSkeleton && <Skeleton className="h-24 w-full" />}
            {taxQ.isError && !taxQ.data && (
              <p role="alert" className="text-sm text-destructive">
                Não foi possível carregar os tons.{" "}
                <button type="button" className="underline" onClick={() => taxQ.refetch()}>
                  Tentar novamente
                </button>
              </p>
            )}
            {taxQ.data?.tons.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-sm">
                <input type="radio" name="hlv-tom" checked={tom === t.id} onChange={() => setTom(t.id)} />
                {t.nome}
              </label>
            ))}
          </fieldset>
          {bloqueado && (
            <p className="text-xs text-muted-foreground">Já existe uma geração em andamento — aguarde terminar para gerar outra.</p>
          )}
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => setPasso(1)}>
              Voltar
            </Button>
            <Button type="submit" disabled={!podeGerar}>
              {criar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} Gerar Headlines
            </Button>
          </div>
        </>
      )}
    </form>
  );
}
