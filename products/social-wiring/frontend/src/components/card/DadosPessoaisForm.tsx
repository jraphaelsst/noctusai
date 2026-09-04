/**
 * `<DadosPessoaisForm/>` — the fields the document checklist derives from.
 *
 * Presentational (S3): `onSave` is the only callback out.
 *
 * 🔴 WHY THIS EXISTS AT ALL
 * -------------------------
 * Until now the card could SHOW that "Profissão" was outstanding and offered
 * nowhere to fill it in. The backend has accepted these columns on
 * `PATCH /api/clientes/{id}` since migration 068, but no UI ever sent them, so
 * four of the checklist's items were unfillable by any means the operator had
 * — a permanently-red gate, and permanently-red gates stop being read.
 *
 * It is the same failure migration 068's `nome_completo` note describes from
 * the other end, and the reason the checklist and this form are rendered
 * together: the list of what is missing sits directly above the place to
 * supply it.
 *
 * FIELD ORDER IS THE CHECKLIST'S ORDER
 * ------------------------------------
 * Deliberately, and it is not decoration: the sequence is the one an operator
 * actually collects details in, so the form reads top-to-bottom as the
 * conversation goes. RG and CPF are absent because they are satisfied by
 * UPLOADING a document, not by typing — they live in Anexos below.
 *
 * 🔴 GÊNERO'S DEFAULT IS A CONVENIENCE, NOT A VALUE
 * -------------------------------------------------
 * The dropdown shows "Masculino" pre-selected so the common case is one click.
 * Nothing is written until Save, and the checkbox does not tick before then —
 * if an unsaved default counted as data, this item would read green for every
 * existing cliente the day it shipped and could never again answer "who still
 * needs checking".
 */
