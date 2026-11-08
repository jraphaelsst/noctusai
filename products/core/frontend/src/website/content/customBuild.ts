/** The four custom-build steps — one copy for the Home section and the /solucoes page. */
export function customBuildSteps(en: boolean): { title: string; description: string }[] {
  return [
    { title: en ? "Diagnosis" : "Diagnóstico", description: en ? "We understand the process, the people and the data you already have." : "Entendemos o processo, as pessoas envolvidas e os dados que você já tem." },
    { title: en ? "Prototype" : "Protótipo", description: en ? "A clickable version with your data, to validate before building." : "Uma versão clicável com os seus dados, para você validar antes de construir." },
    { title: en ? "Production" : "Produção", description: en ? "It goes live on the same base as our products: one login, data separated per organisation." : "Entra no ar na mesma base dos nossos produtos: um login e dados separados por organização." },
    { title: en ? "Evolution" : "Evolução", description: en ? "We follow the usage with you and adjust what is needed." : "Acompanhamos o uso com você e ajustamos o que precisar." },
  ];
}
