/**
 * Julia › Agente card "Especificações do negócio": the business's own data (name, hours, domains, contacts…) that Julia
 * uses. Fields are rendered generically from the declarations the active Julia version carries (rotulo / descricao /
 * exemplo per `tipo`), so a new declaration needs no new UI. This is DATA about the business, validated by the server —
 * never instructions; how Julia behaves is managed by NoctusAI.
 *
 * Draft discipline: edits stay in a local draft, flagged "não salvo" until the server accepts them (a refused save keeps
 * the draft and marks the fields the server named). Loading = two signals off `data` (never `isLoading`).
 */
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, Loader2 } from "lucide-react";
import { UnsavedChangesNotice, useUnsavedChanges } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatarDataHora } from "@/components/julia/ConexaoPlataforma";
import { mensagemErroServidor } from "@/lib/erroServidor";
import {
  leituraErroEspec,
  mensagemErroEspec,
  useJuliaEspecificacoes,
  useSalvarEspecificacoes,
  type EspecificacaoDeclarada,
  type Especificacoes,
  type TipoEspecificacao,
  type ViolacaoEspecificacao,
} from "@/hooks/useJuliaEspecificacoes";

/** Derived by SW itself (the privacy notice's public URL): shown, never edited. */
const CHAVES_SOMENTE_LEITURA = new Set(["aviso_privacidade_url"]);

const DICA_DO_TIPO: Partial<Record<TipoEspecificacao, string>> = {
  dominios: "Um domínio por linha.",
  contatos: "Um contato por linha.",
  lista: "Um item por linha.",
};

const LINHAS: Partial<Record<TipoEspecificacao, number>> = { texto: 3, texto_longo: 8, dominios: 4, contatos: 4, lista: 5, horario: 3 };