import { useEffect, useState } from "react";
import { Check, Pencil, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { TooltipIconButton } from "./TooltipIconButton";

/** The taxonomy the UI offers. The COLUMN is unconstrained TEXT on purpose
 *  (migration 068) — a CHECK would freeze a product decision into the schema —
 *  so widening this list needs no migration. */
export const GENEROS = ["Masculino", "Feminino"] as const;

export const GENERO_PADRAO = GENEROS[0];

export interface DadosPessoais {
  nome_completo?: string | null;
  celular?: string | null;
  email?: string | null;
  data_nascimento?: string | null;
  profissao?: string | null;
  genero?: string | null;

  // ─── Qualificação civil (migration 097) ────────────────────────────────
  //
  // What an "Instrumento Particular de Promessa de Compra e Venda" needs to
  // NAME a party: nome, nacionalidade, estado civil (with regime de bens),
  // profissão, CPF, RG with issuing body, endereço. Of those seven this form
  // used to collect two.
  cpf?: string | null;
  rg?: string | null;
  /** Issuing body and UF as printed — "SSP/SP". Travels with `rg`: a number
   *  without its issuer is an incomplete qualification. */
  rg_orgao_expedidor?: string | null;
  /** 🔴 Decides whether a spouse must sign. Not a preference field. */
  estado_civil?: string | null;
  regime_bens?: string | null;
  nacionalidade?: string | null;
  endereco_cep?: string | null;
  endereco_logradouro?: string | null;
  endereco_numero?: string | null;
  endereco_complemento?: string | null;
  endereco_bairro?: string | null;
  endereco_cidade?: string | null;
  endereco_uf?: string | null;
}

/**
 * Offered for `estado_civil`. Unconstrained TEXT in the database on purpose
 * (migration 097) — the taxonomy is a product decision, so it lives here
 * beside the dropdown rather than as a CHECK that makes each addition a
 * migration.
 */
export const ESTADOS_CIVIS = [
  "Solteiro(a)",
  "Casado(a)",
  "Divorciado(a)",
  "Viúvo(a)",
  "Separado(a)",
  "União estável",
] as const;

/** Regimes de bens. Only meaningful alongside a married state — the form
 *  shows the field regardless rather than hiding it, because an operator
 *  filling a card top-to-bottom should not have a field appear and disappear
 *  under the cursor. */
export const REGIMES_BENS = [
  "Comunhão parcial de bens",
  "Comunhão universal de bens",
  "Separação total de bens",
  "Separação obrigatória de bens",
  "Participação final nos aquestos",
] as const;

/** Sentinel for "not set" in a Select. Radix treats `value=""` as
 *  uncontrolled, so a real token is needed and is mapped back to null on
 *  save. */
const NAO_INFORMADO = "__nao_informado__";

export interface DadosPessoaisFormProps {
  valores: DadosPessoais;
  onSave: (valores: DadosPessoais) => void;
  saving?: boolean;
  /** Disambiguates the testids when several of these are on screen at once —
   *  one per party on the Documentos tab. */
  testId?: string;
}

function texto(v: string | null | undefined): string {
  return v ?? "";
}

export function DadosPessoaisForm({
  valores,
  onSave,
  saving,
  testId = "dados-pessoais",
}: DadosPessoaisFormProps) {
  const [aberto, setAberto] = useState(false);
  const [draft, setDraft] = useState<DadosPessoais>(valores);

  // Re-seeded when the record changes underneath — an extraction confirming a
  // birthdate writes the column, and a stale draft would silently overwrite it
  // on the next Save.
  useEffect(() => {
    setDraft(valores);
  }, [
    valores.nome_completo,
    valores.celular,
    valores.email,
    valores.data_nascimento,
    valores.profissao,
    valores.genero,
    // 097's fields re-seed on the same terms: an extraction that confirms a
    // CPF writes the column, and a stale draft would overwrite it on Save.
    valores.cpf,
    valores.rg,
    valores.rg_orgao_expedidor,
    valores.estado_civil,
    valores.regime_bens,
    valores.nacionalidade,
    valores.endereco_cep,
    valores.endereco_logradouro,
    valores.endereco_numero,
    valores.endereco_complemento,
    valores.endereco_bairro,
    valores.endereco_cidade,
    valores.endereco_uf,
  ]);

  function campo<K extends keyof DadosPessoais>(k: K, v: string) {
    setDraft((d) => ({ ...d, [k]: v === "" ? null : v }));
  }

  function submit() {
    onSave({
      ...draft,
      // The displayed default becomes a real value only here, at Save.
      genero: draft.genero ?? GENERO_PADRAO,
    });
    setAberto(false);
  }

  if (!aberto) {
    return (
      <div className="mb-4">
        {/* Icon-only, caption on hover — and the SAME string on `aria-label`,
            because a hover caption is invisible to a screen reader. */}
        <TooltipIconButton
          label="Editar dados"
          icon={Pencil}
          variant="outline"
          testId={`${testId}-editar-btn`}
          onClick={() => {
            setDraft(valores);
            setAberto(true);
          }}
        />
      </div>
    );
  }

  return (
    <div className="mb-4 space-y-3 rounded-md border p-3" data-testid={testId}>
      <Campo rotulo="Nome Completo" htmlFor={`${testId}-nome`}>
        <Input
          id={`${testId}-nome`}
          value={texto(draft.nome_completo)}
          onChange={(e) => campo("nome_completo", e.target.value)}
          data-testid={`${testId}-nome`}
        />
      </Campo>

      <Campo rotulo="Celular" htmlFor={`${testId}-celular`}>
        <Input
          id={`${testId}-celular`}
          value={texto(draft.celular)}
          onChange={(e) => campo("celular", e.target.value)}
          placeholder="+55 11 99999-8888"
          data-testid={`${testId}-celular`}
        />
      </Campo>

      <Campo rotulo="Email" htmlFor={`${testId}-email`}>
        <Input
          id={`${testId}-email`}
          type="email"
          value={texto(draft.email)}
          onChange={(e) => campo("email", e.target.value)}
          data-testid={`${testId}-email`}
        />
      </Campo>

      <Campo rotulo="Data de Nascimento" htmlFor={`${testId}-nascimento`}>
        <Input
          id={`${testId}-nascimento`}
          type="date"
          value={texto(draft.data_nascimento)}
          onChange={(e) => campo("data_nascimento", e.target.value)}
          data-testid={`${testId}-nascimento`}
        />
      </Campo>

      <Campo rotulo="Profissão" htmlFor={`${testId}-profissao`}>
        <Input
          id={`${testId}-profissao`}
          value={texto(draft.profissao)}
          onChange={(e) => campo("profissao", e.target.value)}
          data-testid={`${testId}-profissao`}
        />
      </Campo>

      <Campo rotulo="Gênero" htmlFor={`${testId}-genero`}>
        <Select
          value={draft.genero ?? GENERO_PADRAO}
          onValueChange={(v) => campo("genero", v)}
        >
          <SelectTrigger id={`${testId}-genero`} data-testid={`${testId}-genero`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GENEROS.map((g) => (
              <SelectItem key={g} value={g}>
                {g}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Campo>

      {/* ─── Qualificação civil (migration 097) ────────────────────────────
          The block a contract needs and a CRM never did. Grouped and labelled
          as such so it reads as one job — "qualify this person" — rather than
          seven more boxes appended to the contact details above. */}
      <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Qualificação
      </p>

      <Campo rotulo="CPF" htmlFor={`${testId}-cpf`}>
        <Input
          id={`${testId}-cpf`}
          value={texto(draft.cpf)}
          onChange={(e) => campo("cpf", e.target.value)}
          placeholder="412.954.238-98"
          data-testid={`${testId}-cpf`}
        />
      </Campo>

      <div className="grid grid-cols-2 gap-2">
        <Campo rotulo="RG" htmlFor={`${testId}-rg`}>
          <Input
            id={`${testId}-rg`}
            value={texto(draft.rg)}
            onChange={(e) => campo("rg", e.target.value)}
            placeholder="52.179.965-X"
            data-testid={`${testId}-rg`}
          />
        </Campo>
        {/* Side by side with the number because the two are one fact: an RG
            without its issuer does not identify a document. */}
        <Campo rotulo="Órgão expedidor" htmlFor={`${testId}-rg-orgao`}>
          <Input
            id={`${testId}-rg-orgao`}
            value={texto(draft.rg_orgao_expedidor)}
            onChange={(e) => campo("rg_orgao_expedidor", e.target.value)}
            placeholder="SSP/SP"
            data-testid={`${testId}-rg-orgao`}
          />
        </Campo>
      </div>

      <Campo rotulo="Nacionalidade" htmlFor={`${testId}-nacionalidade`}>
        <Input
          id={`${testId}-nacionalidade`}
          value={texto(draft.nacionalidade)}
          onChange={(e) => campo("nacionalidade", e.target.value)}
          placeholder="brasileiro(a)"
          data-testid={`${testId}-nacionalidade`}
        />
      </Campo>

      <div className="grid grid-cols-2 gap-2">
        <Campo rotulo="Estado civil" htmlFor={`${testId}-estado-civil`}>
          <Select
            value={draft.estado_civil ?? NAO_INFORMADO}
            onValueChange={(v) =>
              campo("estado_civil", v === NAO_INFORMADO ? "" : v)
            }
          >
            <SelectTrigger
              id={`${testId}-estado-civil`}
              data-testid={`${testId}-estado-civil`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NAO_INFORMADO}>Não informado</SelectItem>
              {ESTADOS_CIVIS.map((e) => (
                <SelectItem key={e} value={e}>
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Campo>
        {/* Always rendered, never conditional on `estado_civil`. A field that
            appears and disappears as the box above changes moves the form
            under the cursor of somebody filling it top-to-bottom — and the
            database deliberately does not tie the two either (097). */}
        <Campo rotulo="Regime de bens" htmlFor={`${testId}-regime-bens`}>
          <Select
            value={draft.regime_bens ?? NAO_INFORMADO}
            onValueChange={(v) =>
              campo("regime_bens", v === NAO_INFORMADO ? "" : v)
            }
          >
            <SelectTrigger
              id={`${testId}-regime-bens`}
              data-testid={`${testId}-regime-bens`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NAO_INFORMADO}>Não informado</SelectItem>
              {REGIMES_BENS.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Campo>
      </div>

      <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Endereço
      </p>

      <div className="grid grid-cols-3 gap-2">
        <Campo rotulo="CEP" htmlFor={`${testId}-cep`}>
          <Input
            id={`${testId}-cep`}
            value={texto(draft.endereco_cep)}
            onChange={(e) => campo("endereco_cep", e.target.value)}
            placeholder="05407-002"
            data-testid={`${testId}-cep`}
          />
        </Campo>
        <div className="col-span-2">
          <Campo rotulo="Logradouro" htmlFor={`${testId}-logradouro`}>
            <Input
              id={`${testId}-logradouro`}
              value={texto(draft.endereco_logradouro)}
              onChange={(e) => campo("endereco_logradouro", e.target.value)}
              data-testid={`${testId}-logradouro`}
            />
          </Campo>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Campo rotulo="Número" htmlFor={`${testId}-numero`}>
          <Input
            id={`${testId}-numero`}
            value={texto(draft.endereco_numero)}
            onChange={(e) => campo("endereco_numero", e.target.value)}
            data-testid={`${testId}-numero`}
          />
        </Campo>
        <Campo rotulo="Complemento" htmlFor={`${testId}-complemento`}>
          <Input
            id={`${testId}-complemento`}
            value={texto(draft.endereco_complemento)}
            onChange={(e) => campo("endereco_complemento", e.target.value)}
            data-testid={`${testId}-complemento`}
          />
        </Campo>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Campo rotulo="Bairro" htmlFor={`${testId}-bairro`}>
          <Input
            id={`${testId}-bairro`}
            value={texto(draft.endereco_bairro)}
            onChange={(e) => campo("endereco_bairro", e.target.value)}
            data-testid={`${testId}-bairro`}
          />
        </Campo>
        <Campo rotulo="Cidade" htmlFor={`${testId}-cidade`}>
          <Input
            id={`${testId}-cidade`}
            value={texto(draft.endereco_cidade)}
            onChange={(e) => campo("endereco_cidade", e.target.value)}
            data-testid={`${testId}-cidade`}
          />
        </Campo>
        <Campo rotulo="UF" htmlFor={`${testId}-uf`}>
          <Input
            id={`${testId}-uf`}
            value={texto(draft.endereco_uf)}
            onChange={(e) => campo("endereco_uf", e.target.value.toUpperCase())}
            maxLength={2}
            placeholder="SP"
            data-testid={`${testId}-uf`}
          />
        </Campo>
      </div>

      <div className="flex gap-1">
        <TooltipIconButton
          label={saving ? "Salvando…" : "Salvar dados"}
          icon={Check}
          variant="default"
          disabled={saving}
          onClick={submit}
          testId={`${testId}-salvar`}
        />
        <TooltipIconButton
          label="Cancelar"
          icon={X}
          onClick={() => setAberto(false)}
          testId={`${testId}-cancelar`}
        />
      </div>
    </div>
  );
}

function Campo({
  rotulo,
  htmlFor,
  children,
}: {
  rotulo: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium text-muted-foreground"
      >
        {rotulo}
      </label>
      {children}
    </div>
  );
}
