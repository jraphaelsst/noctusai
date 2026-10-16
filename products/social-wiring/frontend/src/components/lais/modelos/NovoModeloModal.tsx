/** "Novo modelo de mensagem" modal — name, category, body ≤1024, parameter chips. */
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CATEGORIAS, CONTEUDO_MAX, PARAMETROS, useCriarModelo, type Categoria } from "@/hooks/useLaisModelos";
import { mensagemErroLais } from "@/hooks/useLaisAgente";

/** Insert `{{token}}` at the caret, respecting the cap (returns null if it would overflow). */
export function inserirParametro(texto: string, token: string, pos: number): { texto: string; pos: number } | null {
  const ins = `{{${token}}}`;
  if (texto.length + ins.length > CONTEUDO_MAX) return null;
  return { texto: texto.slice(0, pos) + ins + texto.slice(pos), pos: pos + ins.length };
}

export function NovoModeloModal({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const criar = useCriarModelo();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState<Categoria>("Outros");
  const [conteudo, setConteudo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const invalido = !nome.trim() || !conteudo.trim();

  function addParam(token: string) {
    const pos = ref.current?.selectionStart ?? conteudo.length;
    const r = inserirParametro(conteudo, token, pos);
    if (!r) return;
    setConteudo(r.texto);
  }
  function enviar() {
    setErro(null);
    criar.mutate(
      { nome: nome.trim(), categoria, conteudo },
      {
        onSuccess: () => {
          toast.success("Modelo criado");
          setNome("");
          setConteudo("");
          setCategoria("Outros");
          onOpenChange(false);
        },
        onError: (e) => setErro(mensagemErroLais(e, "Não foi possível criar o modelo.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="novo-modelo-modal">
        <DialogHeader>
          <DialogTitle>Novo modelo de mensagem</DialogTitle>
          <DialogDescription>Crie um modelo reutilizável para seus disparos.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="modelo-nome">Nome do modelo</Label>
            <Input id="modelo-nome" value={nome} maxLength={80} onChange={(e) => setNome(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="modelo-categoria">Categoria</Label>
            <select
              id="modelo-categoria"
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={categoria}
              onChange={(e) => setCategoria(e.target.value as Categoria)}
            >
              {CATEGORIAS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="modelo-conteudo">Conteúdo da mensagem</Label>
            <Textarea
              id="modelo-conteudo"
              ref={ref}
              rows={5}
              value={conteudo}
              maxLength={CONTEUDO_MAX}
              onChange={(e) => setConteudo(e.target.value.slice(0, CONTEUDO_MAX))}
            />
            <p className="text-right text-xs text-muted-foreground" data-testid="modelo-contador">
              {conteudo.length}/{CONTEUDO_MAX}
            </p>
          </div>
          <div className="space-y-1">
            <Label>Adicionar parâmetros</Label>
            <div className="flex flex-wrap gap-1">
              {PARAMETROS.map((p) => (
                <button
                  key={p.token}
                  type="button"
                  className="rounded-full border px-2 py-0.5 text-xs hover:bg-muted"
                  onClick={() => addParam(p.token)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          {erro && (
            <p role="alert" className="text-sm text-destructive">
              {erro}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button onClick={enviar} disabled={invalido || criar.isPending}>
              Criar
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
