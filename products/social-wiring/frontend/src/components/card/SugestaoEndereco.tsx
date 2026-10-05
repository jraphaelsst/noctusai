/**
 * `<SugestaoEndereco/>` — the `endereco` entry of `sugestoes_extras`.
 *
 * Unlike every other reading it is a GROUP (cep, logradouro, número, …), so it
 * cannot ride `SugestaoExtraida` (string `valor`). Two cases:
 *
 *  - `substitui: false` — the record has no address; accepting fills it.
 *  - `substitui: true`  — a bill whose titular is NOT this person proposes a
 *    different address than the one on file. Asks "Substituir o endereço atual
 *    pelo deste comprovante?", shows BOTH addresses side by side plus the
 *    bill's titular and the warning. Accept = `confirmar` (replaces), refuse =
 *    `descartar`. A human decision only — the server never replaces unattended.
 *
 * Presentational: the caller owns the write (and its error toast); `saving`
 * disables both buttons while it is in flight.
 */
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { EnderecoPartes, ExtracaoSugestaoEndereco } from "@/types/cardHub";

export function formatarEndereco(e: Partial<EnderecoPartes> | null | undefined): string[] {
  if (!e) return [];
  const rua = [e.logradouro, e.numero].filter(Boolean).join(", ");
  const linha1 = [rua, e.complemento].filter(Boolean).join(" — ");
  const cidade = [e.cidade, e.uf].filter(Boolean).join("/");
  const linha2 = [e.bairro, cidade].filter(Boolean).join(" · ");
  return [linha1, linha2, e.cep ? `CEP ${e.cep}` : ""].filter(Boolean);
}

function Bloco({ titulo, linhas, tid }: { titulo: string; linhas: string[]; tid: string }) {
  return (
    <div className="rounded border bg-background p-2" data-testid={tid}>
      <p className="text-[11px] font-medium uppercase text-muted-foreground">{titulo}</p>
      {linhas.length === 0 ? (
        <p className="text-sm text-muted-foreground">—</p>
      ) : (
        linhas.map((l) => (
          <p key={l} className="text-sm">
            {l}
          </p>
        ))
      )}
    </div>
  );
}

export function SugestaoEndereco({
  sugestao,
  onResolver,
  saving,
  testIdPrefix,
}: {
  sugestao: ExtracaoSugestaoEndereco;
  onResolver: (documentoId: string, acao: "confirmar" | "descartar", itemKey: string) => void;
  saving?: boolean;
  testIdPrefix: string;
}) {
  const tid = `${testIdPrefix}-endereco-sugestao`;
  const substitui = sugestao.substitui === true;
  const fonteLabel = sugestao.fonte === "ocr" ? "leitura de imagem (OCR)" : "texto do PDF";
  return (
    <div
      className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5 text-sm"
      data-testid={tid}
    >
      <p className="font-medium" data-testid={`${tid}-pergunta`}>
        {substitui
          ? "Substituir o endereço atual pelo deste comprovante?"
          : "Preencher o endereço com o deste comprovante?"}
      </p>
      <p className="text-xs text-muted-foreground">
        Encontramos em{" "}
        <span className="font-medium text-foreground">
          {sugestao.documento_nome ?? "um documento"}
        </span>
        , por {fonteLabel}.
      </p>
      <div className={`mt-2 grid gap-2 ${substitui ? "sm:grid-cols-2" : ""}`}>
        {substitui && (
          <Bloco
            titulo="Endereço atual"
            linhas={formatarEndereco(sugestao.valor_atual)}
            tid={`${tid}-atual`}
          />
        )}
        <Bloco
          titulo={substitui ? "Deste comprovante" : "Endereço lido"}
          linhas={formatarEndereco(sugestao.valor)}
          tid={`${tid}-proposto`}
        />
      </div>
      {sugestao.titular_documento && (
        <p className="mt-1 text-xs text-muted-foreground" data-testid={`${tid}-titular`}>
          Titular do comprovante:{" "}
          <span className="font-medium text-foreground">{sugestao.titular_documento}</span>
        </p>
      )}
      {sugestao.aviso === "comprovante_titular_nao_confere" && (
        <p
          className="mt-1 flex items-center gap-1 text-xs text-amber-700"
          data-testid={`${tid}-aviso-titular`}
        >
          <AlertTriangle className="h-3 w-3 shrink-0" />O titular deste comprovante não é esta
          pessoa — confira o documento antes de substituir o endereço.
        </p>
      )}
      {sugestao.leitura_comprometida && (
        <p
          className="mt-1 flex items-center gap-1 text-xs text-destructive"
          data-testid={`${tid}-aviso-leitura-comprometida`}
        >
          <AlertTriangle className="h-3 w-3 shrink-0" />
          Legibilidade comprometida — conferência humana obrigatória.
        </p>
      )}
      <div className="mt-2 flex gap-2">
        <Button
          size="sm"
          disabled={saving}
          onClick={() => onResolver(sugestao.documento_id, "confirmar", "endereco")}
          data-testid={`${tid}-confirmar`}
        >
          {substitui ? "Substituir" : "Confirmar"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={saving}
          onClick={() => onResolver(sugestao.documento_id, "descartar", "endereco")}
          data-testid={`${tid}-descartar`}
        >
          {substitui ? "Manter o atual" : "Descartar"}
        </Button>
      </div>
    </div>
  );
}
