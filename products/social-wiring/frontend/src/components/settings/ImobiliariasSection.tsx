/**
 * `<ImobiliariasSection/>` — the org's REGISTRY of signing companies
 * (imobiliárias). A contract picks exactly one per card — see
 * `hooks/useContratoImobiliaria.ts`. Identity lives here, per company; the
 * org-wide operational settings stay on Settings "Dados da imobiliária".
 *
 * Same shape as `TestemunhasSection` (registry list + dialog + soft delete),
 * mounted standalone on `pages/Imobiliarias.tsx`. `faltando` (derived by the
 * server) is surfaced as "Incompleta: …" so an operator sees what a contract
 * would still be refused for.
 *
 * CNPJ is REQUIRED on create and checked mod-11 here too, through the
 * canonical `@noctusai/lib/identificador` reader (the server re-validates).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { formatIdentificador, lerIdentificador } from "@noctusai/lib/identificador";
import {
  ROTULO_CAMPO_OBRIGATORIO,
  useCreateImobiliaria,
  useDeleteImobiliaria,
  useImobiliarias,
  useUpdateImobiliaria,
  type Imobiliaria,
  type ImobiliariaCreate,
} from "@/hooks/useImobiliarias";

type CampoTexto = Exclude<keyof ImobiliariaCreate, never>;
type Draft = Record<CampoTexto, string>;

const CAMPOS: CampoTexto[] = [
  "razao_social",
  "nome_fantasia",
  "cnpj",
  "creci_pj",
  "creci_pj_regiao",
  "responsavel_nome",
  "responsavel_creci",
  "responsavel_creci_regiao",
  "telefone",
  "email",
  "endereco_cep",
  "endereco_logradouro",
  "endereco_numero",
  "endereco_complemento",
  "endereco_bairro",
  "endereco_cidade",
  "endereco_uf",
];

const EMPTY_DRAFT = Object.fromEntries(CAMPOS.map((c) => [c, ""])) as Draft;

function errorMessage(err: unknown, fallback: string): string {
  return (err as { message?: string } | null)?.message ?? fallback;
}

/** Mod-11 CNPJ check via the canonical identifier reader. */
export function cnpjValido(valor: string): boolean {
  const r = lerIdentificador("cnpj", valor);
  return r.cabe && r.dvOk === true && !r.dvCompletado;
}

