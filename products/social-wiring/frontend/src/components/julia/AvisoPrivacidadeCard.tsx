/** Julia › Agente card (d): edit the org's public privacy notice (contract 11.2). */
import { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, ExternalLink, Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useJuliaAviso, useSalvarJuliaAviso, type JuliaAvisoAdmin } from "@/hooks/useJuliaAviso";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";
import { blocosParaTexto, contemLink, textoParaBlocos } from "@/lib/juliaAviso";

interface SecaoForm {
  n: string;
  title: string;
  texto: string;
}

function AvisoForm({ aviso, isAdmin }: { aviso: JuliaAvisoAdmin; isAdmin: boolean }) {
  const salvar = useSalvarJuliaAviso();
  const [titulo, setTitulo] = useState(aviso.titulo ?? "");
  const [empresa, setEmpresa] = useState(aviso.empresa_nome ?? "");
  const [email, setEmail] = useState(aviso.contato_email ?? "");
  const [whats, setWhats] = useState(aviso.contato_whatsapp ?? "");
  const [mensagem, setMensagem] = useState(aviso.mensagem_inicial ?? "");
  const [secoes, setSecoes] = useState<SecaoForm[]>(
    aviso.secoes.map((s) => ({ n: s.n, title: s.title, texto: blocosParaTexto(s.blocks) })),
  );
  const [erro, setErro] = useState<string | null>(null);

  const setSecao = (i: number, patch: Partial<SecaoForm>) =>
    setSecoes((cur) => cur.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));

  function enviar() {
    setErro(null);
    if (!contemLink(mensagem)) {
      setErro("A mensagem inicial precisa conter {link} (o link do aviso de privacidade).");
      return;
    }
    salvar.mutate(
      {
        titulo: titulo.trim(),
        empresa_nome: empresa.trim(),
        contato_email: email.trim() || null,
        contato_whatsapp: whats.trim() || null,
        mensagem_inicial: mensagem,
        secoes: secoes.map((s) => ({ n: s.n.trim(), title: s.title.trim(), blocks: textoParaBlocos(s.texto) })),
      },
      {
        onSuccess: () => toast.success("Aviso de privacidade salvo"),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar o aviso.")),
      },
    );
  }

  const ro = !isAdmin;
  return (
    <div className="space-y-4">
      {aviso.incompleto && (
        <p role="alert" className="flex items-start gap-2 text-sm text-warning-foreground" data-testid="aviso-incompleto">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            O aviso ainda tem campos "a definir" (nome da empresa ou contato). A Julia não pode ser ligada até
            completá-lo.
          </span>
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="aviso-titulo">Título</Label>
          <Input id="aviso-titulo" value={titulo} disabled={ro} onChange={(e) => setTitulo(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aviso-empresa">Empresa (controlador)</Label>
          <Input id="aviso-empresa" value={empresa} disabled={ro} onChange={(e) => setEmpresa(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aviso-email">E-mail de contato</Label>
          <Input id="aviso-email" value={email} disabled={ro} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aviso-whats">WhatsApp de contato</Label>
          <Input id="aviso-whats" value={whats} disabled={ro} onChange={(e) => setWhats(e.target.value)} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="aviso-mensagem">Mensagem inicial</Label>
        <Textarea
          id="aviso-mensagem"
          rows={4}
          value={mensagem}
          disabled={ro}
          onChange={(e) => setMensagem(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          Use <code>{"{empresa}"}</code> para o nome da empresa e <code>{"{link}"}</code> para o link do aviso — o{" "}
          <code>{"{link}"}</code> é obrigatório.
        </p>
      </div>

      <div className="space-y-3">
        <Label>Seções do aviso</Label>
        {secoes.map((s, i) => (
          <div key={i} className="space-y-2 rounded-md border p-3" data-testid={`aviso-secao-${i}`}>
            <div className="flex gap-2">
              <Input
                aria-label={`Número da seção ${i + 1}`}
                className="w-16"
                value={s.n}
                disabled={ro}
                onChange={(e) => setSecao(i, { n: e.target.value })}
              />
              <Input
                aria-label={`Título da seção ${i + 1}`}
                value={s.title}
                disabled={ro}
                onChange={(e) => setSecao(i, { title: e.target.value })}
              />
              {!ro && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remover seção ${i + 1}`}
                  onClick={() => setSecoes((cur) => cur.filter((_, idx) => idx !== i))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
            <Textarea
              aria-label={`Texto da seção ${i + 1}`}
              rows={4}
              value={s.texto}
              disabled={ro}
              onChange={(e) => setSecao(i, { texto: e.target.value })}
            />
          </div>
        ))}
        {!ro && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSecoes((cur) => [...cur, { n: String(cur.length + 1), title: "", texto: "" }])}
          >
            <Plus className="mr-1 h-4 w-4" /> Adicionar seção
          </Button>
        )}
        <p className="text-xs text-muted-foreground">
          Separe parágrafos com uma linha em branco; linhas iniciadas por "- " viram uma lista.
        </p>
      </div>

      {erro && (
        <p role="alert" className="text-sm text-destructive" data-testid="aviso-erro-salvar">
          {erro}
        </p>
      )}

      <div className="flex items-center gap-4">
        {isAdmin ? (
          <Button onClick={enviar} disabled={salvar.isPending} data-testid="salvar-aviso">
            {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Salvar aviso
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode editar o aviso.</p>
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
    </div>
  );
}

export function AvisoPrivacidadeCard({ isAdmin }: { isAdmin: boolean }) {
  const q = useJuliaAviso();
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
        ) : q.data ? (
          // Re-key on the saved version so the form re-seeds from the server row.
          <AvisoForm key={`${q.data.versao}:${q.data.atualizado_em}`} aviso={q.data} isAdmin={isAdmin} />
        ) : null}
      </CardContent>
    </Card>
  );
}
