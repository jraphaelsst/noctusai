/** Tab "Réguas de reengajamento" (NOVO): list + "Nova régua de reengajamento". */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertCircle, Loader2, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Drawer } from "./Drawer";
import { mensagemErroReengajamento, useCriarRegua, useReguas } from "@/hooks/useLaisReengajamento";
import { LAIS_PAGES } from "@/nav/lais";

export function operacaoTexto(r: { aluguel: boolean; compra: boolean }): string {
  if (r.aluguel && r.compra) return "Aluguel e compra";
  if (r.aluguel) return "Aluguel";
  if (r.compra) return "Compra";
  return "Nenhuma operação";
}

export function reguaHref(id: string): string {
  return `${LAIS_PAGES.reengajamento.href}/reguas/${id}`;
}

function NovaReguaDrawer({ onClose }: { onClose: () => void }) {
  const criar = useCriarRegua();
  const nav = useNavigate();
  const [nome, setNome] = useState("");
  const [aluguel, setAluguel] = useState(true);
  const [compra, setCompra] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const invalido = !nome.trim() || (!aluguel && !compra);

  function enviar() {
    setErro(null);
    criar.mutate(
      { nome: nome.trim(), aluguel, compra },
      {
        onSuccess: (r) => {
          toast.success("Régua criada");
          onClose();
          nav(reguaHref(r.id));
        },
        onError: (e) => setErro(mensagemErroReengajamento(e, "Não foi possível criar a régua.")),
      },
    );
  }
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="nova-regua-nome">Nome da régua</Label>
        <Input id="nova-regua-nome" value={nome} maxLength={80} onChange={(e) => setNome(e.target.value)} />
      </div>
      <div className="space-y-2">
        <Label>Operação</Label>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={aluguel} onCheckedChange={(v) => setAluguel(v === true)} aria-label="Aluguel" /> Aluguel
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={compra} onCheckedChange={(v) => setCompra(v === true)} aria-label="Compra" /> Compra
        </label>
      </div>
      {erro && (
        <p role="alert" className="text-sm text-destructive">
          {erro}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button onClick={enviar} disabled={invalido || criar.isPending}>
          {criar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          Criar
        </Button>
      </div>
    </div>
  );
}

export function ReguasTab({ isAdmin }: { isAdmin: boolean }) {
  const q = useReguas();
  const nav = useNavigate();
  const [novo, setNovo] = useState(false);
  const showSkeleton = q.isPending && !q.data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Sequências de até 3 tentativas de contato, que começam depois do reengajamento padrão.
        </p>
        {isAdmin && (
          <Button size="sm" onClick={() => setNovo(true)}>
            <Plus className="mr-1 h-4 w-4" /> Nova régua de reengajamento
          </Button>
        )}
      </div>
      {showSkeleton ? (
        <div className="space-y-3" data-testid="reguas-skeleton">
          {[0, 1].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : !q.data ? (
        <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground" data-testid="reguas-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as réguas.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            Tentar de novo
          </Button>
        </div>
      ) : q.data.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground" data-testid="reguas-vazio">
          Nenhuma régua de reengajamento criada ainda.
        </p>
      ) : (
        <ul className="space-y-3">
          {q.data.map((r) => (
            <li key={r.id}>
              <Card
                role="link"
                tabIndex={0}
                className="cursor-pointer hover:bg-muted/40"
                data-testid={`regua-${r.id}`}
                onClick={() => nav(reguaHref(r.id))}
                onKeyDown={(e) => e.key === "Enter" && nav(reguaHref(r.id))}
              >
                <CardContent className="flex items-center justify-between py-4">
                  <div>
                    <p className="font-medium">{r.nome}</p>
                    <p className="text-xs text-muted-foreground">{operacaoTexto(r)}</p>
                  </div>
                  <Badge variant={r.ativa ? "default" : "secondary"}>{r.ativa ? "Ativa" : "Inativa"}</Badge>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
      {novo && (
        <Drawer open onOpenChange={(o) => !o && setNovo(false)} title="Nova régua de reengajamento" testId="drawer-nova-regua">
          <NovaReguaDrawer onClose={() => setNovo(false)} />
        </Drawer>
      )}
    </div>
  );
}
