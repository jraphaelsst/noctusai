/**
 * Novo post (§6.1): marca, título (optional when a headline is chosen), optional headline
 * (the marca's Favoritas, then Sugeridas, only those not yet bound to a post), conta de
 * destino (the marca's connected Instagram accounts; hidden when there is only one, which
 * is then sent) and the planned dates. The server decides the stage.
 */
import { useState } from "react";
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
import { useCriarPost } from "@/hooks/geracao/useEsteira";
import { useHeadlinesLista } from "@/hooks/geracao/useHeadlines";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import type { Marca } from "@/hooks/useMarcas";
import { mensagemErroServidor } from "@/lib/erroServidor";
import type { PostDetalhe } from "@/types/esteira";

export interface NovoPostDialogProps {
  open: boolean;
  marcas: Marca[];
  /** Prefilled from the board filter. */
  marcaIdInicial?: string;
  onClose: () => void;
  onCriado?: (post: PostDetalhe) => void;
}

export function NovoPostDialog({ open, marcas, marcaIdInicial, onClose, onCriado }: NovoPostDialogProps) {
  const criar = useCriarPost();
  const [marcaId, setMarcaId] = useState("");
  const [titulo, setTitulo] = useState("");
  const [gravacao, setGravacao] = useState("");
  const [entrega, setEntrega] = useState("");
  const [headlineId, setHeadlineId] = useState("");
  const [contaEscolhida, setContaEscolhida] = useState("");

  const marcaEscolhida = marcaId || marcaIdInicial || marcas[0]?.id || "";
  const favoritas = useHeadlinesLista(marcaEscolhida || null, "favoritas");
  const sugeridas = useHeadlinesLista(marcaEscolhida || null, "sugeridas");
  const livres = [
    ...(favoritas.data?.items ?? []).map((h) => ({ h, grupo: "Favoritas" })),
    ...(sugeridas.data?.items ?? []).map((h) => ({ h, grupo: "Sugeridas" })),
  ].filter(({ h }) => !h.post);
  const headlineValida = livres.some(({ h }) => h.id === headlineId) ? headlineId : "";

  const contasQ = useIntegrationAccounts({ provider: "instagram", marcaId: marcaEscolhida || undefined });
  const contas = marcaEscolhida ? (contasQ.data ?? []) : [];
  const contaId = contas.length === 1 ? contas[0].id : contas.some((c) => c.id === contaEscolhida) ? contaEscolhida : "";

  const pode =
    Boolean(marcaEscolhida) && (titulo.trim().length > 0 || Boolean(headlineValida)) && !criar.isPending;

  function enviar() {
    criar.mutate(
      {
        marca_id: marcaEscolhida,
        titulo: titulo.trim() || undefined,
        headline_id: headlineValida || undefined,
        conta_id: contaId || undefined,
        gravacao_em: gravacao || undefined,
        data_entrega: entrega || undefined,
      },
      {
        onSuccess: (post) => {
          toast.success("Post criado.");
          setTitulo("");
          setHeadlineId("");
          setGravacao("");
          setEntrega("");
          onCriado?.(post);
          onClose();
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível criar o post.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Novo post</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <label className="block space-y-1">
            <span>Marca</span>
            <select
              aria-label="Marca do post"
              value={marcaEscolhida}
              onChange={(e) => setMarcaId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {marcas.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span>Começar com uma headline (opcional)</span>
            <select
              aria-label="Headline do post"
              value={headlineValida}
              onChange={(e) => setHeadlineId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Sem headline</option>
              {["Favoritas", "Sugeridas"].map((g) => (
                <optgroup key={g} label={g}>
                  {livres
                    .filter((x) => x.grupo === g)
                    .map(({ h }) => (
                      <option key={h.id} value={h.id}>
                        {h.texto.slice(0, 90)}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span>Título</span>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Título do reel (opcional com headline)" />
          </label>
          {contas.length > 1 && (
            <label className="block space-y-1">
              <span>Conta de destino</span>
              <select
                aria-label="Conta de destino"
                value={contaId}
                onChange={(e) => setContaEscolhida(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">Definir depois</option>
                {contas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.account_label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="grid grid-cols-2 gap-3">
            <label className="block space-y-1">
              <span>Gravação prevista</span>
              <Input type="date" value={gravacao} onChange={(e) => setGravacao(e.target.value)} />
            </label>
            <label className="block space-y-1">
              <span>Postagem prevista</span>
              <Input type="date" value={entrega} onChange={(e) => setEntrega(e.target.value)} />
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={!pode} onClick={enviar}>
            Criar post
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
