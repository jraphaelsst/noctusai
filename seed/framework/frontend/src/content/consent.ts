/**
 * Canonical consent-document content for the NoctusAI platform.
 *
 * Single source of truth for the PUBLIC (unauthenticated) legal pages mounted
 * by `createProductApp` at `/consent`, `/consent/privacy-policy` and
 * `/consent/terms-of-use` — inherited by EVERY product (seed-first; no
 * per-product code). These are platform-wide documents: one controller, one
 * policy set for the whole fleet. They double as the canonical URLs submitted
 * for Google OAuth verification and Meta App Review (which require a publicly
 * reachable privacy policy + terms, plus the Google "Limited Use" and Meta
 * Platform disclosures — sections 9 and 10 of the privacy policy below).
 *
 * Structured (ABNT NBR 6024 progressive numbering) so the renderer is dumb and
 * the prose lives in one auditable place. Content is pt-BR (LGPD, Lei nº
 * 13.709/2018). Update `META.version` + `META.lastUpdated` on any change.
 */

export const CONSENT_META = {
  platform: "NoctusAI",
  /** Controlador (LGPD) — pessoa física, conforme ratificado pelo titular do negócio. */
  controllerName: "João Raphael",
  controllerKind: "Pessoa física, na qualidade de controlador dos dados (LGPD, art. 5º, VI)",
  controllerLocation: "Cotia/SP, Brasil",
  /** Encarregado pelo Tratamento de Dados Pessoais (DPO) — LGPD art. 41. */
  dpoName: "João Raphael",
  email: "joaoraphaelsst@gmail.com",
  phone: "+55 (11) 97469-3365",
  canonicalBase: "https://noctusai.com/consent",
  lastUpdated: "01/06/2026",
  version: "1.0",
} as const;

/** A content block: a paragraph (`p`) or an unordered list (`ul`). */
export type DocBlock = { p: string } | { ul: string[] };

/** One progressively-numbered section (ABNT NBR 6024). */
export interface DocSection {
  /** Progressive number, e.g. "1", "9". */
  n: string;
  title: string;
  blocks: DocBlock[];
}

export interface ConsentDoc {
  slug: "privacy-policy" | "terms-of-use";
  title: string;
  /** Short, human label for nav/cards. */
  shortLabel: string;
  intro: string;
  sections: DocSection[];
}

// ───────────────────────────────────────────────────────────────────────────
// Política de Privacidade
// ───────────────────────────────────────────────────────────────────────────

