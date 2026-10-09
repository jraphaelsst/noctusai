/**
 * "Inserir itens na pesquisa" — one item per line. A chosen variable saves the
 * lines manually (approved); no variable = "Classificar com IA" (pending, then a
 * result view). Contract §4.
 */
import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useAdicionarItens,
  useClassificarItens,
  type ClassificarResult,
  type PesquisaVariable,
} from "@/hooks/usePesquisa";
import { VariavelSelect } from "./VariavelSelect";

const MAX_LINHAS_MANUAL = 200;
const MAX_CHARS_IA = 20_000;
const MAX_CHARS_ITEM = 500;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string;
  variaveis: PesquisaVariable[];
  /** Variable preselected from the page filter ("" = classify with AI). */
  variavelInicial: string;
}

type Resultado =
  | { modo: "ia"; data: ClassificarResult }
  | { modo: "manual"; saved: number; skipped: number };

export function AdicionarItensModal({ open, onOpenChange, marcaId, variaveis, variavelInicial }: Props) {
  const [texto, setTexto] = useState("");
  const [variavel, setVariavel] = useState(variavelInicial);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const adicionar = useAdicionarItens();
  const classificar = useClassificarItens();

  useEffect(() => {
    if (open) {
      setTexto("");
      setVariavel(variavelInicial);
      setResultado(null);
    }
  }, [open, variavelInicial]);

  const linhas = texto
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const modoIA = variavel === "";
  const processando = adicionar.isPending || classificar.isPending;
  const labelDe = (slug: string) => variaveis.find((v) => v.slug === slug)?.label ?? slug;

  const itemLongo = linhas.some((l) => l.length > MAX_CHARS_ITEM);
  const excedeu = modoIA ? texto.length > MAX_CHARS_IA : linhas.length > MAX_LINHAS_MANUAL;
  const erroValidacao = itemLongo
    ? `Cada item pode ter no máximo ${MAX_CHARS_ITEM} caracteres.`
    : excedeu
      ? modoIA
        ? `O texto pode ter no máximo ${MAX_CHARS_IA.toLocaleString("pt-BR")} caracteres.`
        : `Máximo de ${MAX_LINHAS_MANUAL} itens por vez.`
      : null;
  const podeSalvar = linhas.length > 0 && !erroValidacao && !processando;

  async function salvar() {
    if (!podeSalvar) return;
    try {
      if (modoIA) {
        const data = await classificar.mutateAsync({ marca_id: marcaId, text: linhas.join("\n") });
        setResultado({ modo: "ia", data });
        toast.success(`${data.saved} item(ns) classificado(s) e enviado(s) para aprovação.`);
      } else {
        const data = await adicionar.mutateAsync({ marca_id: marcaId, variable_slug: variavel, lines: linhas });
        setResultado({ modo: "manual", saved: data.saved, skipped: data.skipped });
        toast.success(`${data.saved} item(ns) adicionado(s) à pesquisa.`);
      }
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "Não foi possível salvar os itens.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !processando && onOpenChange(o)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Inserir itens na pesquisa</DialogTitle>
          <DialogDescription>
            Cole um item por linha. Escolha uma variável para salvar direto, ou deixe a IA classificar.
          </DialogDescription>
        </DialogHeader>

        {processando && modoIA ? (
          <div role="status" className="flex flex-col items-center gap-3 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
            Classificando com IA…
          </div>
        ) : resultado ? (
          <ResultadoView resultado={resultado} labelDe={labelDe} />
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="pesquisa-add-variavel">Variável</Label>
              <VariavelSelect
                id="pesquisa-add-variavel"
                ariaLabel="Variável de destino"
                value={variavel}
                onChange={setVariavel}
                variaveis={variaveis}
                vazioRotulo="Classificar com IA"
                className="w-full"
              />
              {modoIA && (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5" />
                  A IA distribui cada linha na variável certa; os itens ficam pendentes até você aprovar.
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pesquisa-add-texto">Itens (um por linha)</Label>
              <Textarea
                id="pesquisa-add-texto"
                rows={10}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                    e.preventDefault();
                    void salvar();
                  }
                }}
                placeholder="Um item por linha…"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{linhas.length} item(ns)</span>
                <span>Ctrl+Enter para salvar</span>
              </div>
              {erroValidacao && (
                <p role="alert" className="text-xs text-destructive">
                  {erroValidacao}
                </p>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          {resultado ? (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  setResultado(null);
                  setTexto("");
                }}
              >
                Inserir mais
              </Button>
              <Button onClick={() => onOpenChange(false)}>Fechar</Button>
            </>
          ) : (
            <>
              <Button variant="outline" disabled={processando} onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button disabled={!podeSalvar} onClick={() => void salvar()}>
                {modoIA ? "Classificar e salvar" : "Salvar"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResultadoView({ resultado, labelDe }: { resultado: Resultado; labelDe: (slug: string) => string }) {
  const saved = resultado.modo === "ia" ? resultado.data.saved : resultado.saved;
  const skipped = resultado.modo === "ia" ? resultado.data.skipped : resultado.skipped;
  return (
    <div className="space-y-4 text-sm" data-testid="pesquisa-resultado">
      <p>
        <strong>{saved}</strong> salvo(s) · <strong>{skipped}</strong> ignorado(s) (já existiam).
      </p>
      {resultado.modo === "ia" && (
        <>
          {Object.entries(resultado.data.classified).map(([slug, itens]) => (
            <div key={slug}>
              <h4 className="mb-1 font-medium">
                {labelDe(slug)} ({itens.length})
              </h4>
              <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                {itens.map((i, idx) => (
                  <li key={`${slug}-${idx}`}>{i}</li>
                ))}
              </ul>
            </div>
          ))}
          {resultado.data.unclassified.length > 0 && (
            <div>
              <h4 className="mb-1 font-medium text-orange-600">
                Não classificados ({resultado.data.unclassified.length})
              </h4>
              <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                {resultado.data.unclassified.map((i, idx) => (
                  <li key={`u-${idx}`}>{i}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
