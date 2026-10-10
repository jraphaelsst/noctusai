/**
 * ImovelManualModal — "Cadastrar imóvel" / "Editar imóvel" (S6, CONTRACT §8.4).
 *
 * One modal for create and edit (edit = `imovel` prop, prefilled; the PATCH
 * sends only what changed, an emptied field as `null`). Every editable field of
 * `ImovelManualIn`, grouped: Identificação · Endereço · Valores · Áreas e
 * cômodos · Descrição · Referências do negócio.
 *
 * Organ check (noc-organ-consume-check, 2026-10-09): `@noctusai/lib` ships no
 * form/dialog-with-fields organ (EntityDetailDialog is read-only, CardHubDialog
 * is the card hub), so the shell is the product's own `ui/dialog` — same as
 * `MarcaModal` — and the address block is the single shared
 * `ImovelEnderecoFields` also used by `ImovelCodigoPicker`.
 *
 * Validation mirrors the BE: título, logradouro, número, bairro, cidade, UF
 * (2 letras) required; CEP `00000-000` when given; valores/áreas > 0, contagens
 * >= 0; Drive URL `https://drive.google.com/…/folders/<id>`.
 */
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import ImovelEnderecoFields, {
  ENDERECO_VAZIO,
  validarEndereco,
  type EnderecoDraft,
  type EnderecoErros,
} from "@/components/imovel/ImovelEnderecoFields";
import type { Imovel } from "@/hooks/useImoveis";
import {
  driveUrlValida,
  useAtualizarImovelManual,
  useCriarImovelManual,
  type ImovelManualBody,
  type ImovelManualPatch,
} from "@/hooks/useImovelManual";

const STATUS_OPCOES = ["Venda", "Aluguel", "Venda e Aluguel"];

type NumKey =
  | "valor_venda"
  | "valor_locacao"
  | "valor_condominio"
  | "valor_iptu"
  | "area_total"
  | "area_privativa"
  | "area_construida"
  | "dormitorios"
  | "suites"
  | "vagas";
const VALOR_KEYS: NumKey[] = [
  "valor_venda",
  "valor_locacao",
  "valor_condominio",
  "valor_iptu",
];
const AREA_KEYS: NumKey[] = ["area_total", "area_privativa", "area_construida"];
const CONTAGEM_KEYS: NumKey[] = ["dormitorios", "suites", "vagas"];
const NUM_LABEL: Record<NumKey, string> = {
  valor_venda: "Valor de venda (R$)",
  valor_locacao: "Valor de locação (R$/mês)",
  valor_condominio: "Condomínio (R$)",
  valor_iptu: "IPTU (R$)",
  area_total: "Área total (m²)",
  area_privativa: "Área privativa (m²)",
  area_construida: "Área construída (m²)",
  dormitorios: "Dormitórios",
  suites: "Suítes",
  vagas: "Vagas",
};

export interface ImovelDraft extends Record<NumKey, string> {
  titulo: string;
  categoria: string;
  status: string;
  finalidades: string;
  descricao_web: string;
  observacoes: string;
  empreendimento: string;
  em_condominio: boolean;
  processo_atual_numero: string;
  drive_folder_url: string;
  endereco: EnderecoDraft;
}

const VAZIO: ImovelDraft = {
  titulo: "",
  categoria: "",
  status: "",
  finalidades: "",
  valor_venda: "",
  valor_locacao: "",
  valor_condominio: "",
  valor_iptu: "",
  area_total: "",
  area_privativa: "",
  area_construida: "",
  dormitorios: "",
  suites: "",
  vagas: "",
  descricao_web: "",
  observacoes: "",
  empreendimento: "",
  em_condominio: false,
  processo_atual_numero: "",
  drive_folder_url: "",
  endereco: ENDERECO_VAZIO,
};

const s = (v: unknown) => (v === null || v === undefined ? "" : String(v));

