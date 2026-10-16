/** Régua page › card "Regras" + [Editar] drawer (switch, nome, operação, excluir). */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useConfirm } from "@noctusai/lib/components";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Drawer } from "./Drawer";
import { operacaoTexto } from "./ReguasTab";
import {
  mensagemErroReengajamento,
  useAtivarRegua,
  useAtualizarRegua,
  useExcluirRegua,
  type Regua,
} from "@/hooks/useLaisReengajamento";
import { LAIS_PAGES } from "@/nav/lais";

function EditarDrawer({ regua, onClose }: { regua: Regua; onClose: () => void }) {
  const confirm = useConfirm();
  const nav = useNavigate();
  const atualizar = useAtualizarRegua(regua.id);
  const ativar = useAtivarRegua(regua.id);
  const excluir = useExcluirRegua();
  const [ativa, setAtiva] = useState(regua.ativa);
  const [nome, setNome] = useState(regua.nome);
  const [aluguel, setAluguel] = useState(regua.aluguel);
  const [compra, setCompra] = useState(regua.compra);
  const [erro, setErro] = useState<string | null>(null);
  const invalido = !nome.trim() || (!aluguel && !compra);
  const ocupado = atualizar.isPending || ativar.isPending || excluir.isPending;

  async function salvar() {
    setErro(null);
    try {
      await atualizar.mutateAsync({ nome: nome.trim(), aluguel, compra });
      if (ativa !== regua.ativa) await ativar.mutateAsync(ativa);
      toast.success("Régua salva");
      onClose();
    } catch (e) {
      setErro(mensagemErroReengajamento(e, "Não foi possível salvar a régua."));
    }
  }

  async function remover() {
    if (
      !(await confirm({
        title: "Excluir régua?",
        description: "As tentativas de contato desta régua também serão excluídas.",
        confirmLabel: "Excluir",
        tone: "danger",
      }))
    )
      return;
    excluir.mutate(regua.id, {
      onSuccess: () => {
        toast.success("Régua excluída");
        onClose();
        nav(`${LAIS_PAGES.reengajamento.href}?tab=reguas`);
      },
      onError: (e) => setErro(mensagemErroReengajamento(e, "Não foi possível excluir a régua.")),
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label htmlFor="regua-ativa">Ativar régua de reengajamento</Label>
        <Switch id="regua-ativa" checked={ativa} onCheckedChange={setAtiva} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="regua-nome">Nome da régua</Label>
        <Input id="regua-nome" value={nome} maxLength={80} onChange={(e) => setNome(e.target.value)} />
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
      <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground space-y-1">
        <p>A régua começa depois da última tentativa do reengajamento padrão.</p>
        <p>Leads que encerraram a conversa não são contatados.</p>
        <p>A Julia pode reescrever o texto da mensagem com as próprias palavras.</p>
        <p>Somente leads que interagiram e depois pararam de responder entram na régua.</p>
      </div>
      {erro && (
        <p role="alert" className="text-sm text-destructive">
          {erro}
        </p>
      )}
      <div className="flex justify-between gap-2">
        <Button variant="destructive" onClick={remover} disabled={ocupado}>
          Excluir régua
        </Button>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={salvar} disabled={invalido || ocupado}>
            {ocupado && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Salvar
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ReguaRegrasCard({ regua, isAdmin }: { regua: Regua; isAdmin: boolean }) {
  const [aberto, setAberto] = useState(false);
  return (
    <Card data-testid="card-regras">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Regras</CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant={regua.ativa ? "default" : "secondary"}>{regua.ativa ? "Ativa" : "Inativa"}</Badge>
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={() => setAberto(true)}>
              Editar
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <p>
          <span className="text-muted-foreground">Operação: </span>
          {operacaoTexto(regua)}
        </p>
        <p>
          <span className="text-muted-foreground">Período: </span>
          Das 8h às 20h
        </p>
      </CardContent>
      {aberto && (
        <Drawer open onOpenChange={(o) => !o && setAberto(false)} title="Editar régua de reengajamento" testId="drawer-regra">
          <EditarDrawer regua={regua} onClose={() => setAberto(false)} />
        </Drawer>
      )}
    </Card>
  );
}