export const PRIVACY_POLICY: ConsentDoc = {
  slug: "privacy-policy",
  title: "Política de Privacidade",
  shortLabel: "Política de Privacidade",
  intro:
    "Esta Política de Privacidade descreve como a plataforma NoctusAI coleta, " +
    "utiliza, compartilha e protege dados pessoais, em conformidade com a Lei " +
    "Geral de Proteção de Dados Pessoais (Lei nº 13.709/2018 — “LGPD”) e demais " +
    "normas aplicáveis. Ela se aplica a todos os produtos e módulos da plataforma " +
    "NoctusAI e a quaisquer integrações por nós oferecidas.",
  sections: [
    {
      n: "1",
      title: "Quem somos e a quem esta Política se aplica",
      blocks: [
        {
          p:
            "A plataforma NoctusAI (“NoctusAI”, “plataforma”, “nós”) é um conjunto " +
            "de produtos e módulos que oferecem automação, mensageria, integrações e " +
            "recursos assistidos por inteligência artificial. O controlador dos dados " +
            "pessoais tratados por meio da plataforma é João Raphael (pessoa física), " +
            "localizado em Cotia/SP, Brasil.",
        },
        {
          p:
            "Esta Política aplica-se a usuários, titulares de contas e demais pessoas " +
            "cujos dados sejam tratados quando você acessa, configura ou utiliza " +
            "qualquer produto da plataforma NoctusAI, inclusive os fluxos de conexão " +
            "com serviços de terceiros (por exemplo, Google e Meta/WhatsApp).",
        },
      ],
    },
    {
      n: "2",
      title: "Definições",
      blocks: [
        {
          ul: [
            "Dado pessoal: informação relacionada a pessoa natural identificada ou identificável.",
            "Titular: a pessoa natural a quem se referem os dados pessoais.",
            "Tratamento: toda operação realizada com dados pessoais (coleta, uso, armazenamento, compartilhamento, eliminação etc.).",
            "Controlador: quem decide sobre o tratamento dos dados — aqui, João Raphael.",
            "Operador (sub-processador): terceiro que trata dados em nome do controlador (vide seção 8).",
            "Encarregado (DPO): pessoa indicada para atuar como canal entre controlador, titulares e a autoridade (ANPD).",
          ],
        },
      ],
    },
    {
      n: "3",
      title: "Dados que tratamos",
      blocks: [
        { p: "A depender do produto e das integrações que você ativa, podemos tratar:" },
        {
          ul: [
            "Dados cadastrais e de conta: nome, e-mail, telefone, organização e credenciais de autenticação.",
            "Dados de autenticação e integração: tokens de acesso (OAuth) e identificadores de contas que você conecta voluntariamente (por exemplo, canais do YouTube, contas Google, WhatsApp/Meta), armazenados de forma criptografada.",
            "Conteúdo de mensagens e mídia: texto, áudio, imagem e vídeo trocados em fluxos de mensageria e automação (por exemplo, via WhatsApp Business Platform).",
            "Conteúdo criado por você: configurações, fluxos, publicações, documentos e demais conteúdos inseridos na plataforma.",
            "Dados de uso e técnicos: endereço IP, identificadores de dispositivo/navegador, registros de acesso (logs), data e hora de eventos e dados de diagnóstico.",
          ],
        },
        {
          p:
            "Tratamos apenas os dados necessários às finalidades descritas nesta " +
            "Política, observando o princípio da minimização.",
        },
      ],
    },
    {
      n: "4",
      title: "Como coletamos os dados",
      blocks: [
        {
          ul: [
            "Diretamente de você, ao criar conta, configurar produtos ou enviar conteúdo.",
            "Automaticamente, por meio de registros técnicos gerados durante o uso da plataforma.",
            "De serviços de terceiros que você autoriza a conectar (por exemplo, ao concluir um fluxo de consentimento OAuth do Google ou da Meta), estritamente no escopo por você autorizado.",
          ],
        },
      ],
    },
    {
      n: "5",
      title: "Finalidades do tratamento",
      blocks: [
        {
          ul: [
            "Prestar, operar e manter os produtos e funcionalidades da plataforma.",
            "Executar fluxos de automação e mensageria solicitados por você.",
            "Operar integrações com serviços de terceiros que você conecta.",
            "Disponibilizar recursos assistidos por inteligência artificial (vide seção 7).",
            "Garantir segurança, prevenir fraudes e abusos e assegurar a estabilidade do serviço.",
            "Cumprir obrigações legais e regulatórias e exercer direitos em processos.",
            "Comunicar-se com você sobre o serviço (avisos transacionais e de suporte).",
          ],
        },
      ],
    },
    {
      n: "6",
      title: "Bases legais (LGPD)",
      blocks: [
        { p: "Tratamos dados pessoais com fundamento nas seguintes bases legais (LGPD, art. 7º e art. 11):" },
        {
          ul: [
            "Execução de contrato ou de procedimentos preliminares, para prestar o serviço solicitado.",
            "Consentimento, para finalidades específicas — em especial recursos de IA e comunicações opcionais —, que pode ser revogado a qualquer tempo.",
            "Legítimo interesse, para segurança, prevenção a fraudes e melhoria do serviço, sempre ponderado com seus direitos e liberdades.",
            "Cumprimento de obrigação legal ou regulatória.",
          ],
        },
      ],
    },
    {
      n: "7",
      title: "Recursos de inteligência artificial",
      blocks: [
        {
          p:
            "Alguns recursos utilizam modelos de inteligência artificial (próprios ou " +
            "de provedores terceiros) para gerar respostas, resumos, classificações e " +
            "automações. O uso desses recursos é controlado por consentimentos " +
            "granulares, geríveis a qualquer momento na área de Configurações de IA da " +
            "plataforma (rota “/settings/ai”). A revogação vale a partir do próximo uso " +
            "e não afeta resultados já gerados.",
        },
        {
          p:
            "Não utilizamos o conteúdo de suas mensagens privadas para treinar modelos " +
            "de terceiros sem base legal adequada, e contratamos provedores que oferecem " +
            "compromissos de confidencialidade e não-treinamento quando aplicável.",
        },
      ],
    },
    {
      n: "8",
      title: "Compartilhamento e operadores (sub-processadores)",
      blocks: [
        {
          p:
            "Podemos compartilhar dados com operadores que atuam em nosso nome, sob " +
            "obrigações contratuais de confidencialidade e segurança, exclusivamente " +
            "para viabilizar o serviço. As principais categorias são:",
        },
        {
          ul: [
            "Meta Platforms, Inc. — WhatsApp Business Platform, Instagram e Facebook Graph API (mensageria e publicação).",
            "Google LLC — autenticação OAuth e APIs do Google (por exemplo, YouTube, Agenda/Calendar, Drive, Planilhas, Gmail, Maps) e modelos de IA do Google.",
            "OpenAI — modelos de linguagem e geração de embeddings.",
            "Supabase — banco de dados, autenticação e hospedagem.",
            "n8n — orquestração de fluxos de automação.",
            "Cloudflare — rede de distribuição de conteúdo, túnel de acesso e proteção.",
            "Provedor de infraestrutura em nuvem (hospedagem dos servidores da plataforma).",
          ],
        },
        {
          p:
            "Também poderemos compartilhar dados para cumprir obrigação legal, ordem de " +
            "autoridade competente ou para defesa de direitos. Não vendemos dados pessoais.",
        },
      ],
    },
    {
      n: "9",
      title: "Uso de dados obtidos via APIs do Google (Limited Use)",
      blocks: [
        {
          p:
            "O uso, pela NoctusAI, de informações recebidas de APIs do Google adere à " +
            "Google API Services User Data Policy, incluindo seus requisitos de Uso " +
            "Limitado (“Limited Use”). Especificamente:",
        },
        {
          ul: [
            "Utilizamos os dados das APIs do Google apenas para fornecer e aprimorar funcionalidades visíveis ao usuário que solicitou a conexão.",
            "Não transferimos esses dados a terceiros, exceto quando necessário para prestar ou melhorar tais funcionalidades, por exigência legal, ou como parte de fusão/aquisição com o devido consentimento.",
            "Não utilizamos esses dados para fins de publicidade, nem para treinar modelos de IA generalizados ou personalizados.",
            "Não permitimos que pessoas leiam esses dados, salvo com seu consentimento expresso para finalidade específica, por exigência legal/segurança, ou de forma agregada e anonimizada para operação interna.",
          ],
        },
      ],
    },
    {
      n: "10",
      title: "Plataformas Meta (WhatsApp, Instagram e Facebook)",
      blocks: [
        {
          p:
            "Quando você conecta uma conta Meta (por exemplo, WhatsApp Business " +
            "Platform), tratamos os dados estritamente para operar os fluxos de " +
            "mensageria e publicação que você configura, em conformidade com os Termos " +
            "da Plataforma da Meta e suas políticas para desenvolvedores. Não utilizamos " +
            "esses dados para finalidades incompatíveis com a prestação do serviço.",
        },
      ],
    },
    {
      n: "11",
      title: "Transferências internacionais de dados",
      blocks: [
        {
          p:
            "Alguns operadores (por exemplo, Google, OpenAI, Meta e Cloudflare) podem " +
            "tratar dados fora do Brasil. Nesses casos, adotamos salvaguardas previstas " +
            "na LGPD, como cláusulas contratuais adequadas e a observância de padrões " +
            "reconhecidos de segurança e proteção de dados.",
        },
      ],
    },
    {
      n: "12",
      title: "Retenção e eliminação",
      blocks: [
        {
          p:
            "Mantemos os dados pelo tempo necessário às finalidades desta Política e ao " +
            "cumprimento de obrigações legais. Tokens de integração são mantidos até que " +
            "você desconecte a respectiva conta ou revogue o acesso. Encerrado o " +
            "tratamento, os dados são eliminados ou anonimizados, ressalvadas as " +
            "hipóteses de guarda obrigatória previstas em lei.",
        },
      ],
    },
    {
      n: "13",
      title: "Segurança da informação",
      blocks: [
        {
          p:
            "Adotamos medidas técnicas e organizacionais para proteger os dados, " +
            "incluindo criptografia em trânsito (TLS) e criptografia de credenciais " +
            "sensíveis em repouso, controle de acesso, isolamento por organização " +
            "(políticas de segurança em nível de linha) e registro de eventos. Nenhum " +
            "sistema é totalmente imune a incidentes; em caso de incidente relevante, " +
            "atuaremos conforme a LGPD.",
        },
      ],
    },
    {
      n: "14",
      title: "Direitos do titular",
      blocks: [
        { p: "Nos termos da LGPD (art. 18), você pode, a qualquer tempo, solicitar:" },
        {
          ul: [
            "Confirmação da existência de tratamento e acesso aos dados.",
            "Correção de dados incompletos, inexatos ou desatualizados.",
            "Anonimização, bloqueio ou eliminação de dados desnecessários ou tratados em desconformidade.",
            "Portabilidade dos dados a outro fornecedor, observados os segredos comercial e industrial.",
            "Informação sobre o compartilhamento de seus dados.",
            "Revogação do consentimento e informação sobre as consequências da negativa.",
          ],
        },
        {
          p:
            "Para exercer seus direitos, contate o Encarregado pelos canais da seção 17. " +
            "Você também pode peticionar à Autoridade Nacional de Proteção de Dados (ANPD).",
        },
      ],
    },
    {
      n: "15",
      title: "Cookies e tecnologias similares",
      blocks: [
        {
          p:
            "Utilizamos cookies e armazenamento local estritamente necessários para " +
            "autenticação, segurança e funcionamento da plataforma. Não empregamos " +
            "cookies de publicidade comportamental.",
        },
      ],
    },
    {
      n: "16",
      title: "Menores de idade",
      blocks: [
        {
          p:
            "A plataforma não se destina a menores de 18 anos. Não coletamos " +
            "intencionalmente dados de menores; identificado tratamento indevido, os " +
            "dados serão eliminados.",
        },
      ],
    },
    {
      n: "17",
      title: "Encarregado (DPO) e contato",
      blocks: [
        {
          p:
            "Encarregado pelo Tratamento de Dados Pessoais: João Raphael. Para dúvidas, " +
            "solicitações de titular ou assuntos de privacidade, utilize os canais de " +
            "contato indicados ao final desta página.",
        },
      ],
    },
    {
      n: "18",
      title: "Atualizações desta Política",
      blocks: [
        {
          p:
            "Esta Política pode ser atualizada para refletir mudanças operacionais, " +
            "legais ou regulatórias. A versão vigente é sempre publicada nesta URL, com " +
            "indicação de versão e data da última atualização. Recomenda-se a revisão " +
            "periódica.",
        },
      ],
    },
  ],
};

