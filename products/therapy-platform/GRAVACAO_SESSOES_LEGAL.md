# Gravacao de Sessoes Terapeuticas — Analise Legal Brasil

## Contexto

Durante o desenvolvimento da plataforma de terapia, surgiu a duvida se a legislacao brasileira **proibe a gravacao de sessoes de psicoterapia**. Essa questao e critica porque a plataforma possui um pipeline de IA que transcreve sessoes, gera resumos clinicos (Track 1 para paciente, Track 2 para terapeuta) e alimenta analises longitudinais. Se a gravacao fosse proibida, toda essa arquitetura precisaria ser removida ou repensada.

A investigacao revelou que a gravacao **nao e proibida**, mas e **fortemente regulamentada** pelo Conselho Federal de Psicologia (CFP).

---

## O Que Diz a Lei

### Resolucao CFP n. 13/2022 — Artigo 11

A norma principal e a **Resolucao CFP n. 13, de 15 de junho de 2022**, que dispoe sobre diretrizes e deveres para o exercicio da psicoterapia. O **Artigo 11** trata especificamente da gravacao:

> A gravacao de sessoes de psicoterapia, por audio ou video, deve ser consentida, de forma **livre, previa, informada e por escrito**, pela pessoa a ser atendida, devendo:
>
> I — ser justificada pela finalidade ou metodo de trabalho utilizado;
>
> II — assegurar o sigilo, conforme as normas que regulamentam o exercicio da Psicologia.

#### Paragrafos adicionais:

- **§ 1o** — A gravacao de atendimento de criancas, adolescentes ou pessoas interditadas esta condicionada ao consentimento dos responsaveis, livre, previo, informado e por escrito, e ao posterior assentimento da pessoa a ser atendida.

- **§ 2o** — E proibido utilizar registros de audio e imagem das pessoas atendidas de forma estranha as finalidades e ao metodo previamente estabelecidos.

- **§ 3o** — A gravacao de sessoes compreende o registro documental, conforme Resolucao CFP n. 1, de 30 de marco de 2009.

### Resolucao CFP n. 1/2009

Gravacoes de sessoes sao classificadas como **registro documental** e devem ser mantidas por no minimo **5 anos**, podendo ser estendido em casos previstos por lei ou determinacao judicial.

### Resolucao CFP n. 9/2024

A resolucao mais recente sobre servicos psicologicos via **Tecnologias Digitais da Informacao e Comunicacao (TDICs)** reitera que o psicologo deve especificar quais recursos tecnologicos sao utilizados para garantir o sigilo das informacoes e informar o paciente sobre isso.

---

## Resumo das Condicoes para Gravacao

| Requisito | Descricao |
|---|---|
| **Consentimento escrito** | Livre, previo, informado e por escrito — antes de qualquer gravacao |
| **Finalidade justificada** | Deve estar vinculada ao metodo terapeutico ou objetivo clinico especifico |
| **Sigilo garantido** | Armazenamento seguro conforme normas do CFP |
| **Uso restrito** | Gravacoes nao podem ser usadas para finalidade diferente da acordada |
| **Menores/interditados** | Consentimento do responsavel + assentimento do paciente |
| **Retencao minima** | 5 anos conforme Resolucao CFP n. 1/2009 |

---

## Impacto na Plataforma

### O que ja temos e pode ser mantido

O pipeline de IA (`ai_pipeline.py` → transcricao → resumos clinicos → analise longitudinal) esta **arquiteturalmente correto** e pode ser mantido. A gravacao e a transcricao de sessoes sao permitidas desde que as condicoes acima sejam cumpridas.

### O que precisamos adicionar

1. **Fluxo de consentimento explicito** — consentimento por sessao antes de iniciar a gravacao (nao um checkbox unico nos Termos de Uso)
2. **Declaracao de finalidade** — texto claro informando que a gravacao e para geracao de resumos clinicos via IA (justificativa pelo metodo terapeutico)
3. **Gravacao desativada por padrao** — a gravacao deve ser opt-in, nunca automatica
4. **Trilha de auditoria do consentimento** — registros com timestamp de quando o consentimento foi dado ou revogado
5. **Acesso restrito** — transcricoes e gravacoes acessiveis apenas ao terapeuta responsavel pelo atendimento (nao administradores de clinica ou da plataforma)
6. **Capacidade de exclusao** — paciente pode revogar consentimento e solicitar exclusao das gravacoes (alinhado tambem com a LGPD)

### Vantagem competitiva

A maioria das plataformas ou ignora a gravacao por completo, ou nao trata o consentimento adequadamente. Implementar um framework de consentimento robusto e um **diferencial de confianca** perante terapeutas e pacientes.

---

## Fontes

- [E permitido gravar as sessoes de atendimento? — CFP (FAQ Oficial)](https://site.cfp.org.br/faq/e-permitido-gravar-as-sessoes-de-atendimento/)
- [Resolucao CFP n. 13/2022 — Texto Completo](https://atosoficiais.com.br/cfp/resolucao-do-exercicio-profissional-n-13-2022-dispoe-sobre-diretrizes-e-deveres-para-o-exercicio-da-psicoterapia-por-psicologa-e-por-psicologo)
- [CRP-MT — Orientacao Tecnica: Gravacao de Sessoes e Uso de Cameras](https://crpmt.org.br/orientacao-tecnica/gravacao-de-sessoes-e-o-uso-de-cameras)
- [CRP-PR — Gravacao de Sessoes](https://crppr.org.br/orientacoes/gravacao-de-sessoes/)
- [Resolucao CFP n. 9/2024 — Servicos via TDICs](https://www.legisweb.com.br/legislacao/?id=462577)
- [CRP-03 — Nota Tecnica sobre Gravacoes em Atendimentos Psicologicos](https://www.crp03.org.br/nota-tecnica-sobre-uso-de-dispositivos-tecnologicos-para-fins-de-gravacoes-de-video-e-ou-audio-em-locais-de-atendimentos-psicologicos/)
- [Resolucao CFP n. 1/2009 — Registro Documental](https://site.cfp.org.br/wp-content/uploads/2009/04/resolucao2009_01.pdf)

---

*Pesquisa realizada em abril de 2026 durante o desenvolvimento da plataforma NoctusAI Therapy.*
