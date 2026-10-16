/** Régua page › card "Tentativas de contato n/3" + per-attempt drawer. */
import { useState } from "react";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useConfirm } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Drawer } from "./Drawer";
import {
  MAX_TENTATIVAS,
  TEXTO_MAX,
  mensagemErroReengajamento,
  useAtualizarTentativa,
  useCriarTentativa,
  useExcluirTentativa,
  type EsperaUnidade,
  type Regua,
  type ReguaTentativa,
} from "@/hooks/useLaisReengajamento";

const UNIDADES: { v: EsperaUnidade; l: string }[] = [
  { v: "minutos", l: "minutos" },
  { v: "horas", l: "horas" },
  { v: "dias", l: "dias" },
];

export function esperaTexto(t: Pick<ReguaTentativa, "espera_valor" | "espera_unidade">): string {
  return `${t.espera_valor} ${t.espera_unidade}`;
}

function TentativaDrawer({
  reguaId,
  tentativa,
  onClose,
}: {
  reguaId: string;
  tentativa: ReguaTentativa | null;
  onClose: () => void;
}) {
  const criar = useCriarTentativa(reguaId);
  const atualizar = useAtualizarTentativa(reguaId);
  const [valor, setValor] = useState(String(tentativa?.espera_valor ?? 1));
  const [unidade, setUnidade] = useState<EsperaUnidade>(tentativa?.espera_unidade ?? "dias");
  const [texto, setTexto] = useState(tentativa?.texto ?? "");
  const [ativa, setAtiva] = useState(tentativa?.ativa ?? true);
  const [erro, setErro] = useState<string | null>(null);
  const n = Number(valor);
  const invalido = !Number.isInteger(n) || n < 1 || !texto.trim() || texto.length > TEXTO_MAX;
  const pending = criar.isPending || atualizar.isPending;

  function enviar() {
    setErro(null);
    const body = { espera_valor: n, espera_unidade: unidade, texto: texto.trim(), template_id: null, ativa };
    const opts = {
      onSuccess: () => {
        toast.success("Tentativa de contato salva");
        onClose();
      },
      onError: (e: unknown) => setErro(mensagemErroReengajamento(e, "Não foi possível salvar a tentativa.")),
    };
    if (tentativa) atualizar.mutate({ id: tentativa.id, body }, opts);
    else criar.mutate(body, opts);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label htmlFor="tent-ativa">Tentativa ativa</Label>
        <Switch id="tent-ativa" checked={ativa} onCheckedChange={setAtiva} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="tent-valor">Espera</Label>
        <div className="flex gap-2">
          <Input
            id="tent-valor"
            type="number"
            min={1}
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            className="w-24"
          />
          <select
            aria-label="Unidade da espera"
            className="h-9 flex-1 rounded-md border bg-background px-2 text-sm"
            value={unidade}
            onChange={(e) => setUnidade(e.target.value as EsperaUnidade)}
          >
            {UNIDADES.map((u) => (
              <option key={u.v} value={u.v}>
                {u.l}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="space-y-2">
        <Label>Mensagem</Label>
        <div className="flex gap-2 text-sm">
          <Button type="button" size="sm" variant="default" aria-pressed="true">
            Texto
          </Button>
          <span title="disponível com a API oficial" className="inline-block">
            <Button type="button" size="sm" variant="outline" disabled aria-label="Modelo">
              Modelo
            </Button>
          </span>
        </div>
        <Textarea
          aria-label="Texto da mensagem"
          rows={6}
          value={texto}
          maxLength={TEXTO_MAX}
          onChange={(e) => setTexto(e.target.value)}
        />
        <p className="text-xs text-muted-foreground" data-testid="texto-contador">
          {texto.length}/{TEXTO_MAX}
        </p>
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
        <Button onClick={enviar} disabled={invalido || pending}>
          {pending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          Salvar
        </Button>
      </div>
    </div>
  );
}

export function TentativasCard({ regua, isAdmin }: { regua: Regua; isAdmin: boolean }) {
  const confirm = useConfirm();
  const excluir = useExcluirTentativa(regua.id);
  const [editando, setEditando] = useState<ReguaTentativa | "nova" | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const lista = [...(regua.tentativas ?? [])].sort((a, b) => a.ordem - b.ordem);
  const cheia = lista.length >= MAX_TENTATIVAS;

  async function remover(t: ReguaTentativa) {
    setErro(null);
    if (
      !(await confirm({
        title: "Excluir tentativa de contato?",
        description: "Esta ação não poderá ser desfeita.",
        confirmLabel: "Excluir",
        tone: "danger",
      }))
    )
      return;
    excluir.mutate(t.id, {
      onSuccess: () => toast.success("Tentativa excluída"),
      onError: (e) => setErro(mensagemErroReengajamento(e, "Não foi possível excluir a tentativa.")),
    });
  }

  return (
    <Card data-testid="card-tentativas">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">
          Tentativas de contato {lista.length}/{MAX_TENTATIVAS}
        </CardTitle>
        {isAdmin && (
          <Button size="sm" onClick={() => setEditando("nova")} disabled={cheia} title={cheia ? "Limite de 3 tentativas" : undefined}>
            <Plus className="mr-1 h-4 w-4" /> Nova tentativa de contato
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {lista.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="tentativas-vazio">
            Nenhuma tentativa de contato ainda. Adicione ao menos uma para poder ativar a régua.
          </p>
        ) : (
          <ul className="space-y-2">
            {lista.map((t) => (
              <li key={t.id} className="flex items-center justify-between rounded-md border p-3" data-testid={`tentativa-${t.id}`}>
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    Tentativa {t.ordem} · após {esperaTexto(t)}
                    {!t.ativa && <span className="ml-2 text-xs text-muted-foreground">(inativa)</span>}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">{t.texto ?? "Sem modelo"}</p>
                </div>
                {isAdmin && (
                  <div className="flex gap-1">
                    <Button size="icon" variant="ghost" aria-label={`Editar tentativa ${t.ordem}`} onClick={() => setEditando(t)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button size="icon" variant="ghost" aria-label={`Excluir tentativa ${t.ordem}`} onClick={() => remover(t)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {erro && (
          <p role="alert" className="text-sm text-destructive">
            {erro}
          </p>
        )}
      </CardContent>
      {editando && (
        <Drawer
          open
          onOpenChange={(o) => !o && setEditando(null)}
          title={editando === "nova" ? "Nova tentativa de contato" : "Editar tentativa de contato"}
          testId="drawer-tentativa"
        >
          <TentativaDrawer
            reguaId={regua.id}
            tentativa={editando === "nova" ? null : editando}
            onClose={() => setEditando(null)}
          />
        </Drawer>
      )}
    </Card>
  );
}