// ───────────────────────────────────────────────────────────────────────────
// Termos de Uso
// ───────────────────────────────────────────────────────────────────────────

export const TERMS_OF_USE: ConsentDoc = {
  slug: "terms-of-use",
  title: "Termos de Uso",
  shortLabel: "Termos de Uso",
  intro:
    "Estes Termos de Uso regem o acesso e a utilização da plataforma NoctusAI e " +
    "de seus produtos. Ao acessar ou utilizar a plataforma, você concorda com " +
    "estes Termos. Caso não concorde, não utilize o serviço.",
  sections: [
    {
      n: "1",
      title: "Objeto e aceitação",
      blocks: [
        {
          p:
            "A plataforma NoctusAI fornece produtos de automação, mensageria, " +
            "integrações e recursos assistidos por inteligência artificial. Estes Termos " +
            "constituem um acordo entre você e o titular da plataforma (João Raphael) e " +
            "passam a vigorar a partir do primeiro acesso ou uso.",
        },
      ],
    },
    {
      n: "2",
      title: "Definições",
      blocks: [
        {
          ul: [
            "Plataforma/Serviço: os produtos e funcionalidades oferecidos pela NoctusAI.",
            "Usuário: pessoa que acessa ou utiliza a plataforma.",
            "Conteúdo do usuário: dados, configurações e materiais que você insere ou gera na plataforma.",
            "Integrações de terceiros: serviços externos (por exemplo, Google e Meta/WhatsApp) que você conecta voluntariamente.",
          ],
        },
      ],
    },
    {
      n: "3",
      title: "Elegibilidade e cadastro",
      blocks: [
        {
          p:
            "O uso é restrito a maiores de 18 anos com capacidade civil. Você é " +
            "responsável pela veracidade dos dados de cadastro e pela guarda de suas " +
            "credenciais. Podemos recusar, suspender ou encerrar contas em caso de " +
            "fraude, abuso ou violação destes Termos.",
        },
      ],
    },
    {
      n: "4",
      title: "Acesso e licença de uso",
      blocks: [
        {
          p:
            "Concedemos a você uma licença pessoal, limitada, não exclusiva e " +
            "intransferível para acessar e utilizar a plataforma conforme estes Termos. " +
            "Você não adquire qualquer direito sobre o software, marcas ou conteúdos da " +
            "plataforma além do uso autorizado.",
        },
      ],
    },
    {
      n: "5",
      title: "Regras de uso aceitável",
      blocks: [
        { p: "Ao utilizar a plataforma, você concorda em não:" },
        {
          ul: [
            "Praticar atos ilícitos ou violar direitos de terceiros.",
            "Enviar conteúdo ilegal, ofensivo, enganoso, fraudulento ou spam.",
            "Tentar burlar mecanismos de segurança, acessar áreas não autorizadas ou interferir na operação do serviço.",
            "Utilizar a plataforma para violar termos de plataformas de terceiros que você conecta (por exemplo, políticas do Google ou da Meta).",
            "Realizar engenharia reversa ou uso automatizado abusivo não autorizado.",
          ],
        },
      ],
    },
    {
      n: "6",
      title: "Integrações de terceiros e autorizações",
      blocks: [
        {
          p:
            "A plataforma permite conectar contas e serviços de terceiros mediante sua " +
            "autorização expressa (por exemplo, via OAuth). Ao conectar uma integração, " +
            "você declara possuir os direitos necessários e concorda em cumprir os termos " +
            "e políticas do respectivo provedor. As integrações de terceiros não são " +
            "controladas por nós e estão sujeitas a suas próprias condições e " +
            "disponibilidade.",
        },
      ],
    },
    {
      n: "7",
      title: "Conteúdo do usuário e propriedade intelectual",
      blocks: [
        {
          p:
            "Você mantém a titularidade do conteúdo que insere na plataforma e nos " +
            "concede licença limitada para tratá-lo na medida necessária à prestação do " +
            "serviço. O software, código, fluxos, layouts e marcas da NoctusAI " +
            "pertencem ao seu titular ou a seus licenciadores e são protegidos por lei.",
        },
      ],
    },
    {
      n: "8",
      title: "Recursos de inteligência artificial",
      blocks: [
        {
          p:
            "Recursos assistidos por IA podem produzir resultados imprecisos ou " +
            "incompletos. Eles são fornecidos como apoio e não substituem julgamento " +
            "humano; recomenda-se revisão antes de qualquer decisão relevante. O uso " +
            "desses recursos observa os consentimentos granulares descritos na Política " +
            "de Privacidade.",
        },
      ],
    },
    {
      n: "9",
      title: "Privacidade e proteção de dados",
      blocks: [
        {
          p:
            "O tratamento de dados pessoais é regido pela Política de Privacidade da " +
            "NoctusAI, parte integrante destes Termos e disponível na mesma seção de " +
            "documentos (/consent/privacy-policy).",
        },
      ],
    },
    {
      n: "10",
      title: "Disponibilidade, manutenção e alterações do serviço",
      blocks: [
        {
          p:
            "A plataforma é fornecida “no estado em que se encontra” (as is) e pode " +
            "passar por manutenções, atualizações, suspensões ou descontinuação de " +
            "funcionalidades. Empregaremos esforços razoáveis para comunicar mudanças " +
            "relevantes, mas não garantimos disponibilidade ininterrupta.",
        },
      ],
    },
    {
      n: "11",
      title: "Limitação de responsabilidade",
      blocks: [
        {
          p:
            "Na máxima extensão permitida em lei, não nos responsabilizamos por danos " +
            "indiretos, lucros cessantes ou perda de dados decorrentes do uso ou da " +
            "impossibilidade de uso da plataforma, ou de falhas de integrações de " +
            "terceiros. Ficam resguardados os direitos previstos no Código de Defesa do " +
            "Consumidor, quando aplicável.",
        },
      ],
    },
    {
      n: "12",
      title: "Suspensão e rescisão",
      blocks: [
        {
          p:
            "Você pode encerrar o uso a qualquer momento. Podemos suspender ou encerrar " +
            "o acesso em caso de violação destes Termos, exigência legal ou risco à " +
            "segurança. Encerrado o uso, aplicam-se as regras de retenção e eliminação " +
            "previstas na Política de Privacidade.",
        },
      ],
    },
    {
      n: "13",
      title: "Alterações destes Termos",
      blocks: [
        {
          p:
            "Estes Termos podem ser atualizados. A versão vigente é sempre publicada " +
            "nesta URL, com indicação de versão e data. O uso continuado após a " +
            "publicação de alterações implica concordância com a versão atualizada.",
        },
      ],
    },
    {
      n: "14",
      title: "Legislação aplicável e foro",
      blocks: [
        {
          p:
            "Estes Termos são regidos pelas leis da República Federativa do Brasil. " +
            "Fica eleito o foro do domicílio do usuário para dirimir controvérsias, nos " +
            "termos da legislação consumerista aplicável.",
        },
      ],
    },
    {
      n: "15",
      title: "Contato",
      blocks: [
        {
          p:
            "Dúvidas sobre estes Termos podem ser encaminhadas pelos canais de contato " +
            "indicados ao final desta página.",
        },
      ],
    },
  ],
};

export const CONSENT_DOCS: ConsentDoc[] = [PRIVACY_POLICY, TERMS_OF_USE];
