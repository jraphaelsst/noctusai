/**
 * ValidacaoExtracaoDialog — owner decision D2: before a contract is
 * generated, every contract-feeding value a MACHINE extracted and no human
 * validated yet is listed here, one row each, with ✓ accept / ✗ reject
 * (plus "Aceitar tudo" / "Rejeitar tudo"). The backend refuses generation
 * while anything is pending; this dialog is how the operator clears it.
 *
 * Presentational (S3), same discipline as the rest of `card/**`:
 * `GeradorContratoContainer` owns the query + mutations and hands the rows
 * in. `rejeitados` are the items the operator rejected in THIS session that
 * are REQUIRED — they left `pendentes` (the value is now empty), so the
 * container keeps a snapshot to render the inline manual input here, which
 * writes through the item's own `edicao` route (`origem='manual'`).
 *
 * `conflitos` are OPEN extraction conflicts on the same data (a later
 * reading disagreed with a set value). They block generation too, but are
 * READ-ONLY here — each links to the screen where an admin decides it.
 *
 * No `@noctusai/lib` dialog organ exists; the product's own `ui/dialog`
 * primitives are what every sibling dialog (`EnviarAssinaturaDialog`,
 * `NovoContratoDialog`) uses.
 */
import { useState, type ReactNode } from "react";
import {
  AlertCircle,
  Check,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
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

import type { ConflitoExtracao, Decisao, PendenteValidacao } from "@/hooks/useValidacaoExtracao";

/** pt-BR for `origem` — the machine source of the value. */
const ORIGEM_ROTULO: Record<string, string> = {
  api: "Consulta automática",
  ia: "Leitura por IA",
  sugestao: "Sugestão da matrícula",
  sugerido: "Sugestão da matrícula",
  matricula: "Matrícula",
  rg: "RG",
  cnh: "CNH",
  cpf: "CPF",
  cin: "CIN",
  certidao_casamento: "Certidão de casamento",
  certidao_nascimento: "Certidão de nascimento",
  comprovante_endereco: "Comprovante de endereço",
};

const CONFIANCA_ROTULO: Record<string, string> = {
  alta: "Confiança alta",
  baixa: "Confiança baixa",
  nenhuma: "Sem confiança",
};

function agruparPorGrupo(itens: PendenteValidacao[]): [string, PendenteValidacao[]][] {
  const mapa = new Map<string, PendenteValidacao[]>();
  for (const item of itens) {
    const lista = mapa.get(item.grupo) ?? [];
    lista.push(item);
    mapa.set(item.grupo, lista);
  }
  return [...mapa.entries()];
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pendentes: PendenteValidacao[] | undefined;
  conflitos: ConflitoExtracao[];
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  onRetry: () => void;
  /** A decision request is in flight — every accept/reject button waits. */
  decidindo: boolean;
  onDecidir: (decisoes: { chave: string; decisao: Decisao }[]) => void;
  /** Required items rejected in this session, still awaiting a typed value. */
  rejeitados: PendenteValidacao[];
  salvandoChave: string | null;
  onSalvarManual: (item: PendenteValidacao, valor: string) => void;
  gerando: boolean;
  onProsseguir: () => void;
}

function LinhaRejeitada({
  item,
  salvando,
  onSalvar,
}: {
  item: PendenteValidacao;
  salvando: boolean;
  onSalvar: (valor: string) => void;
}) {
  const [valor, setValor] = useState("");
  if (!item.edicao) {
    return (
      <li
        className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800"
        data-testid={`validacao-rejeitado-${item.chave}`}
      >
        <span className="font-medium">{item.rotulo}</span> ({item.grupo}) foi rejeitado e é
        obrigatório — preencha no card antes de gerar.
      </li>
    );
  }
  return (
    <li
      className="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs"
      data-testid={`validacao-rejeitado-${item.chave}`}
    >
      <span className="min-w-40 flex-1">
        <span className="font-medium">{item.rotulo}</span>{" "}
        <span className="text-muted-foreground">({item.grupo})</span>
      </span>
      <Input
        type={item.edicao.tipo === "data" ? "date" : "text"}
        className="h-8 w-56"
        value={valor}
        placeholder="Digite o valor correto"
        aria-label={`Valor correto de ${item.rotulo}`}
        onChange={(e) => setValor(e.target.value)}
        data-testid={`validacao-input-${item.chave}`}
      />
      <Button
        type="button"
        size="sm"
        disabled={!valor.trim() || salvando}
        onClick={() => onSalvar(valor.trim())}
        data-testid={`validacao-salvar-${item.chave}`}
      >
        {salvando && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
        Salvar
      </Button>
    </li>
  );
}

export default function ValidacaoExtracaoDialog({
  open,
  onOpenChange,
  pendentes,
  conflitos,
  showSkeleton,
  isRefreshing,
  isError,
  onRetry,
  decidindo,
  onDecidir,
  rejeitados,
  salvandoChave,
  onSalvarManual,
  gerando,
  onProsseguir,
}: Props) {
  const lista = pendentes ?? [];
  const nadaPendente = !!pendentes && lista.length === 0;
  // A rejected value with an inline input blocks until it is typed; one with
  // no single-input route (a group, an enum) is only pointed at — `gerar`
  // then reports it `faltando`, the existing section's job.
  const aguardandoDigitacao = rejeitados.some((r) => r.edicao !== null);
  const podeGerar = nadaPendente && conflitos.length === 0 && !aguardandoDigitacao && !gerando;

  function decidirTodos(decisao: Decisao) {
    onDecidir(lista.map((p) => ({ chave: p.chave, decisao })));
  }

  let corpo: ReactNode;
  if (showSkeleton) {
    corpo = (
      <div
        className="flex items-center gap-2 p-2 text-xs text-muted-foreground"
        data-testid="validacao-skeleton"
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Verificando dados extraídos…
      </div>
    );
  } else if (isError && !pendentes) {
    corpo = (
      <div
        className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
        data-testid="validacao-erro"
      >
        <span className="text-destructive">
          Não foi possível carregar os dados extraídos para validação.
        </span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  } else if (nadaPendente && conflitos.length === 0) {
    corpo = (
      <p className="text-xs text-muted-foreground" data-testid="validacao-vazio">
        Nenhum dado extraído aguardando validação.
      </p>
    );
  } else if (nadaPendente) {
    corpo = null;
  } else {
    corpo = (
      <div className="space-y-3" data-testid="validacao-lista">
        {agruparPorGrupo(lista).map(([grupo, itens]) => (
          <div key={grupo} className="space-y-1">
            <p className="text-xs font-medium">{grupo}</p>
            <ul className="space-y-1">
              {itens.map((item) => (
                <li
                  key={item.chave}
                  className="flex items-start gap-2 rounded-md border p-2 text-xs"
                  data-testid={`validacao-item-${item.chave}`}
                >
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{item.rotulo}</span>
                      {item.obrigatorio && (
                        <Badge variant="secondary" className="text-[10px]">
                          obrigatório
                        </Badge>
                      )}
                      {item.confianca && (
                        <Badge
                          variant="outline"
                          className={
                            item.confianca === "alta"
                              ? "text-[10px]"
                              : "border-amber-400 text-[10px] text-amber-700"
                          }
                        >
                          {CONFIANCA_ROTULO[item.confianca] ?? item.confianca}
                        </Badge>
                      )}
                    </div>
                    <p className="break-words">{item.valor ?? "—"}</p>
                    <p className="flex items-center gap-1 text-muted-foreground">
                      <FileText className="h-3 w-3 shrink-0" />
                      {ORIGEM_ROTULO[item.origem] ?? item.origem}
                      {item.fonte_nome ? ` · ${item.fonte_nome}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      type="button"
                      size="icon"
                      variant="outline"
                      className="h-7 w-7 text-emerald-700"
                      disabled={decidindo}
                      aria-label={`Aceitar ${item.rotulo}`}
                      title="Aceitar"
                      onClick={() => onDecidir([{ chave: item.chave, decisao: "aceito" }])}
                      data-testid={`validacao-aceitar-${item.chave}`}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="outline"
                      className="h-7 w-7 text-destructive"
                      disabled={decidindo}
                      aria-label={`Rejeitar ${item.rotulo}`}
                      title="Rejeitar"
                      onClick={() => onDecidir([{ chave: item.chave, decisao: "rejeitado" }])}
                      data-testid={`validacao-rejeitar-${item.chave}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] max-w-2xl overflow-y-auto"
        data-testid="validacao-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Validar dados extraídos
            {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </DialogTitle>
          <DialogDescription>
            Estes dados foram lidos automaticamente de documentos e ainda não foram conferidos.
            Aceite ou rejeite cada um antes de gerar o contrato.
          </DialogDescription>
        </DialogHeader>

        {lista.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={decidindo}
              onClick={() => decidirTodos("aceito")}
              data-testid="validacao-aceitar-tudo"
            >
              <Check className="mr-1.5 h-3.5 w-3.5" />
              Aceitar tudo
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={decidindo}
              onClick={() => decidirTodos("rejeitado")}
              data-testid="validacao-rejeitar-tudo"
            >
              <X className="mr-1.5 h-3.5 w-3.5" />
              Rejeitar tudo
            </Button>
            {decidindo && <Loader2 className="h-4 w-4 animate-spin self-center" />}
          </div>
        )}

        {corpo}

        {conflitos.length > 0 && (
          <div className="space-y-1" data-testid="validacao-conflitos">
            <p className="flex items-center gap-1 text-xs font-medium text-destructive">
              <AlertCircle className="h-3.5 w-3.5" />
              Conflitos em aberto — decida antes de gerar
            </p>
            <ul className="space-y-1">
              {conflitos.map((c) => (
                <li
                  key={c.id}
                  className="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs"
                  data-testid={`validacao-conflito-${c.id}`}
                >
                  <p>
                    <span className="font-medium">{c.rotulo}</span>{" "}
                    <span className="text-muted-foreground">({c.grupo})</span>
                  </p>
                  <p className="text-muted-foreground">
                    Atual: {c.valor_atual ?? "—"} · Lido do documento: {c.valor_proposto ?? "—"}
                  </p>
                  <a
                    href={c.link.rota}
                    className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
                    data-testid={`validacao-conflito-link-${c.id}`}
                  >
                    <ExternalLink className="h-3 w-3" />
                    Resolver em {c.link.rotulo}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {rejeitados.length > 0 && (
          <div className="space-y-1" data-testid="validacao-rejeitados">
            <p className="flex items-center gap-1 text-xs font-medium text-amber-800">
              <AlertCircle className="h-3.5 w-3.5" />
              Rejeitados — informe o valor correto
            </p>
            <ul className="space-y-1">
              {rejeitados.map((item) => (
                <LinhaRejeitada
                  key={item.chave}
                  item={item}
                  salvando={salvandoChave === item.chave}
                  onSalvar={(valor) => onSalvarManual(item, valor)}
                />
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Fechar
          </Button>
          <Button
            type="button"
            disabled={!podeGerar}
            onClick={onProsseguir}
            data-testid="validacao-prosseguir"
          >
            {gerando ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            )}
            Gerar contrato
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
