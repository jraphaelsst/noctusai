/** Julia › Agente — "Relatórios e alertas" (where the report goes) and "Catálogo de imóveis" (Vista live | local mirror). */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";
import {
  useCatalogoFonte,
  useRelatorioDestino,
  useSalvarCatalogoFonte,
  useSalvarRelatorioDestino,
  type FonteCatalogo,
  type ModoRelatorioDestino,
} from "@/hooks/useJuliaRelatorioLead";

/** "+5511987654321" -> "(11) 98765-4321". Anything unparseable shows the digits typed. */
export function e164ParaMascara(e164: string | null | undefined): string {
  let d = (e164 ?? "").replace(/\D/g, "");
  if (d.startsWith("55") && d.length > 11) d = d.slice(2);
  return mascaraBR(d);
}
export function mascaraBR(digitos: string): string {
  const d = digitos.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d ? `(${d}` : "";
  const ddd = d.slice(0, 2);
  const resto = d.slice(2);
  const corte = d.length > 10 ? 5 : 4;
  return resto.length <= corte ? `(${ddd}) ${resto}` : `(${ddd}) ${resto.slice(0, corte)}-${resto.slice(corte)}`;
}
/** Masked BR phone -> E.164, or null when it is not a full 10/11-digit number. */
export function mascaraParaE164(mascarado: string): string | null {
  const d = mascarado.replace(/\D/g, "");
  return d.length === 10 || d.length === 11 ? `+55${d}` : null;
}

function Esqueleto({ testId }: { testId: string }) {
  return <div className="h-32 animate-pulse rounded-lg bg-muted" data-testid={testId} />;
}

function ErroCard({ titulo, testId, onRetry }: { titulo: string; testId: string; onRetry: () => void }) {
  return (
    <Card data-testid={testId}>
      <CardContent className="flex items-center justify-between gap-3 py-6">
        <p role="alert" className="text-sm text-destructive">
          Não foi possível carregar: {titulo}.
        </p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Tentar de novo
        </Button>
      </CardContent>
    </Card>
  );
}

export function RelatoriosCard({ isAdmin }: { isAdmin: boolean }) {
  const q = useRelatorioDestino();
  const salvar = useSalvarRelatorioDestino();
  const [modo, setModo] = useState<ModoRelatorioDestino>("numero");
  const [tel, setTel] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const servidor = q.data;
  useEffect(() => {
    if (servidor) {
      setModo(servidor.modo);
      setTel(e164ParaMascara(servidor.numero_e164));
    }
  }, [servidor]);

  if (q.isPending && !q.data) return <Esqueleto testId="relatorios-skeleton" />;
  if (!q.data) return <ErroCard titulo="destino dos relatórios" testId="relatorios-erro" onRetry={() => q.refetch()} />;

  const e164 = mascaraParaE164(tel);
  const telInvalido = tel.trim() !== "" && !e164;
  const faltaNumero = modo === "numero" && !e164;
  const sujo = modo !== q.data.modo || (e164 ?? null) !== (q.data.numero_e164 ?? null);

  function enviar() {
    setErro(null);
    salvar.mutate(
      { modo, numero_e164: e164 },
      {
        onSuccess: () => toast.success("Destino dos relatórios salvo"),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar o destino dos relatórios.")),
      },
    );
  }

  return (
    <Card data-testid="relatorios-card">
      <CardHeader>
        <CardTitle className="text-base">Relatórios e alertas</CardTitle>
        <CardDescription>
          Quando a Julia passa um lead para uma pessoa (ou algo dá errado) ela envia um relatório por WhatsApp. Escolha
          quem recebe; o relatório também fica salvo no card do lead.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-2" disabled={!isAdmin || salvar.isPending}>
          <legend className="sr-only">Destino dos relatórios</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="rel-modo" checked={modo === "numero"} onChange={() => setModo("numero")} />
            Número fixo
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="rel-modo" checked={modo === "responsavel"} onChange={() => setModo("responsavel")} />
            Responsável do lead
          </label>
          {modo === "responsavel" && (
            <p className="text-xs text-muted-foreground">
              Vai para o WhatsApp do responsável pelo lead; se ele não tiver número, usa o número abaixo.
            </p>
          )}
        </fieldset>
        <div className="space-y-1">
          <Label htmlFor="rel-numero">{modo === "numero" ? "WhatsApp que recebe os relatórios" : "Número reserva (opcional)"}</Label>
          <Input
            id="rel-numero"
            inputMode="tel"
            placeholder="(11) 98765-4321"
            value={tel}
            disabled={!isAdmin || salvar.isPending}
            onChange={(e) => setTel(mascaraBR(e.target.value))}
            className="max-w-xs"
          />
          {telInvalido && (
            <p role="alert" className="text-xs text-destructive" data-testid="rel-tel-invalido">
              Informe DDD + número (10 ou 11 dígitos).
            </p>
          )}
        </div>
        {erro && (
          <p role="alert" className="text-sm text-destructive" data-testid="relatorios-salvar-erro">
            {erro}
          </p>
        )}
        {isAdmin ? (
          <Button onClick={enviar} disabled={!sujo || telInvalido || faltaNumero || salvar.isPending} data-testid="relatorios-salvar">
            {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Salvar
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>
        )}
      </CardContent>
    </Card>
  );
}

export function CatalogoCard({ isAdmin }: { isAdmin: boolean }) {
  const q = useCatalogoFonte();
  const salvar = useSalvarCatalogoFonte();
  const [erro, setErro] = useState<string | null>(null);

  if (q.isPending && !q.data) return <Esqueleto testId="catalogo-skeleton" />;
  if (!q.data) return <ErroCard titulo="fonte do catálogo" testId="catalogo-erro" onRetry={() => q.refetch()} />;

  function escolher(fonte: FonteCatalogo) {
    if (fonte === q.data?.fonte) return;
    setErro(null);
    salvar.mutate(
      { fonte },
      {
        onSuccess: () => toast.success("Fonte do catálogo atualizada"),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar a fonte do catálogo.")),
      },
    );
  }

  return (
    <Card data-testid="catalogo-card">
      <CardHeader>
        <CardTitle className="text-base">Catálogo de imóveis</CardTitle>
        <CardDescription>De onde a Julia busca os imóveis que oferece aos leads.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <fieldset className="space-y-2" disabled={!isAdmin || salvar.isPending}>
          <legend className="sr-only">Fonte do catálogo</legend>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="cat-fonte" checked={q.data.fonte === "vista"} onChange={() => escolher("vista")} />
            Vista (ao vivo)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="cat-fonte" checked={q.data.fonte === "espelho"} onChange={() => escolher("espelho")} />
            Espelho local
          </label>
        </fieldset>
        {salvar.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {erro && (
          <p role="alert" className="text-sm text-destructive" data-testid="catalogo-salvar-erro">
            {erro}
          </p>
        )}
        {!isAdmin && <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>}
      </CardContent>
    </Card>
  );
}
