/**
 * Julia › Agente card (d): the org's public privacy notice (contract 11.2). Everyone reads it; ONLY NoctusAI platform admins
 * get "Editar aviso" (owner 2026-11-17), saved through the platform-admin-only `PUT /api/julia/agente/aviso`. Org admins
 * keep the read-only view and the "fale com o suporte" copy. A refusal (e.g. `link_obrigatorio`) is always shown, never silent.
 */
import { useState } from "react";
import { AlertTriangle, ExternalLink, Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useJuliaAviso, useSalvarAviso, type JuliaAvisoAdmin } from "@/hooks/useJuliaAviso";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { blocosParaTexto, textoParaBlocos } from "@/lib/juliaAviso";

export const NOTA_AVISO_NOCTUS =
  "O aviso de privacidade da Julia é configurado pela equipe NoctusAI. Para alterar, fale com o suporte.";

function Linha({ rotulo, valor, testid }: { rotulo: string; valor: string | null | undefined; testid?: string }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs font-medium text-muted-foreground">{rotulo}</dt>
      <dd className="whitespace-pre-wrap text-sm" data-testid={testid}>
        {valor?.trim() ? valor : <span className="text-muted-foreground">Não definido</span>}
      </dd>
    </div>
  );
}

function AvisoLeitura({ aviso, podeEditar, onEditar }: { aviso: JuliaAvisoAdmin; podeEditar: boolean; onEditar: () => void }) {
  return (
    <div className="space-y-4">
      {aviso.incompleto && (
        <p role="alert" className="flex items-start gap-2 text-sm text-warning-foreground" data-testid="aviso-incompleto">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            O aviso ainda tem campos "a definir" (nome da empresa ou contato). A Julia não pode ser ligada até que a equipe
            NoctusAI o complete: fale com o suporte.
          </span>
        </p>
      )}
      <dl className="grid gap-3 sm:grid-cols-2" data-testid="aviso-leitura">
        <Linha rotulo="Título" valor={aviso.titulo} testid="aviso-titulo" />
        <Linha rotulo="Empresa (controlador)" valor={aviso.empresa_nome} testid="aviso-empresa" />
        <Linha rotulo="E-mail de contato" valor={aviso.contato_email} />
        <Linha rotulo="WhatsApp de contato" valor={aviso.contato_whatsapp} />
      </dl>
      <dl>
        <Linha rotulo="Mensagem inicial" valor={aviso.mensagem_inicial} testid="aviso-mensagem" />
      </dl>
      <div className="space-y-3">
        {aviso.secoes.map((s, i) => (
          <div key={i} className="space-y-1 rounded-md border p-3" data-testid={`aviso-secao-${i}`}>
            <p className="text-sm font-medium">
              {s.n}. {s.title}
            </p>
            <p className="whitespace-pre-wrap text-sm">{blocosParaTexto(s.blocks)}</p>
          </div>
        ))}
      </div>
      {podeEditar ? (
        <div className="flex items-center gap-3">
          <Button type="button" size="sm" onClick={onEditar} data-testid="aviso-editar">
            Editar aviso
          </Button>
          <span className="text-xs text-muted-foreground" data-testid="aviso-versao">
            Versão {aviso.versao}
          </span>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground" data-testid="aviso-nota-suporte">
          {NOTA_AVISO_NOCTUS}
        </p>
      )}
      <a
        href={`/privacidade/${aviso.slug}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-sm text-primary underline"
        data-testid="aviso-pagina-publica"
      >
        Ver página pública <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </div>
  );
}


interface SecaoRascunho {
  n: string;
  title: string;
  texto: string;
}

export function mensagemErroAviso(err: unknown): string {
  const code = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  if (code === "link_obrigatorio") {
    return "A mensagem inicial precisa conter {link}: é onde o aviso de privacidade é enviado ao lead.";
  }
  if (code === "edicao_restrita_plataforma") return NOTA_AVISO_NOCTUS;
  return mensagemErroServidor(err, "Não foi possível salvar o aviso de privacidade.");
}

function AvisoEditor({ aviso, onFechar }: { aviso: JuliaAvisoAdmin; onFechar: (salvo: boolean) => void }) {
  const salvar = useSalvarAviso();
  const [titulo, setTitulo] = useState(aviso.titulo ?? "");
  const [empresa, setEmpresa] = useState(aviso.empresa_nome ?? "");
  const [email, setEmail] = useState(aviso.contato_email ?? "");
  const [whatsapp, setWhatsapp] = useState(aviso.contato_whatsapp ?? "");
  const [mensagem, setMensagem] = useState(aviso.mensagem_inicial ?? "");
  const [secoes, setSecoes] = useState<SecaoRascunho[]>(
    aviso.secoes.map((s) => ({ n: s.n, title: s.title, texto: blocosParaTexto(s.blocks) })),
  );

  const semLink = !mensagem.includes("{link}");
  const invalido =
    !titulo.trim() || !empresa.trim() || !mensagem.trim() || secoes.length === 0 || secoes.some((s) => !s.n.trim() || !s.title.trim());

  const mudar = (i: number, parte: Partial<SecaoRascunho>) =>
    setSecoes((atual) => atual.map((s, j) => (j === i ? { ...s, ...parte } : s)));

  const onSalvar = () =>
    salvar.mutate(
      {
        titulo: titulo.trim(),
        empresa_nome: empresa.trim(),
        contato_email: email.trim() || null,
        contato_whatsapp: whatsapp.trim() || null,
        mensagem_inicial: mensagem,
        secoes: secoes.map((s) => ({ n: s.n.trim(), title: s.title.trim(), blocks: textoParaBlocos(s.texto) })),
      },
      { onSuccess: () => onFechar(true) },
    );

  return (
    <form
      className="space-y-4"
      data-testid="aviso-editor"
      onSubmit={(e) => {
        e.preventDefault();
        if (!invalido) onSalvar();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="aviso-f-titulo">Título</Label>
          <Input id="aviso-f-titulo" value={titulo} maxLength={200} onChange={(e) => setTitulo(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aviso-f-empresa">Empresa (controlador)</Label>
          <Input id="aviso-f-empresa" value={empresa} maxLength={200} onChange={(e) => setEmpresa(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aviso-f-email">E-mail de contato</Label>
          <Input id="aviso-f-email" type="email" value={email} maxLength={200} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aviso-f-whatsapp">WhatsApp de contato</Label>
          <Input id="aviso-f-whatsapp" value={whatsapp} maxLength={40} onChange={(e) => setWhatsapp(e.target.value)} />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="aviso-f-mensagem">Mensagem inicial</Label>
        <Textarea
          id="aviso-f-mensagem"
          rows={3}
          value={mensagem}
          maxLength={1000}
          aria-invalid={semLink}
          aria-describedby="aviso-f-mensagem-ajuda"
          onChange={(e) => setMensagem(e.target.value)}
        />
        <p id="aviso-f-mensagem-ajuda" className={semLink ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
          Deve conter {"{link}"}, o link da página pública do aviso.
        </p>
      </div>
      <div className="space-y-3">
        {secoes.map((s, i) => (
          <fieldset key={i} className="space-y-2 rounded-md border p-3" data-testid={`aviso-editor-secao-${i}`}>
            <legend className="px-1 text-xs text-muted-foreground">Seção {i + 1}</legend>
            <div className="grid gap-2 sm:grid-cols-[6rem_1fr_auto]">
              <div className="space-y-1">
                <Label htmlFor={`aviso-s-n-${i}`}>Número</Label>
                <Input id={`aviso-s-n-${i}`} value={s.n} maxLength={8} onChange={(e) => mudar(i, { n: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`aviso-s-t-${i}`}>Título da seção</Label>
                <Input id={`aviso-s-t-${i}`} value={s.title} maxLength={200} onChange={(e) => mudar(i, { title: e.target.value })} />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="self-end"
                disabled={secoes.length <= 1}
                aria-label={`Remover seção ${i + 1}`}
                onClick={() => setSecoes((atual) => atual.filter((_, j) => j !== i))}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-1">
              <Label htmlFor={`aviso-s-c-${i}`}>Conteúdo</Label>
              <Textarea id={`aviso-s-c-${i}`} rows={5} value={s.texto} onChange={(e) => mudar(i, { texto: e.target.value })} />
              <p className="text-xs text-muted-foreground">
                Separe parágrafos com uma linha em branco; linhas iniciadas por "- " viram lista.
              </p>
            </div>
          </fieldset>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={secoes.length >= 40}
          onClick={() => setSecoes((atual) => [...atual, { n: String(atual.length + 1), title: "", texto: "" }])}
        >
          <Plus className="mr-1 h-4 w-4" /> Adicionar seção
        </Button>
      </div>
      {salvar.isError && (
        <p role="alert" className="text-sm text-destructive" data-testid="aviso-erro-salvar">
          {mensagemErroAviso(salvar.error)}
        </p>
      )}
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={invalido || salvar.isPending} data-testid="aviso-salvar">
          {salvar.isPending ? (
            <>
              <Loader2 className="mr-1 h-4 w-4 animate-spin" /> Salvando…
            </>
          ) : (
            "Salvar aviso"
          )}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => onFechar(false)} disabled={salvar.isPending}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

export function AvisoPrivacidadeCard({ isPlatformAdmin = false }: { isPlatformAdmin?: boolean } = {}) {
  const q = useJuliaAviso();
  const [editando, setEditando] = useState(false);
  const [salvo, setSalvo] = useState(false);
  const showSkeleton = q.isPending && !q.data;

  return (
    <Card data-testid="aviso-card">
      <CardHeader>
        <CardTitle className="text-base">Aviso de privacidade</CardTitle>
        <CardDescription>
          Página pública enviada ao lead na primeira mensagem (LGPD). A empresa é o controlador dos dados.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {showSkeleton ? (
          <div className="h-40 animate-pulse rounded-md bg-muted" data-testid="aviso-skeleton" />
        ) : q.isError && !q.data ? (
          <p role="alert" className="text-sm text-destructive" data-testid="aviso-erro">
            Não foi possível carregar o aviso de privacidade.{" "}
            <button className="underline" onClick={() => q.refetch()}>
              Tentar de novo
            </button>
          </p>
        ) : q.data && editando && isPlatformAdmin ? (
          <AvisoEditor
            aviso={q.data}
            onFechar={(foiSalvo) => {
              setEditando(false);
              setSalvo(foiSalvo);
            }}
          />
        ) : q.data ? (
          <>
            {salvo && (
              <p role="status" className="mb-3 text-sm" data-testid="aviso-salvo">
                Aviso salvo. Versão atual: {q.data.versao}.
              </p>
            )}
            <AvisoLeitura
              aviso={q.data}
              podeEditar={isPlatformAdmin}
              onEditar={() => {
                setSalvo(false);
                setEditando(true);
              }}
            />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
