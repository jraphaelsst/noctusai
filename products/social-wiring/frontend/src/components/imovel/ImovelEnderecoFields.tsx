/**
 * ImovelEnderecoFields — the address inputs shared by `ImovelCodigoPicker`'s
 * "cadastrar novo" form and `ImovelManualModal` (one copy, never two).
 *
 * Controlled + presentational. Required: logradouro, número, bairro, cidade,
 * UF; complemento optional; `cepObrigatorio` decides CEP (the picker's
 * registration still requires it; the manual modal treats it as optional but
 * format-checked, as the BE does).
 */
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface EnderecoDraft {
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
  cep: string;
}

export const ENDERECO_VAZIO: EnderecoDraft = {
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "",
  uf: "",
  cep: "",
};

export const CEP_RE = /^\d{5}-?\d{3}$/;
export const UF_RE = /^[A-Za-z]{2}$/;

export type EnderecoErros = Partial<Record<keyof EnderecoDraft, string>>;

/** Client-side mirror of the BE rule: 5 required fields, UF = 2 letters, CEP format. */
export function validarEndereco(
  d: EnderecoDraft,
  cepObrigatorio = false,
): EnderecoErros {
  const e: EnderecoErros = {};
  if (!d.logradouro.trim()) e.logradouro = "Informe o logradouro.";
  if (!d.numero.trim()) e.numero = "Informe o número.";
  if (!d.bairro.trim()) e.bairro = "Informe o bairro.";
  if (!d.cidade.trim()) e.cidade = "Informe a cidade.";
  if (!UF_RE.test(d.uf.trim())) e.uf = "UF com 2 letras.";
  const cep = d.cep.trim();
  if (cep ? !CEP_RE.test(cep) : cepObrigatorio)
    e.cep = "CEP no formato 00000-000.";
  return e;
}

interface Props {
  value: EnderecoDraft;
  onChange: (next: EnderecoDraft) => void;
  disabled?: boolean;
  idPrefix: string;
  testIdPrefix: string;
  cepObrigatorio?: boolean;
  errors?: EnderecoErros;
}

export default function ImovelEnderecoFields({
  value,
  onChange,
  disabled,
  idPrefix,
  testIdPrefix,
  cepObrigatorio = false,
  errors = {},
}: Props) {
  const set = (k: keyof EnderecoDraft, v: string) =>
    onChange({ ...value, [k]: v });
  const erro = (k: keyof EnderecoDraft) =>
    errors[k] ? (
      <p
        className="text-xs text-destructive"
        data-testid={`${testIdPrefix}-${k}-erro`}
      >
        {errors[k]}
      </p>
    ) : null;

  return (
    <div className="space-y-1.5">
      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-logradouro`} className="text-xs">
          Logradouro *
        </Label>
        <Input
          id={`${idPrefix}-logradouro`}
          value={value.logradouro}
          onChange={(e) => set("logradouro", e.target.value)}
          placeholder="Ex.: Alameda Alemanha"
          disabled={disabled}
          data-testid={`${testIdPrefix}-logradouro`}
        />
        {erro("logradouro")}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-numero`} className="text-xs">
            Número *
          </Label>
          <Input
            id={`${idPrefix}-numero`}
            value={value.numero}
            onChange={(e) => set("numero", e.target.value)}
            placeholder="Ex.: 535"
            disabled={disabled}
            data-testid={`${testIdPrefix}-numero`}
          />
          {erro("numero")}
        </div>
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-complemento`} className="text-xs">
            Complemento
          </Label>
          <Input
            id={`${idPrefix}-complemento`}
            value={value.complemento}
            onChange={(e) => set("complemento", e.target.value)}
            placeholder="Ex.: Apto 535"
            disabled={disabled}
            data-testid={`${testIdPrefix}-complemento`}
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-bairro`} className="text-xs">
          Bairro *
        </Label>
        <Input
          id={`${idPrefix}-bairro`}
          value={value.bairro}
          onChange={(e) => set("bairro", e.target.value)}
          placeholder="Ex.: Euroville - Km 23"
          disabled={disabled}
          data-testid={`${testIdPrefix}-bairro`}
        />
        {erro("bairro")}
      </div>
      <div className="grid grid-cols-[1fr_auto] gap-1.5">
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-cidade`} className="text-xs">
            Cidade *
          </Label>
          <Input
            id={`${idPrefix}-cidade`}
            value={value.cidade}
            onChange={(e) => set("cidade", e.target.value)}
            placeholder="Ex.: São Paulo"
            disabled={disabled}
            data-testid={`${testIdPrefix}-cidade`}
          />
          {erro("cidade")}
        </div>
        <div className="w-16 space-y-1">
          <Label htmlFor={`${idPrefix}-uf`} className="text-xs">
            UF *
          </Label>
          <Input
            id={`${idPrefix}-uf`}
            value={value.uf}
            onChange={(e) => set("uf", e.target.value.toUpperCase())}
            maxLength={2}
            placeholder="SP"
            disabled={disabled}
            data-testid={`${testIdPrefix}-uf`}
          />
          {erro("uf")}
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-cep`} className="text-xs">
          CEP{cepObrigatorio ? " *" : ""}
        </Label>
        <Input
          id={`${idPrefix}-cep`}
          value={value.cep}
          onChange={(e) => set("cep", e.target.value)}
          maxLength={9}
          placeholder="Ex.: 06355-465"
          disabled={disabled}
          data-testid={`${testIdPrefix}-cep`}
        />
        {erro("cep")}
      </div>
    </div>
  );
}
