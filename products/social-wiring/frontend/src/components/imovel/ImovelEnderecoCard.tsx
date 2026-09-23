/**
 * `<ImovelEnderecoCard/>` — the manual address override (migration 149,
 * widened by 159), as its own card.
 *
 * 🔴 EXTRACTED FROM `ImovelCartorioCard.tsx` ON 2026-09-23, DELIBERATELY ITS
 * OWN FILE. `pages/ImovelDetalhes.tsx` and `hooks/useImovelDados.ts` are hot
 * files right now (a peer engineer's document-rows/404-toast/Matrículas-
 * prefill work) — keeping this address UI in its own component means the
 * page only needs a one-line mount (`<ImovelEnderecoCard .../>`) rather than
 * a deep edit to the shared cartório card or the page's own JSX tree.
 *
 * Owner rule (verbatim, 2026-09-23): "The address doesn't come from the
 * matrícula. The address comes from the property table; it will be
 * mandatory upon property registration that it has the address in it."
 * `complemento`/`bairro`/`CEP` (159) exist mainly for a condomínio whose
 * Vista row mirrors only the GATE address — an operator can override the
 * UNIT's own complemento here (e.g. Vista "Itália, 343, compl. 535" vs. the
 * real unit "Alameda Alemanha, 535"). Every change is logged
 * (`imovel_endereco_historico`): the mirror is external/synced data, so an
 * override needs no admin approval, but does need a trail.
 */
import { useEffect, useState } from "react";
import { Loader2, MapPin } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { EnderecoManualPatch, ImovelDados } from "@/hooks/useImovelDados";

interface Props {
  dados: ImovelDados | undefined;
  loading: boolean;
  saving: boolean;
  onSave: (patch: EnderecoManualPatch) => void;
  mirror?: {
    logradouro?: string | null;
    numero?: string | null;
    complemento?: string | null;
    bairro?: string | null;
    cidade?: string | null;
    uf?: string | null;
    cep?: string | null;
  };
}

interface Draft {
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
  cep: string;
}

function toDraft(dados: ImovelDados | undefined): Draft {
  return {
    logradouro: dados?.endereco_manual_logradouro ?? "",
    numero: dados?.endereco_manual_numero ?? "",
    complemento: dados?.endereco_manual_complemento ?? "",
    bairro: dados?.endereco_manual_bairro ?? "",
    cidade: dados?.endereco_manual_cidade ?? "",
    uf: dados?.endereco_manual_uf ?? "",
    cep: dados?.endereco_manual_cep ?? "",
  };
}

export default function ImovelEnderecoCard({ dados, loading, saving, onSave, mirror }: Props) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(dados));

  // Re-seed when the server view changes — keyed on the values themselves
  // rather than object identity, so a refetch that changed nothing does not
  // stomp a field mid-typing (same convention `ImovelCartorioCard` uses).
  useEffect(() => {
    setDraft(toDraft(dados));
  }, [
    dados?.endereco_manual_logradouro,
    dados?.endereco_manual_numero,
    dados?.endereco_manual_complemento,
    dados?.endereco_manual_bairro,
    dados?.endereco_manual_cidade,
    dados?.endereco_manual_uf,
    dados?.endereco_manual_cep,
  ]);

  const set = (k: keyof Draft) => (v: string) => setDraft((d) => ({ ...d, [k]: v }));

  function submit() {
    const blank = (s: string) => (s.trim() === "" ? null : s.trim());
    onSave({
      logradouro: blank(draft.logradouro),
      numero: blank(draft.numero),
      complemento: blank(draft.complemento),
      bairro: blank(draft.bairro),
      cidade: blank(draft.cidade),
      uf: blank(draft.uf),
      cep: blank(draft.cep),
    });
  }

  return (
    <Card data-testid="imovel-endereco-manual">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MapPin className="h-4 w-4" />
          Endereço (substituição manual)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Corrige o endereço lido do CRM/Vista — usado pelo gerador de contratos quando
          preenchido. Para um condomínio, use o complemento para o número da unidade quando o
          CRM só traz o endereço da portaria. Deixe em branco para usar o endereço do CRM.
        </p>

        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2 space-y-1">
            <Label htmlFor="endereco-manual-logradouro" className="text-xs">
              Logradouro {mirror?.logradouro ? `(CRM: ${mirror.logradouro})` : ""}
            </Label>
            <Input
              id="endereco-manual-logradouro"
              value={draft.logradouro}
              onChange={(e) => set("logradouro")(e.target.value)}
              placeholder={mirror?.logradouro ?? "Ex.: Rua Fictícia"}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-logradouro"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="endereco-manual-numero" className="text-xs">
              Número {mirror?.numero ? `(CRM: ${mirror.numero})` : ""}
            </Label>
            <Input
              id="endereco-manual-numero"
              value={draft.numero}
              onChange={(e) => set("numero")(e.target.value)}
              placeholder={mirror?.numero ?? "Ex.: 100"}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-numero"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="endereco-manual-complemento" className="text-xs">
              Complemento {mirror?.complemento ? `(CRM: ${mirror.complemento})` : ""}
            </Label>
            <Input
              id="endereco-manual-complemento"
              value={draft.complemento}
              onChange={(e) => set("complemento")(e.target.value)}
              placeholder={mirror?.complemento ?? "Ex.: Apto 535"}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-complemento"
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="endereco-manual-bairro" className="text-xs">
              Bairro {mirror?.bairro ? `(CRM: ${mirror.bairro})` : ""}
            </Label>
            <Input
              id="endereco-manual-bairro"
              value={draft.bairro}
              onChange={(e) => set("bairro")(e.target.value)}
              placeholder={mirror?.bairro ?? "Ex.: Pinheiros"}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-bairro"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="endereco-manual-uf" className="text-xs">
              UF {mirror?.uf ? `(CRM: ${mirror.uf})` : ""}
            </Label>
            <Input
              id="endereco-manual-uf"
              value={draft.uf}
              onChange={(e) => set("uf")(e.target.value.toUpperCase())}
              placeholder={mirror?.uf ?? "Ex.: SP"}
              maxLength={2}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-uf"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="endereco-manual-cep" className="text-xs">
              CEP {mirror?.cep ? `(CRM: ${mirror.cep})` : ""}
            </Label>
            <Input
              id="endereco-manual-cep"
              value={draft.cep}
              onChange={(e) => set("cep")(e.target.value)}
              placeholder={mirror?.cep ?? "Ex.: 01000-000"}
              maxLength={9}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-cep"
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="endereco-manual-cidade" className="text-xs">
              Cidade {mirror?.cidade ? `(CRM: ${mirror.cidade})` : ""}
            </Label>
            <Input
              id="endereco-manual-cidade"
              value={draft.cidade}
              onChange={(e) => set("cidade")(e.target.value)}
              placeholder={mirror?.cidade ?? "Ex.: São Paulo"}
              disabled={loading || saving}
              data-testid="imovel-endereco-manual-cidade"
            />
          </div>
        </div>

        {dados?.endereco_manual_confirmado_por && (
          <p className="text-xs text-muted-foreground">
            Última alteração por {dados.endereco_manual_confirmado_por.nome ?? "—"}
            {dados.endereco_manual_confirmado_em
              ? ` em ${new Date(dados.endereco_manual_confirmado_em).toLocaleString("pt-BR")}`
              : ""}
          </p>
        )}

        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={loading || saving}
          onClick={submit}
          data-testid="imovel-endereco-manual-salvar"
        >
          {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          Salvar endereço
        </Button>
      </CardContent>
    </Card>
  );
}
