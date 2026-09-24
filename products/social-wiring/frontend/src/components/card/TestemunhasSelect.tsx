/**
 * `<TestemunhasSelect/>` — "quantas testemunhas este contrato tem, e quais":
 * a count selector plus that many "which registered witness" dropdowns.
 *
 * Presentational (S3 discipline) — `TestemunhasSelectContainer` owns the
 * data (`useContratoTestemunhas`) and the registry (`useTestemunhas`, the
 * SAME hook the Settings page and `EnviarAssinaturaDialog`'s prefill
 * already call). A CPF-incomplete registry row ("CPF pendente" — migration
 * 168) is listed but disabled: it cannot be selected for a contract until
 * an operator adds a CPF on the Testemunhas settings page.
 *
 * No duplicates: once a witness is picked in one slot it is removed from
 * every OTHER slot's options — never merely disabled there (a disabled-but-
 * visible duplicate reads as "still pickable, just not right now").
 */
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Testemunha } from "@/hooks/useTestemunhas";

export interface TestemunhasSelectProps {
  /** The org's full registry (`useTestemunhas`). */
  registro: Testemunha[];
  /** Current selection, in order — `null` slots are "count chosen, witness
   *  not picked yet". */
  selecionados: (string | null)[];
  onChangeQuantidade: (quantidade: number) => void;
  onChangeSlot: (indice: number, testemunhaId: string) => void;
  salvando?: boolean;
}

const QUANTIDADES = [0, 1, 2, 3, 4, 5];

export function TestemunhasSelect({
  registro,
  selecionados,
  onChangeQuantidade,
  onChangeSlot,
  salvando = false,
}: TestemunhasSelectProps) {
  return (
    <div className="space-y-3" data-testid="testemunhas-select">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Quantidade de testemunhas</span>
        <Select
          value={String(selecionados.length)}
          onValueChange={(v) => onChangeQuantidade(Number(v))}
          disabled={salvando}
        >
          <SelectTrigger className="h-8 w-20" data-testid="testemunhas-quantidade">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {QUANTIDADES.map((q) => (
              <SelectItem key={q} value={String(q)}>
                {q}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {selecionados.length === 0 && (
        <p className="text-xs text-muted-foreground">Nenhuma testemunha selecionada.</p>
      )}

      {selecionados.map((atual, indice) => {
        const outrosSelecionados = new Set(
          selecionados.filter((_, i) => i !== indice).filter((v): v is string => !!v),
        );
        return (
          <Select
            key={indice}
            value={atual ?? undefined}
            onValueChange={(v) => onChangeSlot(indice, v)}
            disabled={salvando}
          >
            <SelectTrigger
              className="h-9 w-full"
              data-testid={`testemunhas-slot-${indice}`}
            >
              <SelectValue placeholder="Selecione uma testemunha" />
            </SelectTrigger>
            <SelectContent>
              {registro.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                  Nenhuma testemunha cadastrada.
                </div>
              )}
              {registro.map((t) => (
                <SelectItem
                  key={t.id}
                  value={t.id}
                  disabled={t.cpf_pendente || outrosSelecionados.has(t.id)}
                >
                  {t.nome}
                  {t.cpf_pendente ? " — CPF pendente" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      })}
    </div>
  );
}
