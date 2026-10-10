/**
 * "Gerar headline" wizard from a viral (contract §7.3), 3 steps:
 * 1 Escolha os assuntos virais · 2 Revisar e Enviar · 3 Criar Headline
 * (POST /headlines/lotes `origem:'biblioteca'`, §4.4 #20).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAssuntosVirais } from "@/hooks/useAssuntosVirais";
import { useGerarHeadlineViral } from "@/hooks/geracao/useBiblioteca";

export const ASSUNTOS_MAX = 5;
export const ASSUNTO_LIVRE_MAX = 300;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  marcaId: string;
  viralId: string;
  handle: string;
}

type Passo = 1 | 2 | 3;

export function GerarHeadlineWizard({ open, onOpenChange, marcaId, viralId, handle }: Props) {
  const [passo, setPasso] = useState<Passo>(1);
  const [ids, setIds] = useState<string[]>([]);
  const [livre, setLivre] = useState("");
  const [enviada, setEnviada] = useState(false);

  const assuntosQ = useAssuntosVirais(open ? marcaId : null, "approved");
  const gerar = useGerarHeadlineViral();

  useEffect(() => {
    if (open) {
      setPasso(1);
      setIds([]);
      setLivre("");
      setEnviada(false);
    }
  }, [open, viralId]);

  const assuntos = assuntosQ.items;
  const escolhidos = assuntos.filter((a) => ids.includes(a.id));
  const livreLimpo = livre.trim();

  function alternar(id: string, marcado: boolean) {
    setIds((cur) => {
      if (!marcado) return cur.filter((x) => x !== id);
      return cur.length >= ASSUNTOS_MAX || cur.includes(id) ? cur : [...cur, id];
    });
  }

  async function criar() {
    try {
      await gerar.mutateAsync({
        marca_id: marcaId,
        viral_id: viralId,
        ...(ids.length > 0 ? { assunto_ids: ids } : {}),
        ...(livreLimpo ? { assunto_livre: livreLimpo } : {}),
      });
      setEnviada(true);
      setPasso(3);
    } catch (e) {
      toast.error(
        e instanceof Error && e.message ? e.message : "Não foi possível criar a headline.",
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !gerar.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-xl">
        {enviada ? (
          <>
            <DialogHeader>
              <DialogTitle>Headline enviada para criação!</DialogTitle>
              <DialogDescription>
                Em 1 ou 2 minutos sua headline será criada e aparecerá em Headlines Sugeridas.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button asChild>
                <Link to="/media-creation/headlines/sugeridas">Ver Headlines Sugeridas</Link>
              </Button>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Continuar na Biblioteca
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Gerar headline a partir de @{handle}</DialogTitle>
              <DialogDescription>Passo {passo} de 3</DialogDescription>
            </DialogHeader>

            {passo === 1 && (
              <section className="flex flex-col gap-3">
                <h3 className="text-sm font-semibold">Escolha os assuntos virais</h3>
                <p className="text-xs text-muted-foreground">
                  {ids.length}/{ASSUNTOS_MAX} selecionados
                </p>
                {assuntosQ.showSkeleton ? (
                  <Skeleton className="h-24 w-full" />
                ) : assuntosQ.isError ? (
                  <div className="text-sm text-destructive">
                    Não foi possível carregar os assuntos.{" "}
                    <Button variant="link" className="h-auto p-0" onClick={() => assuntosQ.refetch()}>
                      Tentar novamente
                    </Button>
                  </div>
                ) : assuntos.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Esta marca ainda não tem assuntos virais aprovados. Escreva um abaixo ou
                    aprove assuntos em Minha Pesquisa.
                  </p>
                ) : (
                  <ul className="max-h-56 space-y-1 overflow-y-auto">
                    {assuntos.map((a) => {
                      const marcado = ids.includes(a.id);
                      return (
                        <li key={a.id}>
                          <label className="flex items-center gap-2 text-sm">
                            <Checkbox
                              checked={marcado}
                              disabled={!marcado && ids.length >= ASSUNTOS_MAX}
                              onCheckedChange={(v) => alternar(a.id, v === true)}
                            />
                            {a.topic}
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="wiz-livre">Escreva o assunto viral manualmente (opcional)</Label>
                  <Textarea
                    id="wiz-livre"
                    maxLength={ASSUNTO_LIVRE_MAX}
                    value={livre}
                    onChange={(e) => setLivre(e.target.value)}
                  />
                </div>
              </section>
            )}

            {passo === 2 && (
              <section className="flex flex-col gap-2 text-sm">
                <h3 className="font-semibold">Revisar e Enviar</h3>
                <p>
                  <span className="text-muted-foreground">Viral de: </span>@{handle}
                </p>
                <div>
                  <span className="text-muted-foreground">Assuntos: </span>
                  {escolhidos.length === 0 && !livreLimpo
                    ? "nenhum (a IA escolhe)"
                    : [...escolhidos.map((a) => a.topic), ...(livreLimpo ? [livreLimpo] : [])].join(
                        " · ",
                      )}
                </div>
              </section>
            )}

            <DialogFooter>
              {passo > 1 && (
                <Button
                  variant="outline"
                  disabled={gerar.isPending}
                  onClick={() => setPasso((p) => (p - 1) as Passo)}
                >
                  Voltar
                </Button>
              )}
              {passo === 1 && <Button onClick={() => setPasso(2)}>Próximo: Revisar e Enviar</Button>}
              {passo === 2 && (
                <Button onClick={criar} disabled={gerar.isPending}>
                  {gerar.isPending ? "Enviando..." : "Criar Headline"}
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
