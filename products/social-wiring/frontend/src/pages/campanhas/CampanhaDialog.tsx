/**
 * CampanhaDialog — create / edit one campanha (CONTRACT §1.1).
 *
 * The imóvel picker is the card's `ImovelCodigoPicker` (registry-backed
 * search), used as an "add" box: each pick lands in the list and the picker
 * resets. Server errors surface where they belong:
 *   · 400 — lists the unknown códigos (the backend's own message);
 *   · 409 `veiculacao_em_uso` — inline on the veiculação row it names.
 */
import { useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@noctusai/lib";

import { ImovelCodigoPicker } from "@/components/card/ImovelCodigoPicker";
import { mensagemDoErro } from "@/components/card/mensagemDoErro";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCampanhaMutations,
  type Campanha,
  type VeiculacaoNivel,
} from "@/hooks/useCampanhas";

export const NIVEL_LABEL: Record<VeiculacaoNivel, string> = {
  ad: "Anúncio",
  adset: "Conjunto",
  campaign: "Campanha",
  form: "Formulário",
};

interface VeiculacaoDraft {
  key: number;
  nivel: VeiculacaoNivel;
  ref_codigo: string;
}

export interface CampanhaDialogProps {
  open: boolean;
  /** `null` ⇒ create. */
  campanha: Campanha | null;
  onClose: () => void;
}

