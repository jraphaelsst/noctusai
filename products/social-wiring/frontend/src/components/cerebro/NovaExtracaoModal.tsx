/**
 * "Nova Extração" modal (contract §6): Nome · Extrair para (brain multi-select +
 * inline "Clique aqui para criar um novo núcleo" → POST /brains) · Transcrição.
 * The `Url:` toggle stays hidden (§10: URL sources are phase 2).
 */
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MAX_CONTEUDO, mensagemErro } from "@/components/cerebro/labels";
import { useCerebroBrains, useCriarBrain } from "@/hooks/useCerebro";
import { useCriarExtracao } from "@/hooks/useExtracoes";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string;
}

export const MAX_ALVOS = 20;

export function NovaExtracaoModal({ open, onOpenChange, marcaId }: Props) {
  const brainsQ = useCerebroBrains(marcaId);
  const brains = brainsQ.data ?? [];
  const criarExtracao = useCriarExtracao();
  const criarBrain = useCriarBrain();

  const [nome, setNome] = useState("");
  const [texto, setTexto] = useState("");
  const [alvos, setAlvos] = useState<string[]>([]);
  const [novoNucleo, setNovoNucleo] = useState(false);
  const [nomeNucleo, setNomeNucleo] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setNome("");
      setTexto("");
      setAlvos([]);
      setNovoNucleo(false);
      setNomeNucleo("");
      setErro(null);
    }
  }, [open]);

  function alternar(id: string) {
    setAlvos((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  async function onCriarNucleo() {
    const name = nomeNucleo.trim();
    if (!name) {
      setErro("Informe o nome do novo núcleo.");
      return;
    }
    try {
      const b = await criarBrain.mutateAsync({ marca_id: marcaId, name });
      setAlvos((cur) => (cur.includes(b.id) ? cur : [...cur, b.id]));
      setNovoNucleo(false);
      setNomeNucleo("");
      setErro(null);
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível criar o núcleo."));
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const name = nome.trim();
    if (!name) return setErro("Informe o nome da extração.");
    if (alvos.length === 0) return setErro("Selecione ao menos um cérebro.");
    if (alvos.length > MAX_ALVOS) return setErro(`Selecione no máximo ${MAX_ALVOS} cérebros.`);
    if (!texto.trim()) return setErro("Cole a transcrição antes de criar.");
    try {
      await criarExtracao.mutateAsync({ marca_id: marcaId, name, brain_ids: alvos, text: texto });
      toast.success("Extração criada.");
      onOpenChange(false);
    } catch (err) {
      setErro(mensagemErro(err, "Não foi possível criar a extração."));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Nova Extração</DialogTitle>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor="extracao-nome">Nome:</Label>
            <Input
              id="extracao-nome"
              value={nome}
              maxLength={120}
              placeholder="ex: Pesquisa 1"
              onChange={(e) => setNome(e.target.value)}
              autoComplete="off"
            />
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Extrair para:</legend>
            {brainsQ.showSkeleton ? (
              <p className="text-sm text-muted-foreground">Carregando cérebros…</p>
            ) : (
              <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2">
                {brains.map((b) => (
                  <li key={b.id}>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={alvos.includes(b.id)}
                        onChange={() => alternar(b.id)}
                        aria-label={b.name}
                      />
                      {b.name}
                    </label>
                  </li>
                ))}
              </ul>
            )}
            {novoNucleo ? (
              <div className="flex gap-2">
                <Input
                  aria-label="Nome do novo núcleo"
                  value={nomeNucleo}
                  maxLength={80}
                  placeholder="Ex: Reels Instagram"
                  onChange={(e) => setNomeNucleo(e.target.value)}
                  autoComplete="off"
                />
                <Button type="button" variant="outline" disabled={criarBrain.isPending} onClick={() => void onCriarNucleo()}>
                  {criarBrain.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                  Criar núcleo
                </Button>
              </div>
            ) : (
              <button
                type="button"
                className="text-sm text-primary underline underline-offset-2"
                onClick={() => setNovoNucleo(true)}
              >
                Clique aqui para criar um novo núcleo
              </button>
            )}
          </fieldset>

          <div className="space-y-1.5">
            <Label htmlFor="extracao-texto">Transcrição:</Label>
            <Textarea
              id="extracao-texto"
              rows={8}
              value={texto}
              maxLength={MAX_CONTEUDO}
              placeholder="Cole aqui sua transcrição..."
              onChange={(e) => setTexto(e.target.value)}
            />
          </div>

          {erro && (
            <p role="alert" className="text-sm text-destructive">
              {erro}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={criarExtracao.isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={criarExtracao.isPending}>
              {criarExtracao.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Criar Transcrição
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
