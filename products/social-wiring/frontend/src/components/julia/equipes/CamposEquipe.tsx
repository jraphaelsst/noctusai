/** Shared form sections of a team (wizard steps 1 and 3, and the "Configurações" drawer). */
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { EquipeInput, ModoDistribuicao } from "@/hooks/useJuliaEquipes";

export type CamposValor = EquipeInput;

export const CAMPOS_PADRAO: CamposValor = {
  nome: "", atende_apos_julia: true, modo: "funil", manter_ultimo: false,
};

interface Props { valor: CamposValor; onChange: (p: Partial<CamposValor>) => void }

export function Passo1Campos({ valor, onChange }: Props) {
  return (
    <div className="space-y-5">
      <label className="block space-y-1.5 text-sm font-medium">
        Nome da equipe*
        <Input value={valor.nome} placeholder="Ex.: Comercial" data-testid="equipe-nome"
          onChange={(e) => onChange({ nome: e.target.value })} />
      </label>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Esta equipe atende clientes diretamente após a Julia?</legend>
        <label className="flex items-start gap-2 text-sm">
          <input type="radio" name="atende" className="mt-1" checked={valor.atende_apos_julia}
            onChange={() => onChange({ atende_apos_julia: true })} />
          <span><b>Sim</b><br /><span className="text-muted-foreground">A equipe assume conversas assim que a Julia conclui o pré-atendimento.</span></span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input type="radio" name="atende" className="mt-1" checked={!valor.atende_apos_julia}
            onChange={() => onChange({ atende_apos_julia: false })} />
          <span><b>Não</b><br /><span className="text-muted-foreground">A equipe só recebe atribuições manuais pela página de Conversas.</span></span>
        </label>
      </fieldset>
    </div>
  );
}

const MODOS: { key: ModoDistribuicao; titulo: string; desc?: string }[] = [
  { key: "funil", titulo: "Via funil do SW (Padrão)" },
  { key: "julia", titulo: "Via Julia (Atendimento mais rápido)",
    desc: "A Julia atribui leads diretamente aos atendentes assim que o pré-atendimento termina." },
];

export function Passo3Campos({ valor, onChange }: Props) {
  return (
    <div className="space-y-5">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Como os leads serão atribuídos?</legend>
        {MODOS.map((m) => (
          <label key={m.key} className="flex items-start gap-2 text-sm">
            <input type="radio" name="modo" className="mt-1" checked={valor.modo === m.key}
              onChange={() => onChange({ modo: m.key })} />
            <span><b>{m.titulo}</b>{m.desc && <><br /><span className="text-muted-foreground">{m.desc}</span></>}</span>
          </label>
        ))}
      </fieldset>
      <label className="flex items-center justify-between gap-3 text-sm">
        Manter atribuição ao último responsável
        <Switch checked={valor.manter_ultimo} aria-label="Manter atribuição ao último responsável"
          onCheckedChange={(v) => onChange({ manter_ultimo: v })} />
      </label>
    </div>
  );
}
