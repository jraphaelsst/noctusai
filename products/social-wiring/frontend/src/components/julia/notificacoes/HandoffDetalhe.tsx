/**
 * Body of a `handoff` notification: the lead PROFILE, the atendimento SUMMARY and the MASKED identity that agents
 * recorded when Julia handed the lead to a person (julia-v2 0.4). The server writes it as lines
 * (`Rótulo: valor`); we split them into labelled blocks. Identity is masked server-side AND again here — a raw
 * CPF/RG is never rendered.
 */
import { desescaparEntidades, mascararIdentidade } from "@/lib/mascaraIdentidade";

const SECOES: { prefixo: string; titulo: string; testId: string }[] = [
  { prefixo: "Resumo do atendimento:", titulo: "Resumo do atendimento", testId: "handoff-resumo" },
  { prefixo: "Perfil:", titulo: "Perfil do lead", testId: "handoff-perfil" },
  { prefixo: "Identificação (mascarada):", titulo: "Identificação (mascarada)", testId: "handoff-identificacao" },
  { prefixo: "Identificação:", titulo: "Identificação", testId: "handoff-identificacao" },
  { prefixo: "Em aberto:", titulo: "Em aberto", testId: "handoff-aberto" },
  { prefixo: "Combinado com o lead:", titulo: "Combinado com o lead", testId: "handoff-combinado" },
];

export function HandoffDetalhe({ mensagem }: { mensagem: string }) {
  const linhas = mensagem.split("\n").map((l) => l.trim()).filter(Boolean);
  const [intro, ...resto] = linhas;
  const blocos = resto.map((l) => {
    const s = SECOES.find((x) => l.startsWith(x.prefixo));
    return s
      ? { ...s, texto: l.slice(s.prefixo.length).trim() }
      : { prefixo: "", titulo: "", testId: "handoff-outro", texto: l };
  });
  return (
    <div className="space-y-2" data-testid="handoff-detalhe">
      {intro && <p>{mascararIdentidade(desescaparEntidades(intro))}</p>}
      {blocos.map((b, i) => (
        <section key={i} data-testid={b.testId}>
          {b.titulo && <h4 className="text-xs font-semibold uppercase text-muted-foreground">{b.titulo}</h4>}
          {b.testId === "handoff-perfil" || b.testId === "handoff-identificacao" ? (
            <ul className="list-inside list-disc text-sm">
              {b.texto.split(";").map((it) => it.trim()).filter(Boolean).map((it, j) => (
                <li key={j}>{mascararIdentidade(desescaparEntidades(it))}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm">{mascararIdentidade(desescaparEntidades(b.texto))}</p>
          )}
        </section>
      ))}
    </div>
  );
}