export function ImobiliariasSection() {
  const query = useImobiliarias();
  const criar = useCreateImobiliaria();
  const atualizar = useUpdateImobiliaria();
  const excluir = useDeleteImobiliaria();

  const [open, setOpen] = useState(false);
  const [editando, setEditando] = useState<Imobiliaria | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [removendo, setRemovendo] = useState<Imobiliaria | null>(null);

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const items = query.data?.items ?? [];

  function campo(k: CampoTexto, v: string) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  function abrirNova() {
    setEditando(null);
    setDraft(EMPTY_DRAFT);
    setOpen(true);
  }

  function abrirEdicao(i: Imobiliaria) {
    setEditando(i);
    setDraft(
      Object.fromEntries(CAMPOS.map((c) => [c, (i[c] as string | null) ?? ""])) as Draft,
    );
    setOpen(true);
  }

  const cnpjTexto = draft.cnpj.trim();
  const cnpjInvalido = !!cnpjTexto && !cnpjValido(cnpjTexto);

  function submit() {
    const onSuccess = () => {
      setOpen(false);
      toast.success(editando ? "Imobiliária atualizada." : "Imobiliária adicionada.");
    };
    const onError = (err: unknown) =>
      toast.error(errorMessage(err, "Não foi possível salvar a imobiliária."));

    // Blank optional box = "not recorded" (null), never "".
    const opcionais = Object.fromEntries(
      CAMPOS.filter((c) => c !== "razao_social" && c !== "cnpj").map((c) => [
        c,
        draft[c].trim() || null,
      ]),
    );
    if (editando) {
      atualizar.mutate(
        {
          id: editando.id,
          patch: {
            ...opcionais,
            razao_social: draft.razao_social.trim(),
            cnpj: cnpjTexto,
          },
        },
        { onSuccess, onError },
      );
    } else {
      criar.mutate(
        { ...opcionais, razao_social: draft.razao_social.trim(), cnpj: cnpjTexto },
        { onSuccess, onError },
      );
    }
  }

  function remover(i: Imobiliaria) {
    excluir.mutate(i.id, {
      onSuccess: () => setRemovendo(null),
      onError: (err) =>
        toast.error(errorMessage(err, "Não foi possível remover a imobiliária.")),
    });
  }

  const salvando = criar.isPending || atualizar.isPending;
  const podeSalvar = !!draft.razao_social.trim() && !!cnpjTexto && !cnpjInvalido;

  const input = (k: CampoTexto, rotulo: string, extra?: { placeholder?: string; maxLength?: number; upper?: boolean }) => (
    <div className="space-y-1.5">
      <Label htmlFor={`imobs-${k}`}>{rotulo}</Label>
      <Input
        id={`imobs-${k}`}
        value={draft[k]}
        maxLength={extra?.maxLength}
        placeholder={extra?.placeholder}
        onChange={(e) => campo(k, extra?.upper ? e.target.value.toUpperCase() : e.target.value)}
        data-testid={`imobs-${k}`}
      />
    </div>
  );

  return (
    <Card data-testid="imobiliarias-section">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>Imobiliárias</CardTitle>
          <CardDescription>
            Imobiliárias que assinam os contratos. Cada contrato escolhe qual
            delas assina, na aba Contratos do card. Se houver só uma
            cadastrada, ela é usada automaticamente.
          </CardDescription>
        </div>
        <Button size="sm" onClick={abrirNova} data-testid="imobiliaria-nova">
          <Plus className="mr-1 h-4 w-4" />
          Nova imobiliária
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {isRefreshing && (
          <p className="text-xs text-muted-foreground" data-testid="imobiliarias-refreshing">
            Atualizando…
          </p>
        )}
        {showSkeleton ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : query.isError && !query.data ? (
          <p className="text-sm text-destructive">Não foi possível carregar as imobiliárias.</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma imobiliária cadastrada.</p>
        ) : (
          <div className="space-y-2">
            {items.map((i) => (
              <div
                key={i.id}
                className="flex items-center justify-between rounded-md border p-3"
                data-testid={`imobiliaria-${i.id}`}
              >
                <div>
                  <p className="text-sm font-medium">{i.razao_social ?? "—"}</p>
                  <p className="text-xs text-muted-foreground">
                    {[
                      i.nome_fantasia,
                      i.cnpj ? formatIdentificador("cnpj", i.cnpj) : null,
                      i.endereco_cidade,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </p>
                  {i.faltando.length > 0 && (
                    <Badge
                      variant="outline"
                      className="mt-1 text-[10px] text-amber-700"
                      data-testid={`imobiliaria-incompleta-${i.id}`}
                    >
                      Incompleta: {i.faltando.map((f) => ROTULO_CAMPO_OBRIGATORIO[f] ?? f).join(", ")}
                    </Badge>
                  )}
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => abrirEdicao(i)}
                    aria-label={`Editar ${i.razao_social ?? "imobiliária"}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setRemovendo(i)}
                    aria-label={`Remover ${i.razao_social ?? "imobiliária"}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editando ? "Editar imobiliária" : "Nova imobiliária"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              {input("razao_social", "Razão social *")}
              {input("nome_fantasia", "Nome fantasia")}
              <div className="space-y-1.5">
                <Label htmlFor="imobs-cnpj">CNPJ *</Label>
                <Input
                  id="imobs-cnpj"
                  value={draft.cnpj}
                  placeholder="12.345.678/0001-90"
                  onChange={(e) => campo("cnpj", e.target.value)}
                  aria-invalid={cnpjInvalido}
                  data-testid="imobs-cnpj"
                />
                {cnpjInvalido && (
                  <p className="text-xs text-destructive" data-testid="imobs-cnpj-invalido">
                    CNPJ inválido.
                  </p>
                )}
              </div>
              {input("creci_pj", "CRECI PJ", { placeholder: "J-12345" })}
              {input("creci_pj_regiao", "Região do CRECI PJ", { placeholder: "CRECI/SP", maxLength: 64 })}
              {input("responsavel_nome", "Responsável técnico")}
              {input("responsavel_creci", "CRECI do responsável")}
              {input("responsavel_creci_regiao", "Região do CRECI do responsável", { placeholder: "CRECI/SP", maxLength: 64 })}
              {input("telefone", "Telefone")}
              {input("email", "E-mail")}
            </div>
            <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Endereço (a cidade é o local de assinatura)
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              {input("endereco_cep", "CEP")}
              <div className="sm:col-span-2">{input("endereco_logradouro", "Logradouro")}</div>
              {input("endereco_numero", "Número")}
              {input("endereco_complemento", "Complemento")}
              {input("endereco_bairro", "Bairro")}
              {input("endereco_cidade", "Cidade")}
              {input("endereco_uf", "UF", { maxLength: 2, upper: true })}
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={submit}
              disabled={!podeSalvar || salvando}
              data-testid="imobiliaria-salvar"
            >
              {salvando ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!removendo} onOpenChange={(o) => !o && setRemovendo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover imobiliária</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover {removendo?.razao_social} do cadastro? Ela
              deixa de aparecer para novos contratos.
              {removendo && removendo.contratos_em_uso > 0 && (
                <span
                  className="mt-2 block font-medium text-amber-700"
                  data-testid="imobiliaria-remover-em-uso"
                >
                  Atenção:{" "}
                  {removendo.contratos_em_uso === 1
                    ? "1 contrato usa esta imobiliária"
                    : `${removendo.contratos_em_uso} contratos usam esta imobiliária`}
                  . Esses contratos não são alterados e continuam com ela.
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => removendo && remover(removendo)}
              className="bg-destructive hover:bg-destructive/90"
              data-testid="imobiliaria-confirmar-remover"
            >
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