export function draftDoImovel(
  i?: Imovel | null,
  emCondominio?: boolean | null,
): ImovelDraft {
  if (!i) return VAZIO;
  return {
    titulo: s(i.titulo),
    categoria: s(i.categoria),
    status: s(i.status),
    finalidades: (i.finalidades ?? []).join(", "),
    valor_venda: s(i.valor_venda),
    valor_locacao: s(i.valor_locacao),
    valor_condominio: s(i.valor_condominio),
    valor_iptu: s(i.valor_iptu),
    area_total: s(i.area_total),
    area_privativa: s(i.area_privativa),
    area_construida: s(i.area_construida),
    dormitorios: s(i.dormitorios),
    suites: s(i.suites),
    vagas: s(i.vagas),
    descricao_web: s(i.descricao_web),
    observacoes: s(i.observacoes),
    empreendimento: s(i.empreendimento),
    em_condominio: emCondominio === true,
    processo_atual_numero: s(i.referencias?.processo_atual_numero),
    drive_folder_url: s(i.referencias?.drive_folder_url),
    endereco: {
      logradouro: s(i.logradouro),
      numero: s(i.numero),
      complemento: s(i.complemento),
      bairro: s(i.bairro),
      cidade: s(i.cidade),
      uf: s(i.uf),
      cep: s(i.cep),
    },
  };
}

/** "1.234,56" / "1234.56" / "1234,56" → number; "" → null; garbage → NaN. */
export function parseNumero(texto: string): number | null {
  const t = texto.trim();
  if (!t) return null;
  const normal = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  return /^\d+(\.\d+)?$/.test(normal) ? Number(normal) : Number.NaN;
}

type Erros = Partial<Record<NumKey | "titulo" | "drive_folder_url", string>> & {
  endereco: EnderecoErros;
};

export function validar(d: ImovelDraft): Erros {
  const erros: Erros = { endereco: validarEndereco(d.endereco) };
  if (!d.titulo.trim()) erros.titulo = "Informe o título.";
  for (const k of [...VALOR_KEYS, ...AREA_KEYS]) {
    const n = parseNumero(d[k]);
    if (n !== null && !(n > 0)) erros[k] = "Informe um número maior que zero.";
  }
  for (const k of CONTAGEM_KEYS) {
    const n = parseNumero(d[k]);
    if (n !== null && !(Number.isInteger(n) && n >= 0))
      erros[k] = "Informe um inteiro >= 0.";
  }
  if (d.drive_folder_url.trim() && !driveUrlValida(d.drive_folder_url)) {
    erros.drive_folder_url =
      "Use o link de uma pasta: https://drive.google.com/…/folders/<id>";
  }
  return erros;
}

const temErro = (e: Erros) =>
  Object.entries(e).some(([k, v]) =>
    k === "endereco" ? Object.keys(v as object).length > 0 : !!v,
  );

const txt = (v: string) => v.trim() || null;
const lista = (v: string) =>
  v
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
const enderecoBody = (e: EnderecoDraft) => ({
  cep: txt(e.cep),
  logradouro: e.logradouro.trim(),
  numero: e.numero.trim(),
  complemento: txt(e.complemento),
  bairro: e.bairro.trim(),
  cidade: e.cidade.trim(),
  uf: e.uf.trim().toUpperCase(),
});

/** Full body for create. */
export function corpoCriacao(d: ImovelDraft): ImovelManualBody {
  const body: ImovelManualBody = {
    titulo: d.titulo.trim(),
    categoria: txt(d.categoria),
    status: txt(d.status),
    finalidades: lista(d.finalidades),
    descricao_web: txt(d.descricao_web),
    observacoes: txt(d.observacoes),
    empreendimento: txt(d.empreendimento),
    em_condominio: d.em_condominio,
    processo_atual_numero: txt(d.processo_atual_numero),
    drive_folder_url: txt(d.drive_folder_url),
    endereco: enderecoBody(d.endereco),
  };
  for (const k of [...VALOR_KEYS, ...AREA_KEYS, ...CONTAGEM_KEYS])
    body[k] = parseNumero(d[k]);
  return body;
}

/** Only what changed vs. the prefill; an emptied field goes as `null`. */
export function corpoEdicao(
  d: ImovelDraft,
  inicial: ImovelDraft,
): ImovelManualPatch {
  const full = corpoCriacao(d);
  const base = corpoCriacao(inicial);
  const patch: Record<string, unknown> = {};
  for (const k of Object.keys(full) as (keyof ImovelManualBody)[]) {
    if (JSON.stringify(full[k]) !== JSON.stringify(base[k])) patch[k] = full[k];
  }
  return patch as ImovelManualPatch;
}