function Campo({
  decl,
  valor,
  onChange,
  disabled,
  problema,
  alterado,
}: {
  alterado?: { nome?: string | null; em?: string | null } | null;
  decl: EspecificacaoDeclarada;
  valor: string;
  onChange: (v: string) => void;
  disabled: boolean;
  problema: string | null;
}) {
  const id = `espec-${decl.chave}`;
  const ajuda = [decl.descricao, DICA_DO_TIPO[decl.tipo]].filter(Boolean).join(" ");
  const comum = {
    id,
    value: valor,
    disabled,
    placeholder: decl.exemplo ? `Ex.: ${decl.exemplo}` : undefined,
    "aria-invalid": problema ? true : undefined,
    "aria-describedby": `${id}-ajuda`,
  } as const;
  const linhas = LINHAS[decl.tipo];
  return (
    <div className="space-y-1" data-testid={`espec-campo-${decl.chave}`}>
      <Label htmlFor={id}>
        {decl.rotulo}
        {decl.obrigatoria && <span className="ml-1 text-destructive" aria-label="obrigatório">*</span>}
      </Label>
      {linhas ? (
        <Textarea {...comum} rows={linhas} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <Input
          {...comum}
          type={decl.tipo === "url" ? "url" : "text"}
          inputMode={decl.tipo === "cnpj" ? "numeric" : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {ajuda && (
        <p id={`${id}-ajuda`} className="text-xs text-muted-foreground">
          {ajuda}
        </p>
      )}
      {alterado?.nome && (
        <p className="text-xs text-muted-foreground" data-testid={`espec-alterado-${decl.chave}`}>
          Alterado por {alterado.nome}
          {alterado.em ? ` em ${formatarDataHora(alterado.em)}` : ""}
        </p>
      )}
      {problema && (
        <p role="alert" className="text-xs text-destructive" data-testid={`espec-problema-${decl.chave}`}>
          {problema}
        </p>
      )}
    </div>
  );
}

function Formulario({ data, isAdmin }: { data: Especificacoes; isAdmin: boolean }) {
  const salvar = useSalvarEspecificacoes();
  const salvo = Object.fromEntries(data.declaradas.map((d) => [d.chave, data.valores.find((v) => v.chave === d.chave)?.valor ?? ""]));
  const [editado, setEditado] = useState<Record<string, string>>({});
  const [recusadas, setRecusadas] = useState<ViolacaoEspecificacao[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const rascunho = { ...salvo, ...editado };
  const { dirty } = useUnsavedChanges(rascunho, salvo);

  const doServidor = new Map<string, string>();
  for (const i of data.invalidas) doServidor.set(i.chave, i.mensagem);
  for (const v of recusadas) doServidor.set(v.chave, v.mensagem);
  const faltando = new Set(data.faltando);

  function enviar() {
    setErro(null);
    setRecusadas([]);
    salvar.mutate(
      { valores: rascunho },
      {
        onSuccess: (r) => {
          setEditado({});
          toast.success(r.invalidas.length ? "Salvo, com avisos em alguns campos" : "Especificações salvas");
        },
        onError: (e) => {
          const { violacoes } = leituraErroEspec(e);
          if (violacoes.length) {
            setRecusadas(violacoes);
            setErro("Revise os campos marcados. Nada foi salvo.");
          } else {
            setErro(mensagemErroEspec(e) ?? mensagemErroServidor(e, "Não foi possível salvar as especificações."));
          }
        },
      },
    );
  }

  if (data.declaradas.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="espec-vazio">
        A Julia não pede nenhuma informação do seu negócio por enquanto.
      </p>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (isAdmin && dirty) enviar();
      }}
      data-testid="espec-form"
    >
      {data.declaradas.map((d) => {
        const somenteLeitura = CHAVES_SOMENTE_LEITURA.has(d.chave);
        const problema =
          doServidor.get(d.chave) ?? (faltando.has(d.chave) && !rascunho[d.chave]?.trim() ? "Obrigatório: falta preencher." : null);
        return (
          <Campo
            key={d.id}
            decl={d}
            valor={rascunho[d.chave] ?? ""}
            onChange={(v) => setEditado((e) => ({ ...e, [d.chave]: v }))}
            disabled={!isAdmin || somenteLeitura || salvar.isPending}
            problema={problema}
            alterado={(() => {
              const v = data.valores.find((x) => x.chave === d.chave);
              return v ? { nome: v.updated_by_nome, em: v.updated_at } : null;
            })()}
          />
        );
      })}

      {erro && (
        <p role="alert" className="flex items-start gap-2 text-sm text-destructive" data-testid="espec-erro-salvar">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{erro}</span>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!isAdmin || !dirty || salvar.isPending} data-testid="espec-salvar">
          {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          Salvar especificações
        </Button>
        <UnsavedChangesNotice dirty={dirty} data-testid="espec-nao-salvo" />
        {!isAdmin && <span className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</span>}
      </div>
    </form>
  );
}

export function EspecificacoesCard({ isAdmin }: { isAdmin: boolean }) {
  const q = useJuliaEspecificacoes();
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const refusa = q.error ? mensagemErroEspec(q.error) : null;
  const naoConectado = q.error ? leituraErroEspec(q.error).code === "agente_nao_conectado" : false;

  return (
    <Card id="especificacoes" data-testid="especificacoes-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Especificações do negócio</CardTitle>
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="espec-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
        </div>
        <CardDescription>
          Dados da sua empresa que a Julia usa para atender seus leads. São informações do seu negócio: o funcionamento da Julia é mantido pela NoctusAI e não muda por aqui.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {q.data ? (
          <Formulario data={q.data} isAdmin={isAdmin} />
        ) : showSkeleton ? (
          <div className="h-40 animate-pulse rounded-md bg-muted" data-testid="espec-skeleton" />
        ) : (
          <div role="alert" className="space-y-2 text-sm text-destructive" data-testid="espec-erro" data-codigo={leituraErroEspec(q.error).code ?? ""}>
            <p>{refusa ?? "Não foi possível carregar as especificações."}</p>
            {naoConectado ? (
              <a href="#conexao-plataforma" className="text-primary underline" data-testid="espec-ver-conexao">
                Ver conexão com a plataforma
              </a>
            ) : (
              <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
                Tentar de novo
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