export function CampanhaDialog({ open, campanha, onClose }: CampanhaDialogProps) {
  // The parent remounts this per open (key), so initial state IS the draft.
  const [nome, setNome] = useState(campanha?.nome ?? "");
  const [codigos, setCodigos] = useState<string[]>(
    campanha?.imoveis.map((i) => i.codigo) ?? [],
  );
  const [veics, setVeics] = useState<VeiculacaoDraft[]>(
    (campanha?.veiculacoes ?? []).map((v, i) => ({
      key: i,
      nivel: v.nivel,
      ref_codigo: v.ref_codigo,
    })),
  );
  const [proxKey, setProxKey] = useState(veics.length);
  const [erro, setErro] = useState<string | null>(null);
  const [erroVeic, setErroVeic] = useState<string | null>(null);
  const { criar, atualizar } = useCampanhaMutations();
  const salvando = criar.isPending || atualizar.isPending;
  const titulos = new Map((campanha?.imoveis ?? []).map((i) => [i.codigo, i.titulo]));

  const veicsValidas = veics.filter((v) => v.ref_codigo.trim() !== "");
  const podeSalvar = nome.trim() !== "" && !salvando;

  function addCodigo(c: string | null) {
    if (c && !codigos.includes(c)) setCodigos((l) => [...l, c]);
  }

  function addVeic() {
    setVeics((l) => [...l, { key: proxKey, nivel: "ad", ref_codigo: "" }]);
    setProxKey((k) => k + 1);
  }

  function onError(err: unknown) {
    const msg = mensagemDoErro(err, "Não foi possível salvar a campanha.");
    if (err instanceof ApiError && err.status === 409 && err.code === "veiculacao_em_uso") {
      setErro(null);
      setErroVeic(msg);
      return;
    }
    setErroVeic(null);
    setErro(msg);
  }

  function salvar() {
    setErro(null);
    setErroVeic(null);
    const body = {
      nome: nome.trim(),
      imovel_codigos: codigos,
      veiculacoes: veicsValidas.map((v) => ({
        canal: "meta_ads" as const,
        nivel: v.nivel,
        ref_codigo: v.ref_codigo.trim(),
      })),
    };
    const opts = {
      onSuccess: () => {
        toast.success(campanha ? "Campanha atualizada." : "Campanha criada.");
        onClose();
      },
      onError,
    };
    if (campanha) atualizar.mutate({ id: campanha.id, body }, opts);
    else criar.mutate(body, opts);
  }

  // The 409 names the ref that is already in use; pin it to its row.
  const linhaEmUso = (ref: string) =>
    !!erroVeic && ref.trim() !== "" && erroVeic.includes(ref.trim());
  const erroSemLinha =
    !!erroVeic && !veics.some((v) => linhaEmUso(v.ref_codigo));

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !salvando && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="campanha-dialog">
        <DialogHeader>
          <DialogTitle>{campanha ? "Editar campanha" : "Nova campanha"}</DialogTitle>
          <DialogDescription>
            Quando um lead chega por um destes objetos do Meta, o imóvel já vem
            vinculado ao atendimento.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-5 overflow-y-auto pr-1">
          <div className="space-y-1.5">
            <Label htmlFor="campanha-nome">Nome *</Label>
            <Input
              id="campanha-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Lançamento Pinheiros — outubro"
              data-testid="campanha-nome"
            />
          </div>

          <div className="space-y-2">
            <Label>Imóveis</Label>
            {codigos.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nenhum imóvel vinculado.</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5" data-testid="campanha-imoveis">
                {codigos.map((c) => (
                  <li
                    key={c}
                    className="flex items-center gap-1 rounded-full border bg-muted px-2.5 py-1 text-xs"
                  >
                    <span className="tabular-nums font-medium">{c}</span>
                    {titulos.get(c) && (
                      <span className="max-w-[16rem] truncate text-muted-foreground">
                        {titulos.get(c)}
                      </span>
                    )}
                    <button
                      type="button"
                      aria-label={`Remover o imóvel ${c}`}
                      onClick={() => setCodigos((l) => l.filter((x) => x !== c))}
                      data-testid={`campanha-imovel-remover-${c}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <ImovelCodigoPicker
              value={null}
              onChange={addCodigo}
              data-testid="campanha-imovel-picker"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Veiculações (Meta Ads)</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 text-xs"
                onClick={addVeic}
                data-testid="campanha-veic-add"
              >
                <Plus className="h-3 w-3" />
                Adicionar veiculação
              </Button>
            </div>
            {veics.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Sem veiculações — a campanha ainda não resolve nenhum lead.
              </p>
            )}
            {veics.map((v, idx) => (
              <div key={v.key} className="space-y-1" data-testid={`campanha-veic-${idx}`}>
                <div className="flex items-center gap-2">
                  <Select
                    value={v.nivel}
                    onValueChange={(n) =>
                      setVeics((l) =>
                        l.map((x) => (x.key === v.key ? { ...x, nivel: n as VeiculacaoNivel } : x)),
                      )
                    }
                  >
                    <SelectTrigger className="w-40" aria-label="Nível">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(Object.keys(NIVEL_LABEL) as VeiculacaoNivel[]).map((n) => (
                        <SelectItem key={n} value={n}>
                          {NIVEL_LABEL[n]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    value={v.ref_codigo}
                    onChange={(e) =>
                      setVeics((l) =>
                        l.map((x) => (x.key === v.key ? { ...x, ref_codigo: e.target.value } : x)),
                      )
                    }
                    placeholder="ID no Meta"
                    aria-label="ID no Meta"
                    className="flex-1"
                    data-testid={`campanha-veic-ref-${idx}`}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    aria-label="Remover veiculação"
                    onClick={() => setVeics((l) => l.filter((x) => x.key !== v.key))}
                    data-testid={`campanha-veic-remover-${idx}`}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                {linhaEmUso(v.ref_codigo) && (
                  <p
                    className="text-xs text-destructive"
                    role="alert"
                    data-testid={`campanha-veic-erro-${idx}`}
                  >
                    {erroVeic}
                  </p>
                )}
              </div>
            ))}
            {erroSemLinha && (
              <p className="text-xs text-destructive" role="alert" data-testid="campanha-veic-erro">
                {erroVeic}
              </p>
            )}
          </div>

          {erro && (
            <p className="text-sm text-destructive" role="alert" data-testid="campanha-erro">
              {erro}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={salvando}>
            Cancelar
          </Button>
          <Button onClick={salvar} disabled={!podeSalvar} data-testid="campanha-salvar">
            {salvando && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Salvar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