function Campo({
  id,
  label,
  erro,
  children,
}: {
  id: string;
  label: string;
  erro?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      {children}
      {erro && (
        <p className="text-xs text-destructive" data-testid={`${id}-erro`}>
          {erro}
        </p>
      )}
    </div>
  );
}

function Grupo({
  titulo,
  children,
}: {
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-sm font-semibold">{titulo}</legend>
      {children}
    </fieldset>
  );
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present = edit mode, prefilled. */
  imovel?: Imovel | null;
  /** `imovel_dados.em_condominio` (not on the Imovel shape) for the edit prefill. */
  emCondominio?: boolean | null;
  /** Called with the saved imóvel's código (create → caller navigates). */
  onSaved?: (codigo: string) => void;
}

export default function ImovelManualModal({
  open,
  onOpenChange,
  imovel,
  emCondominio,
  onSaved,
}: Props) {
  const edicao = Boolean(imovel);
  const inicial = draftDoImovel(imovel, emCondominio);
  const [draft, setDraft] = useState<ImovelDraft>(inicial);
  const [mostrarErros, setMostrarErros] = useState(false);
  const [erroServidor, setErroServidor] = useState<string | null>(null);
  const criar = useCriarImovelManual();
  const atualizar = useAtualizarImovelManual(imovel?.codigo ?? "");
  const salvando = criar.isPending || atualizar.isPending;

  // Re-seed whenever the modal (re)opens or a different imóvel is loaded.
  useEffect(() => {
    if (open) {
      setDraft(draftDoImovel(imovel, emCondominio));
      setMostrarErros(false);
      setErroServidor(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, imovel?.codigo, emCondominio]);

  const erros = validar(draft);
  const set = <K extends keyof ImovelDraft>(k: K, v: ImovelDraft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));
  const mostrar = (k: keyof Erros) =>
    mostrarErros ? (erros[k] as string | undefined) : undefined;

  async function submeter(ev: React.FormEvent) {
    ev.preventDefault();
    setErroServidor(null);
    if (temErro(erros)) {
      setMostrarErros(true);
      return;
    }
    try {
      if (imovel) {
        const patch = corpoEdicao(draft, inicial);
        if (Object.keys(patch).length === 0) {
          onOpenChange(false);
          return;
        }
        const res = await atualizar.mutateAsync(patch);
        toast.success(`Imóvel ${res.codigo} atualizado.`);
        onSaved?.(res.codigo);
      } else {
        const res = await criar.mutateAsync(corpoCriacao(draft));
        toast.success(`Imóvel ${res.codigo} cadastrado.`);
        onSaved?.(res.codigo);
      }
      onOpenChange(false);
    } catch (err) {
      setErroServidor(
        err instanceof Error
          ? err.message
          : "Não foi possível salvar o imóvel.",
      );
    }
  }

  const numero = (k: NumKey) => (
    <Campo
      key={k}
      id={`imovel-manual-${k}`}
      label={NUM_LABEL[k]}
      erro={mostrar(k)}
    >
      <Input
        id={`imovel-manual-${k}`}
        inputMode="decimal"
        value={draft[k]}
        onChange={(e) => set(k, e.target.value)}
        disabled={salvando}
        data-testid={`imovel-manual-${k}`}
      />
    </Campo>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        data-testid="imovel-manual-modal"
      >
        <DialogHeader>
          <DialogTitle>
            {edicao ? `Editar imóvel ${imovel?.codigo}` : "Cadastrar imóvel"}
          </DialogTitle>
          <DialogDescription>
            {edicao
              ? "Altere os dados deste imóvel cadastrado na plataforma."
              : "Registre uma nova captação. O código é gerado automaticamente."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submeter} className="space-y-4" noValidate>
          <Grupo titulo="Identificação">
            <Campo
              id="imovel-manual-titulo"
              label="Título *"
              erro={mostrar("titulo")}
            >
              <Input
                id="imovel-manual-titulo"
                value={draft.titulo}
                onChange={(e) => set("titulo", e.target.value)}
                disabled={salvando}
                data-testid="imovel-manual-titulo"
              />
            </Campo>
            <div className="grid gap-3 sm:grid-cols-3">
              <Campo id="imovel-manual-categoria" label="Categoria">
                <Input
                  id="imovel-manual-categoria"
                  value={draft.categoria}
                  onChange={(e) => set("categoria", e.target.value)}
                  placeholder="Ex.: Apartamento"
                  disabled={salvando}
                  data-testid="imovel-manual-categoria"
                />
              </Campo>
              <Campo id="imovel-manual-status" label="Finalidade">
                <select
                  id="imovel-manual-status"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  value={draft.status}
                  onChange={(e) => set("status", e.target.value)}
                  disabled={salvando}
                  data-testid="imovel-manual-status"
                >
                  <option value="">—</option>
                  {STATUS_OPCOES.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo
                id="imovel-manual-finalidades"
                label="Finalidades (vírgula)"
              >
                <Input
                  id="imovel-manual-finalidades"
                  value={draft.finalidades}
                  onChange={(e) => set("finalidades", e.target.value)}
                  disabled={salvando}
                  data-testid="imovel-manual-finalidades"
                />
              </Campo>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo
                id="imovel-manual-empreendimento"
                label="Empreendimento / condomínio"
              >
                <Input
                  id="imovel-manual-empreendimento"
                  value={draft.empreendimento}
                  onChange={(e) => set("empreendimento", e.target.value)}
                  disabled={salvando}
                  data-testid="imovel-manual-empreendimento"
                />
              </Campo>
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.em_condominio}
                  onChange={(e) => set("em_condominio", e.target.checked)}
                  disabled={salvando}
                  data-testid="imovel-manual-em_condominio"
                />
                Em condomínio
              </label>
            </div>
          </Grupo>

          <Grupo titulo="Endereço">
            <ImovelEnderecoFields
              value={draft.endereco}
              onChange={(e) => set("endereco", e)}
              disabled={salvando}
              idPrefix="imovel-manual-end"
              testIdPrefix="imovel-manual-end"
              errors={mostrarErros ? erros.endereco : {}}
            />
          </Grupo>

          <Grupo titulo="Valores">
            <div className="grid gap-3 sm:grid-cols-2">
              {VALOR_KEYS.map(numero)}
            </div>
          </Grupo>

          <Grupo titulo="Áreas e cômodos">
            <div className="grid gap-3 sm:grid-cols-3">
              {AREA_KEYS.map(numero)}
              {CONTAGEM_KEYS.map(numero)}
            </div>
          </Grupo>

          <Grupo titulo="Descrição">
            <Campo id="imovel-manual-descricao_web" label="Descrição">
              <Textarea
                id="imovel-manual-descricao_web"
                value={draft.descricao_web}
                onChange={(e) => set("descricao_web", e.target.value)}
                disabled={salvando}
                rows={3}
                data-testid="imovel-manual-descricao_web"
              />
            </Campo>
            <Campo id="imovel-manual-observacoes" label="Observações internas">
              <Textarea
                id="imovel-manual-observacoes"
                value={draft.observacoes}
                onChange={(e) => set("observacoes", e.target.value)}
                disabled={salvando}
                rows={2}
                data-testid="imovel-manual-observacoes"
              />
            </Campo>
          </Grupo>

          <Grupo titulo="Referências do negócio">
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo id="imovel-manual-processo" label="Processo atual (nº)">
                <Input
                  id="imovel-manual-processo"
                  value={draft.processo_atual_numero}
                  onChange={(e) => set("processo_atual_numero", e.target.value)}
                  disabled={salvando}
                  data-testid="imovel-manual-processo"
                />
              </Campo>
              <Campo
                id="imovel-manual-drive"
                label="Pasta do Drive (link)"
                erro={mostrar("drive_folder_url")}
              >
                <Input
                  id="imovel-manual-drive"
                  value={draft.drive_folder_url}
                  onChange={(e) => set("drive_folder_url", e.target.value)}
                  placeholder="https://drive.google.com/drive/folders/…"
                  disabled={salvando}
                  data-testid="imovel-manual-drive"
                />
              </Campo>
            </div>
          </Grupo>

          {erroServidor && (
            <p
              className="text-sm text-destructive"
              role="alert"
              data-testid="imovel-manual-erro"
            >
              {erroServidor}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={salvando}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={salvando}
              data-testid="imovel-manual-salvar"
            >
              {salvando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {edicao ? "Salvar alterações" : "Cadastrar imóvel"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
