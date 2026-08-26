/**
 * `<ImovelCartorioCard/>` — the registry data we author for a property.
 *
 * Número da matrícula, número do registro de imóveis, prefeitura do cadastro
 * imobiliário, and the captador (the agent who brought the property in — a
 * platform USER, because migration 076's 5% captação slice is attributed to
 * them and a free-text name cannot be aggregated).
 *
 * 🔴 WHY IT SHOWS WHERE THE MATRÍCULA NUMBER CAME FROM
 * -----------------------------------------------------
 * A number read off an uploaded PDF and a number a person typed are not
 * equally trustworthy, and the difference is invisible once both are just
 * text in a box. The provenance line is what lets someone answer "did anyone
 * actually check this?" without re-opening the certidão — and it is the same
 * reason the backend stores `numero_matricula_origem` at all.
 */
import { useEffect, useState } from "react";
import { Landmark, Loader2, ScrollText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { ImovelDados, ImovelDadosPatch } from "@/hooks/useImovelDados";
import { origemLabel } from "@/hooks/useImovelDados";
import type { Member } from "@/hooks/useTeam";

/** Sentinel for "no captador". Radix `SelectItem` refuses an empty string. */
const SEM_CAPTADOR = "__sem_captador__";

interface Props {
  dados: ImovelDados | undefined;
  membros: Member[];
  loading: boolean;
  saving: boolean;
  error?: string | null;
  onSave: (patch: ImovelDadosPatch) => void;
}

interface Draft {
  numero_matricula: string;
  numero_registro_imoveis: string;
  prefeitura_cadastro_imobiliario: string;
  captador_user_id: string;
}

function toDraft(dados: ImovelDados | undefined): Draft {
  return {
    numero_matricula: dados?.numero_matricula ?? "",
    numero_registro_imoveis: dados?.numero_registro_imoveis ?? "",
    prefeitura_cadastro_imobiliario: dados?.prefeitura_cadastro_imobiliario ?? "",
    captador_user_id: dados?.captador?.id ?? SEM_CAPTADOR,
  };
}

export default function ImovelCartorioCard({
  dados,
  membros,
  loading,
  saving,
  error,
  onSave,
}: Props) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(dados));

  // Re-seed when the server view changes — including when a background
  // matrícula read fills `numero_matricula` while this card is on screen.
  // Keyed on the values themselves rather than on the object identity, so a
  // refetch that changed nothing does not stomp a field mid-typing.
  useEffect(() => {
    setDraft(toDraft(dados));
  }, [
    dados?.numero_matricula,
    dados?.numero_registro_imoveis,
    dados?.prefeitura_cadastro_imobiliario,
    dados?.captador?.id,
  ]);

  const set = (k: keyof Draft) => (v: string) =>
    setDraft((d) => ({ ...d, [k]: v }));

  function submit() {
    // 🔴 Empty string → `null`, never `""`. The backend treats absence as
    // "leave alone" and null as "clear"; sending "" would store a blank
    // string that reads as present everywhere downstream.
    const blank = (s: string) => (s.trim() === "" ? null : s.trim());
    onSave({
      numero_matricula: blank(draft.numero_matricula),
      numero_registro_imoveis: blank(draft.numero_registro_imoveis),
      prefeitura_cadastro_imobiliario: blank(draft.prefeitura_cadastro_imobiliario),
      captador_user_id:
        draft.captador_user_id === SEM_CAPTADOR ? null : draft.captador_user_id,
    });
  }

  const origem = origemLabel(dados?.numero_matricula_origem ?? null);
  const lidoAutomaticamente = dados?.numero_matricula_origem === "matricula";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Landmark className="h-4 w-4" />
          Cartório e registro
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="numero-matricula">Número da matrícula</Label>
          <Input
            id="numero-matricula"
            value={draft.numero_matricula}
            onChange={(e) => set("numero_matricula")(e.target.value)}
            placeholder="Ex.: 12345"
            disabled={loading}
          />
          {origem && (
            // A <div>, not a <p>: `Badge` renders a <div>.
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <ScrollText className="h-3 w-3" />
              {origem}
              {lidoAutomaticamente && !dados?.numero_matricula_confirmado_em && (
                // Said plainly: a machine read it, and nobody has agreed with
                // it yet. Saving the form is what confirms it.
                <Badge variant="outline" className="ml-1 text-[10px]">
                  não conferido
                </Badge>
              )}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="numero-registro">Número do registro de imóveis</Label>
          <Input
            id="numero-registro"
            value={draft.numero_registro_imoveis}
            onChange={(e) => set("numero_registro_imoveis")(e.target.value)}
            placeholder="Ex.: 5º RI"
            disabled={loading}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="prefeitura">Prefeitura do cadastro imobiliário</Label>
          <Input
            id="prefeitura"
            value={draft.prefeitura_cadastro_imobiliario}
            onChange={(e) =>
              set("prefeitura_cadastro_imobiliario")(e.target.value)
            }
            placeholder="Ex.: São Paulo"
            disabled={loading}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="captador">Captador</Label>
          <Select
            value={draft.captador_user_id}
            onValueChange={set("captador_user_id")}
            disabled={loading}
          >
            <SelectTrigger id="captador">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SEM_CAPTADOR}>Sem captador</SelectItem>
              {membros.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.nome || m.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Recebe 5% da comissão nas negociações deste imóvel.
          </p>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button onClick={submit} disabled={loading || saving} className="w-full">
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Salvar
        </Button>
      </CardContent>
    </Card>
  );
}
