/**
 * Configurações → Limites diários (geracao-contract.md §9.4.1).
 *
 * One row per daily generation limit: label, scope, default, an editable number (owner/admin) and
 * "Restaurar padrão" when the org has its own value; one "Salvar" sends every dirty row. Server-state rules:
 * skeleton only while there is no data, a refused save keeps what was typed and shows the server's sentence, the
 * answered list is written to the cache by the hook, unsaved edits are flagged.
 */
import { useState } from "react";
import { Gauge, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { UnsavedChangesNotice, useBeforeUnloadGuard } from "@noctusai/lib/components";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mensagemErroServidor } from "@/lib/erroServidor";
import {
  useLimitesGeracao,
  useSalvarLimitesGeracao,
  type LimiteEscopo,
  type LimiteGeracao,
  type LimitesGeracaoSave,
} from "@/hooks/useLimitesGeracao";

const ESCOPO: Record<LimiteEscopo, string> = {
  usuario: "por pessoa, a cada 24 horas",
  marca: "por marca, por dia",
  org: "para a organização toda, a cada 24 horas",
};

/** The typed text of a row, or `undefined` when the row is untouched. */
type Rascunho = Record<string, string>;

function erroDoValor(l: LimiteGeracao, texto: string): string | null {
  if (!/^\d+$/.test(texto.trim())) return "Informe um número inteiro.";
  const n = Number(texto);
  if (n < 1 || n > l.maximo) return `Use um valor entre 1 e ${l.maximo}.`;
  return null;
}

export function LimitesDiariosSection({ canEdit }: { canEdit: boolean }) {
  const { data, loading, isError, refetch, isRefreshing } = useLimitesGeracao();
  const salvar = useSalvarLimitesGeracao();
  const [rascunho, setRascunho] = useState<Rascunho>({});

  const itens = data?.items ?? [];
  const sujos = itens.filter((l) => rascunho[l.chave] !== undefined && rascunho[l.chave] !== String(l.valor));
  const invalidos = sujos.filter((l) => erroDoValor(l, rascunho[l.chave]) !== null);
  useBeforeUnloadGuard(sujos.length > 0);

  async function enviar(limites: LimitesGeracaoSave, sucesso: string) {
    try {
      await salvar.mutateAsync(limites);
      setRascunho((r) => {
        const resto = { ...r };
        for (const chave of Object.keys(limites)) delete resto[chave];
        return resto;
      });
      toast.success(sucesso);
    } catch (e) {
      // The typed values stay in the draft so the user can fix and retry.
      toast.error(mensagemErroServidor(e, "Não foi possível salvar os limites."));
    }
  }

  function onSalvar() {
    if (sujos.length === 0 || invalidos.length > 0) return;
    const limites: LimitesGeracaoSave = {};
    for (const l of sujos) limites[l.chave] = Number(rascunho[l.chave]);
    void enviar(limites, "Limites diários atualizados.");
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center p-12" data-testid="limites-carregando">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (isError && !data) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 p-12 text-center" data-testid="limites-erro">
          <p className="text-sm text-muted-foreground">Não foi possível carregar os limites diários.</p>
          <Button variant="outline" size="sm" onClick={() => refetch()} data-testid="limites-tentar-novamente">
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card id="limites-diarios">
      <CardHeader>
        <div className="flex items-center gap-3">
          <Gauge className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle>Limites diários</CardTitle>
            <CardDescription>
              Quanto a geração com IA pode ser usada por dia. Ao atingir um limite, aumente-o aqui. Cada limite tem
              um teto da plataforma.
            </CardDescription>
          </div>
          {isRefreshing && <Loader2 className="ml-auto h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!canEdit && (
          <p className="text-xs text-muted-foreground" data-testid="limites-somente-leitura">
            Somente owner ou admin podem alterar estes limites.
          </p>
        )}
        {itens.map((l) => {
          const texto = rascunho[l.chave] ?? String(l.valor);
          const erro = rascunho[l.chave] !== undefined ? erroDoValor(l, texto) : null;
          const id = `limite-${l.chave}`;
          return (
            <div key={l.chave} className="flex flex-wrap items-end gap-3 border-b pb-4 last:border-0" data-testid={id}>
              <div className="min-w-[16rem] flex-1 space-y-1">
                <Label htmlFor={`${id}-input`}>{l.rotulo}</Label>
                <p className="text-xs text-muted-foreground">
                  {l.descricao} ({ESCOPO[l.escopo]}). Padrão: {l.padrao} · máximo: {l.maximo}
                  {l.personalizado ? " · personalizado" : ""}
                </p>
                {erro && (
                  <p className="text-xs text-destructive" role="alert" data-testid={`${id}-erro`}>
                    {erro}
                  </p>
                )}
              </div>
              <Input
                id={`${id}-input`}
                data-testid={`${id}-input`}
                type="number"
                inputMode="numeric"
                min={1}
                max={l.maximo}
                step={1}
                className="w-28"
                value={texto}
                disabled={!canEdit || salvar.isPending}
                onChange={(e) => setRascunho((r) => ({ ...r, [l.chave]: e.target.value }))}
              />
              {canEdit && l.personalizado && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={salvar.isPending}
                  data-testid={`${id}-restaurar`}
                  onClick={() => void enviar({ [l.chave]: null }, `${l.rotulo}: padrão restaurado.`)}
                >
                  Restaurar padrão
                </Button>
              )}
            </div>
          );
        })}
        {canEdit && (
          <div className="flex items-center gap-3">
            <Button
              onClick={onSalvar}
              disabled={sujos.length === 0 || invalidos.length > 0 || salvar.isPending}
              data-testid="limites-salvar"
            >
              {salvar.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Salvar
            </Button>
            <UnsavedChangesNotice dirty={sujos.length > 0} data-testid="limites-nao-salvo" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
