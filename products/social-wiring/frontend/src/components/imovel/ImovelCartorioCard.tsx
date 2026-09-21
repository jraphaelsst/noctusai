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
 *
 * 🔴 READ-ONLY TÍTULO AQUISITIVO / ÔNUS BADGES (migration 109)
 * ---------------------------------------------------------------
 * `titulo_aquisitivo_fonte` / `onus_fonte` are pointers into a matrícula
 * TRANSCRIPTION — offsets into text that lives on `/matriculas`, not on this
 * card. Rendering them as editable fields here would mean duplicating both
 * the literal quote AND the confirm/choose-other flow that already exists
 * there (`GET/PUT .../extracoes/{id}/fontes`); a badge that links to the
 * matrícula page is the whole feature, not a placeholder for a bigger one.
 */
import { useEffect, useState } from "react";
import { Landmark, Link2, Loader2, MapPin, ScrollText } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type {
  EnderecoManualPatch,
  ImovelDados,
  ImovelDadosPatch,
} from "@/hooks/useImovelDados";
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

  // ─── Manual address override (migration 147) ───────────────────────────
  // A SEPARATE save (its own PUT, its own confirmation stamp) from `onSave`
  // above — `dados_service.gravar_endereco_manual` is not part of
  // `atualizar`'s `CAMPOS_EDITAVEIS`, because every touched field logs an
  // `imovel_endereco_historico` row (see the section below).
  mirror?: { logradouro: string | null; numero: string | null; cidade: string | null; uf: string | null };
  savingEnderecoManual?: boolean;
  onSaveEnderecoManual?: (patch: EnderecoManualPatch) => void;
}

interface Draft {
  numero_matricula: string;
  numero_registro_imoveis: string;
  prefeitura_cadastro_imobiliario: string;
  captador_user_id: string;
  situacao_onus: string;
  onus_observacoes: string;
  onus_certidao_em: string;
}

/** Sentinel for "not assessed" — Radix treats `value=""` as uncontrolled, so
 *  the absence needs a real token, mapped back to null on save. */
const SEM_ONUS = "__sem_onus__";

/** Fallback vocabulary, used only if the server sends none. The list's real
 *  home is `dados_service.SITUACOES_ONUS`; duplicating it here would be two
 *  places to update, so this exists purely so the control is never empty. */
const SITUACOES_ONUS_PADRAO = [
  "livre",
  "hipoteca",
  "alienacao_fiduciaria",
  "penhora",
  "usufruto",
  "indisponibilidade",
  "outro",
] as const;

const ONUS_LABEL: Record<string, string> = {
  livre: "Livre e desembaraçado",
  hipoteca: "Hipoteca",
  alienacao_fiduciaria: "Alienação fiduciária",
  penhora: "Penhora",
  usufruto: "Usufruto",
  indisponibilidade: "Indisponibilidade",
  outro: "Outro",
};

function toDraft(dados: ImovelDados | undefined): Draft {
  return {
    numero_matricula: dados?.numero_matricula ?? "",
    numero_registro_imoveis: dados?.numero_registro_imoveis ?? "",
    prefeitura_cadastro_imobiliario: dados?.prefeitura_cadastro_imobiliario ?? "",
    captador_user_id: dados?.captador?.id ?? SEM_CAPTADOR,
    situacao_onus: dados?.situacao_onus ?? SEM_ONUS,
    onus_observacoes: dados?.onus_observacoes ?? "",
    onus_certidao_em: dados?.onus_certidao_em ?? "",
  };
}

interface EnderecoManualDraft {
  logradouro: string;
  numero: string;
  cidade: string;
  uf: string;
}

function toEnderecoManualDraft(dados: ImovelDados | undefined): EnderecoManualDraft {
  return {
    logradouro: dados?.endereco_manual_logradouro ?? "",
    numero: dados?.endereco_manual_numero ?? "",
    cidade: dados?.endereco_manual_cidade ?? "",
    uf: dados?.endereco_manual_uf ?? "",
  };
}

