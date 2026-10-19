/** FAQ from the live Julia page: what "qualificatória" means. */
export function FaqQualificatoria() {
  return (
    <section className="rounded-lg border bg-muted/30 p-4 text-sm" data-testid="perguntas-faq">
      <h2 className="mb-1 font-semibold">Como funcionam as perguntas essenciais?</h2>
      <p className="text-muted-foreground">
        A Julia pergunta somente o que ainda falta saber sobre o lead. Uma pergunta{" "}
        <strong>qualificatória</strong> é perseguida até ser respondida: o lead só é considerado qualificado quando
        todas as perguntas qualificatórias tiverem resposta. Você pode ativar até 8 perguntas, sendo até 5
        qualificatórias.
      </p>
    </section>
  );
}