export default function ImovelCartorioCard({
  dados,
  membros,
  loading,
  saving,
  error,
  onSave,
  mirror,
  savingEnderecoManual,
  onSaveEnderecoManual,
}: Props) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(dados));
  const [enderecoManualDraft, setEnderecoManualDraft] = useState<EnderecoManualDraft>(() =>
    toEnderecoManualDraft(dados),
  );

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
    dados?.situacao_onus,
    dados?.onus_observacoes,
    dados?.onus_certidao_em,
  ]);

  useEffect(() => {
    setEnderecoManualDraft(toEnderecoManualDraft(dados));
  }, [
    dados?.endereco_manual_logradouro,
    dados?.endereco_manual_numero,
    dados?.endereco_manual_cidade,
    dados?.endereco_manual_uf,
  ]);

  const set = (k: keyof Draft) => (v: string) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const setEndereco = (k: keyof EnderecoManualDraft) => (v: string) =>
    setEnderecoManualDraft((d) => ({ ...d, [k]: v }));

  function submitEnderecoManual() {
    const blank = (s: string) => (s.trim() === "" ? null : s.trim());
    onSaveEnderecoManual?.({
      logradouro: blank(enderecoManualDraft.logradouro),
      numero: blank(enderecoManualDraft.numero),
      cidade: blank(enderecoManualDraft.cidade),
      uf: blank(enderecoManualDraft.uf),
    });
  }

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
      situacao_onus:
        draft.situacao_onus === SEM_ONUS ? null : draft.situacao_onus,
      onus_observacoes: blank(draft.onus_observacoes),
      onus_certidao_em: blank(draft.onus_certidao_em),
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

        {/* ─── Manual address override (migration 147) ───────────────────
            This product has no write-back to the Vista mirror the imóvel's
            address normally comes from — the contract gate reads THESE 4
            fields when set, falling back to the mirror otherwise. Every
            change is logged (`imovel_endereco_historico`): the mirror is
            external/synced data so an override needs no admin approval,
            but does need a trail. */}
        {onSaveEnderecoManual && (
          <div className="space-y-3 border-t pt-4" data-testid="imovel-endereco-manual">
            <Label className="flex items-center gap-1.5 text-sm font-semibold">
              <MapPin className="h-3.5 w-3.5" />
              Endereço (substituição manual)
            </Label>
            <p className="text-xs text-muted-foreground">
              Corrige o endereço lido do CRM/Vista — usado pelo gerador de contratos
              quando preenchido. Deixe em branco para usar o endereço do CRM.
            </p>

            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2 space-y-1">
                <Label htmlFor="endereco-manual-logradouro" className="text-xs">
                  Logradouro {mirror?.logradouro ? `(CRM: ${mirror.logradouro})` : ""}
                </Label>
                <Input
                  id="endereco-manual-logradouro"
                  value={enderecoManualDraft.logradouro}
                  onChange={(e) => setEndereco("logradouro")(e.target.value)}
                  placeholder={mirror?.logradouro ?? "Ex.: Rua Fictícia"}
                  disabled={loading || savingEnderecoManual}
                  data-testid="imovel-endereco-manual-logradouro"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="endereco-manual-numero" className="text-xs">
                  Número {mirror?.numero ? `(CRM: ${mirror.numero})` : ""}
                </Label>
                <Input
                  id="endereco-manual-numero"
                  value={enderecoManualDraft.numero}
                  onChange={(e) => setEndereco("numero")(e.target.value)}
                  placeholder={mirror?.numero ?? "Ex.: 100"}
                  disabled={loading || savingEnderecoManual}
                  data-testid="imovel-endereco-manual-numero"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="endereco-manual-uf" className="text-xs">
                  UF {mirror?.uf ? `(CRM: ${mirror.uf})` : ""}
                </Label>
                <Input
                  id="endereco-manual-uf"
                  value={enderecoManualDraft.uf}
                  onChange={(e) => setEndereco("uf")(e.target.value.toUpperCase())}
                  placeholder={mirror?.uf ?? "Ex.: SP"}
                  maxLength={2}
                  disabled={loading || savingEnderecoManual}
                  data-testid="imovel-endereco-manual-uf"
                />
              </div>
              <div className="col-span-2 space-y-1">
                <Label htmlFor="endereco-manual-cidade" className="text-xs">
                  Cidade {mirror?.cidade ? `(CRM: ${mirror.cidade})` : ""}
                </Label>
                <Input
                  id="endereco-manual-cidade"
                  value={enderecoManualDraft.cidade}
                  onChange={(e) => setEndereco("cidade")(e.target.value)}
                  placeholder={mirror?.cidade ?? "Ex.: São Paulo"}
                  disabled={loading || savingEnderecoManual}
                  data-testid="imovel-endereco-manual-cidade"
                />
              </div>
            </div>

            {dados?.endereco_manual_confirmado_por && (
              <p className="text-xs text-muted-foreground">
                Última alteração por {dados.endereco_manual_confirmado_por.nome ?? "—"}
                {dados.endereco_manual_confirmado_em
                  ? ` em ${new Date(dados.endereco_manual_confirmado_em).toLocaleString("pt-BR")}`
                  : ""}
              </p>
            )}

            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || savingEnderecoManual}
              onClick={submitEnderecoManual}
              data-testid="imovel-endereco-manual-salvar"
            >
              {savingEnderecoManual && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Salvar endereço
            </Button>
          </div>
        )}

        {/* ─── Situação de ônus (migration 099) ──────────────────────────
            What a contract's first clause asserts about this property. The
            field exists; the RULES that consume it deliberately do not yet —
            nothing here refuses anything on a stale certidão, because the
            policy is still the user's to decide. */}
        <div className="space-y-1.5 border-t pt-4">
          <Label htmlFor="imovel-onus">Situação de ônus</Label>
          <Select
            value={draft.situacao_onus}
            onValueChange={set("situacao_onus")}
            disabled={loading || saving}
          >
            <SelectTrigger id="imovel-onus" data-testid="imovel-onus">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SEM_ONUS}>Não verificado</SelectItem>
              {(dados?.situacoes_onus?.length
                ? dados.situacoes_onus
                : [...SITUACOES_ONUS_PADRAO]
              ).map((v) => (
                <SelectItem key={v} value={v}>
                  {ONUS_LABEL[v] ?? v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Conforme a Certidão de Ônus Reais.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="imovel-onus-data">Data da certidão</Label>
          <Input
            id="imovel-onus-data"
            type="date"
            value={draft.onus_certidao_em}
            onChange={(e) => set("onus_certidao_em")(e.target.value)}
            disabled={loading || saving}
            data-testid="imovel-onus-data"
          />
          {/* Spelled out because the distinction is the whole reason the
              column exists separately from the upload timestamp. */}
          <p className="text-xs text-muted-foreground">
            A data impressa na certidão — não a data do upload.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="imovel-onus-obs">Observações sobre o ônus</Label>
          <Textarea
            id="imovel-onus-obs"
            rows={2}
            value={draft.onus_observacoes}
            onChange={(e) => set("onus_observacoes")(e.target.value)}
            disabled={loading || saving}
            placeholder="Credor, valor, número do registro do gravame…"
            data-testid="imovel-onus-obs"
          />
        </div>

        {/* ─── Título aquisitivo / ônus sources (migration 109) — read-only ──
            Pointers into a matrícula transcription; the literal quote and
            the confirm/choose-other flow live on `/matriculas`. */}
        <div className="space-y-1.5 border-t pt-4">
          <Label>Fontes da matrícula</Label>
          <div className="flex flex-wrap gap-2">
            {dados?.titulo_aquisitivo_fonte ? (
              <Link
                to={`/matriculas?extracao=${dados.titulo_aquisitivo_fonte.extracao_id}`}
                data-testid="imovel-titulo-aquisitivo-badge"
              >
                <Badge variant="outline" className="gap-1 hover:bg-muted">
                  <Link2 className="h-3 w-3" />
                  Título aquisitivo
                  {dados.titulo_aquisitivo_fonte.origem === "manual" ? " · manual" : ""}
                </Badge>
              </Link>
            ) : (
              <Badge variant="outline" className="gap-1 text-muted-foreground" data-testid="imovel-titulo-aquisitivo-ausente">
                <Link2 className="h-3 w-3" />
                Título aquisitivo não confirmado
              </Badge>
            )}
            {dados?.onus_fonte ? (
              <Link
                to={`/matriculas?extracao=${dados.onus_fonte.extracao_id}`}
                data-testid="imovel-onus-fonte-badge"
              >
                <Badge variant="outline" className="gap-1 hover:bg-muted">
                  <Link2 className="h-3 w-3" />
                  Ônus ({dados.onus_fonte.atos.length})
                  {dados.onus_fonte.origem === "manual" ? " · manual" : ""}
                </Badge>
              </Link>
            ) : (
              <Badge variant="outline" className="gap-1 text-muted-foreground" data-testid="imovel-onus-fonte-ausente">
                <Link2 className="h-3 w-3" />
                Ônus não confirmado
              </Badge>
            )}
          </div>
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
