/**
 * `/coleta` data — one entry per município in and around the project's territory.
 *
 * Everything here comes from public sources researched on 2026-09-29; each
 * município lists them in `fontes`, with the DOCUMENT's own date. The
 * schedule rows (`dados/<slug>.ts`) are transcriptions of the prefeitura's
 * published calendar; the rest (ecopontos, contatos, avisos) is from the
 * prefeitura's pages and, where marked `oficial: false`, the local press.
 *
 * Adding a município: transcribe its rows into `dados/<slug>.ts`, add its
 * entry below (sources + caveats are not optional — the page shows them),
 * and it appears on `/coleta` and at `/coleta/<slug>`.
 */
import type { Municipio, PontoEntrega } from './tipos';
import { ROTAS as BARUERI } from './dados/barueri';
import { ROTAS as CARAPICUIBA } from './dados/carapicuiba';
import { RUAS as CARAPICUIBA_RUAS } from './dados/carapicuiba-ruas';
import { ROTAS as COTIA } from './dados/cotia';
import { ROTAS as EMBU } from './dados/embu-das-artes';
import { ROTAS as ITAPEVI } from './dados/itapevi';
import { ROTAS as OSASCO } from './dados/osasco';
import { ROTAS as VARGEM_GRANDE } from './dados/vargem-grande-paulista';

const tel = (numero: string) => `tel:+55${numero.replace(/\D/g, '')}`;
const whatsapp = (numero: string) => `https://wa.me/55${numero.replace(/\D/g, '')}`;

const OSASCO_ECOPONTO_ACEITA =
  'Entulho ensacado (até 1 m³ por CPF), móveis desmontados, colchões, madeira, poda, recicláveis, eletrodomésticos e eletrônicos. Não aceita pneus, amianto, lâmpadas, lixo orgânico nem hospitalar.';
const OSASCO_ECOPONTO_HORARIO = 'Seg a sáb, 7h às 21h (abre em feriados, exceto Natal e Ano Novo)';
const osascoEcoponto = (nome: string, endereco: string, gesso = false): PontoEntrega => ({
  nome: `Ecoponto ${nome}`,
  endereco,
  horario: OSASCO_ECOPONTO_HORARIO,
  aceita: gesso ? `${OSASCO_ECOPONTO_ACEITA} Também recebe gesso.` : OSASCO_ECOPONTO_ACEITA,
});

const CARAPICUIBA_REGIONAL_HORARIO = 'Recebe materiais seg a sex, 8h30 às 16h30; sáb, 8h30 às 11h30';

export const MUNICIPIOS: Municipio[] = [
  {
    slug: 'cotia',
    nome: 'Cotia',
    cobertura: 'parcial',
    resumo:
      'A coleta comum passa três vezes por semana (seg/qua/sex ou ter/qui/sáb), de dia ou à noite conforme o setor; o Centro tem coleta diária. A coleta seletiva atende sobretudo condomínios e bairros cadastrados, um dia por semana. A Granja Viana está nos setores 02, 03, 05, 06, 07 e 25.',
    operador: 'Cotia Ambiental S.A. (concessão, contrato 120/2010)',
    rotas: COTIA,
    ecopontos: [
      {
        nome: 'Ecoponto EcoCotia Limpa — Granja Viana',
        endereco: 'R. Salma, 581 — Parque São George',
        horario: 'Seg a qui, 7h às 17h; sex, 7h às 16h (fechado em feriados)',
        aceita:
          'Plástico, papel, vidro, metal e entulho de pequenas reformas (até 50 kg). Não aceita lixo orgânico, hospitalar, pilhas, lâmpadas nem eletrônicos.',
      },
    ],
    outros: [
      {
        nome: 'Coopernova Cotia Recicla (coleta seletiva)',
        endereco: 'R. Nova Pátria, 120 — Jd. Nova Cotia',
        horario: 'Seg a sex, 8h às 17h',
        aceita: 'Cooperativa que faz a coleta seletiva porta a porta: o condomínio ou bairro se cadastra e recebe um dia fixo de coleta.',
      },
      { nome: 'PEV Pão de Açúcar Granja Viana', endereco: 'Rod. Raposo Tavares, km 23,5', aceita: 'Recicláveis (ponto de entrega voluntária — lista de 2021)' },
      { nome: 'PEV Supermercado Pedroso', endereco: 'Av. Prof. Manoel José Pedroso, 340', aceita: 'Recicláveis (lista de 2021)' },
      { nome: 'PEV Assaí', endereco: 'Estr. do Embu, 162', aceita: 'Recicláveis (lista de 2021)' },
      { nome: 'PEV Caucaia do Alto', endereco: 'Av. Luiz Sacramento, ao lado da Regional', aceita: 'Recicláveis (lista de 2021)' },
    ],
    contatos: [
      { rotulo: 'Secretaria de Obras e Infraestrutura Urbana', valor: '(11) 4703-7355', href: tel('11 4703-7355') },
      { rotulo: 'E-mail da Secretaria de Obras', valor: 'obras@cotia.sp.gov.br', href: 'mailto:obras@cotia.sp.gov.br' },
      { rotulo: 'WhatsApp do ecoponto (divulgado pela imprensa)', valor: '(11) 97717-3516', href: whatsapp('11 97717-3516') },
    ],
    avisos: [
      'O calendário oficial é um PDF escaneado de setembro de 2023 — a prefeitura não publicou versão mais nova.',
      'Faltam no documento as páginas dos setores 15 a 19.',
      'Em abril de 2026 o Tribunal de Contas julgou irregular o contrato da concessionária, e em agosto houve greve dos coletores. Os dias podem mudar — na dúvida, pergunte na portaria ou à prefeitura.',
      'O documento informa o dia e o turno, não o horário.',
    ],
    fontes: [
      { titulo: 'Escala Coleta Domiciliar (PDF)', url: 'https://cotia.sp.gov.br/wp-content/uploads/2023/09/escala-de-coleta-domiciliar.pdf', data: '2023-09', oficial: true },
      { titulo: 'EcoCotia Limpa: Granja Viana ganha ecoponto', url: 'https://cotia.sp.gov.br/ecotia-limpa-regiao-da-granja-viana-ganha-ecoponto-para-descarte-de-entulho-e-reciclaveis/', data: '2025-09-05', oficial: true },
      { titulo: 'Coleta seletiva passa por 12 bairros e 80 condomínios (PEVs)', url: 'https://cotia.sp.gov.br/dia-internacional-da-reciclagem-coleta-seletiva-passa-por-12-bairros-e-80-condominios-de-cotia/', data: '2021-05-17', oficial: true },
      { titulo: 'TCE julga irregular contrato da Cotia Ambiental', url: 'https://cotiatododia.com.br/tribunal-de-contas-julga-irregular-contrato-da-cotia-ambiental-e-propoe-sua-sustacao/', data: '2026-04-17', oficial: false },
      { titulo: 'Ecoponto de Cotia: limites e WhatsApp', url: 'https://www.cotiaecia.com.br/2026/07/ecoponto-de-cotia-recebe-ate-7.html', data: '2026-07-07', oficial: false },
    ],
  },
  {
    slug: 'carapicuiba',
    nome: 'Carapicuíba',
    cobertura: 'completa',
    resumo:
      'São 30 setores, e cada rua pertence a um deles. A maioria tem coleta três vezes por semana, de manhã ou à tarde; Centro e Cohab 5 têm coleta de segunda a sábado. A Fazendinha se divide em dois setores com dias diferentes (24: seg/qua/sex; 25: ter/qui/sáb) — busque sua rua.',
    operador: '4R Ambiental (contrato 90/2024)',
    rotas: CARAPICUIBA,
    ruas: CARAPICUIBA_RUAS,
    ecopontos: [
      { nome: 'Ecoponto e Regional Cohab', endereco: 'Av. Brasil, 292', horario: CARAPICUIBA_REGIONAL_HORARIO },
      { nome: 'Regional Jandaia', endereco: 'Estr. do Gopiúva, 1557', horario: CARAPICUIBA_REGIONAL_HORARIO },
      { nome: 'Regional Santa Brígida', endereco: 'R. Peruíbe, 4', horario: CARAPICUIBA_REGIONAL_HORARIO },
      { nome: 'Regional Veloso', endereco: 'Av. Jatobá, 576', horario: CARAPICUIBA_REGIONAL_HORARIO },
      { nome: 'Regional Ariston', endereco: 'Av. Comendador Dante Carraro, 333', horario: CARAPICUIBA_REGIONAL_HORARIO },
    ],
    outros: [],
    contatos: [
      { rotulo: 'Regional Cohab', valor: '(11) 4184-1179', href: tel('11 4184-1179') },
      { rotulo: 'Regional Santa Brígida', valor: '(11) 4186-2668', href: tel('11 4186-2668') },
      { rotulo: 'Regional Veloso', valor: '(11) 4167-6806', href: tel('11 4167-6806') },
      { rotulo: 'Regional Ariston', valor: '(11) 4183-6864', href: tel('11 4183-6864') },
    ],
    avisos: [
      'Cronograma publicado em 25/09/2024. O contrato de coleta era de 12 meses e não encontramos publicação de renovação — a empresa e os dias podem ter mudado.',
      'Não há calendário municipal de coleta seletiva porta a porta.',
      'O documento informa o dia e o turno, não o horário.',
    ],
    fontes: [
      { titulo: 'Cronograma de Coleta de Lixo (PDF)', url: 'https://carapicuiba.sp.gov.br/uploads/legislacao/26804/mGfuRgi-bX873SgNEAu7CUSRruX0hjQU.pdf', data: '2024-09-25', oficial: true },
      { titulo: 'Regionais / Ecopontos', url: 'https://www.carapicuiba.sp.gov.br/servico/view/31/regionais-ecopontos', oficial: true },
      { titulo: 'Contrato nº 90/2024 (coleta domiciliar)', url: 'https://www.carapicuiba.sp.gov.br/contrato/view/913/contrato-n-902024', data: '2024-10-18', oficial: true },
    ],
  },
  {
    slug: 'osasco',
    nome: 'Osasco',
    cobertura: 'completa',
    resumo:
      'A coleta comum passa três vezes por semana em cada bairro, de dia ou à noite; Centro e Vila Osasco têm coleta de segunda a sábado. A coleta seletiva passa um dia por semana em cada bairro. Móveis e volumosos: agende o cata-bagulho pela Central 156.',
    operador: 'Eco Osasco Ambiental (PPP, contrato 017/2008)',
    rotas: OSASCO,
    ecopontos: [
      osascoEcoponto('Centro', 'Av. Maria Campos, 15'),
      osascoEcoponto('Baronesa', 'R. Duke Elington, 360'),
      osascoEcoponto("Colinas D'Oeste", 'R. Alexandre Vanucchi Leme', true),
      osascoEcoponto('Helena Maria', 'Av. Walt Disney x R. Belmiro Alves da Silva'),
      osascoEcoponto('Mutinga', 'Av. Ônix, 783', true),
      osascoEcoponto('Cidade das Flores', 'Av. Ipê, 527'),
      osascoEcoponto('Jaguaribe', 'R. Fernando Miolin Filho, 150'),
      osascoEcoponto('Novo Osasco', 'R. Theodoro de Souza Brandão, 1020', true),
      osascoEcoponto('Pestana', 'R. José Antonio Augusto, 55'),
      osascoEcoponto('Veloso', 'R. Dr. Armando Anjo Corrêa Filho, 195', true),
    ],
    outros: [
      { nome: 'Cata-bagulho (móveis e volumosos)', endereco: 'Agendamento pela Central 156 — telefone, app ou WhatsApp, 24h. Informe nome, CPF e endereço.' },
      { nome: 'Mini-ecoponto Adalgisa', endereco: 'R. Octávio Catelani', horario: '6h às 22h' },
      { nome: 'Mini-ecoponto Munhoz Jr.', endereco: 'R. Dr. José Marquês de Rezende', horario: '6h às 22h' },
      { nome: 'Mini-ecoponto Bandeiras', endereco: 'R. João Guimarães Rosa, 220', horario: '6h às 22h' },
      { nome: 'Mini-ecoponto Jd. Padroeira', endereco: 'Av. Benedito Alves Turíbio', horario: '6h às 22h' },
    ],
    contatos: [
      { rotulo: 'Central 156', valor: '156 ou (11) 3651-7080', href: 'tel:156' },
      { rotulo: 'Diretoria de Gestão de Resíduos (DIGRES)', valor: '(11) 3652-9353', href: tel('11 3652-9353') },
    ],
    avisos: [
      'As páginas de calendário da prefeitura são de maio de 2022, e o contrato mudou em 2025 (equipes reduzidas e depois reativadas). Se notar diferença, avise a prefeitura — e a gente.',
      'Aos sábados, a coleta noturna começa às 17h (e não às 18h) em 14 bairros, entre eles Centro, IAPI, Mutinga, Km 18 e Quitaúna.',
    ],
    fontes: [
      { titulo: 'Coleta de resíduos domiciliar', url: 'https://osasco.sp.gov.br/coleta-de-residuos-domiciliar/', data: '2022-05-16', oficial: true },
      { titulo: 'Coleta seletiva de resíduos', url: 'https://osasco.sp.gov.br/coleta-seletiva-de-residuos/', data: '2022-05-16', oficial: true },
      { titulo: 'Coleta de lixo terá horário alterado em 14 bairros', url: 'https://osasco.sp.gov.br/coleta-de-lixo-tera-horario-alterado-em-14-bairros/', data: '2023-10-09', oficial: true },
      { titulo: '10º ecoponto é entregue na Av. Maria Campos', url: 'https://osasco.sp.gov.br/10o-ecoponto-e-entregue-na-avenida-maria-campos-no-centro/', data: '2026-05-18', oficial: true },
      { titulo: 'Ecopontos passam a funcionar em novo horário', url: 'https://osasco.sp.gov.br/ecopontos-de-osasco-passam-a-funcionar-em-novo-horario/', data: '2026-04-12', oficial: true },
      { titulo: 'Lixo Zero (mini-ecopontos)', url: 'https://osasco.sp.gov.br/lixo-zero/', data: '2025-04-16', oficial: true },
      { titulo: 'Perguntas frequentes — Central 156', url: 'https://osasco.sp.gov.br/faq-3/', oficial: true },
    ],
  },
  {
    slug: 'barueri',
    nome: 'Barueri',
    cobertura: 'completa',
    resumo:
      'A coleta comum passa três vezes por semana, ou de segunda a sábado nas áreas centrais e empresariais. A diurna começa às 7h e a noturna às 19h. A coleta seletiva passa em todas as ruas, porta a porta, de segunda a sexta.',
    rotas: BARUERI,
    ecopontos: [],
    outros: [
      { nome: 'Cata-cacareco (móveis e volumosos)', endereco: 'Agendamento com a Secretaria de Serviços Municipais — (11) 4162-7300' },
    ],
    contatos: [
      { rotulo: 'Secretaria de Serviços Municipais', valor: '(11) 4162-7300', href: tel('11 4162-7300') },
    ],
    avisos: [
      'A página da prefeitura não traz data de atualização.',
      'O dia da coleta seletiva não é publicado por bairro.',
    ],
    fontes: [
      { titulo: 'Coleta de lixo — Secretaria de Serviços Municipais', url: 'https://portal.barueri.sp.gov.br/secretarias/secretaria-servicos-municipais/coleta-de-lixo', oficial: true },
      { titulo: 'Entenda como funciona a coleta seletiva em Barueri', url: 'https://portal.barueri.sp.gov.br/Noticia/02122025-entenda-como-funciona-a-coleta-seletiva-em-barueri', data: '2025-12-02', oficial: true },
    ],
  },
  {
    slug: 'itapevi',
    nome: 'Itapevi',
    cobertura: 'completa',
    resumo:
      'A coleta comum passa três vezes por semana, de dia ou à noite; a lista oficial mistura bairros e ruas. A coleta seletiva passa um dia por semana em cada região, das 6h às 16h. Móveis e volumosos: cata-bagulho por agendamento no WhatsApp.',
    operador: 'Mais Itapevi (PPP, contrato 166/2021), regulada pela Regula Ita',
    rotas: ITAPEVI,
    ecopontos: [
      { nome: 'Ecoponto Cardoso', endereco: 'Av. Nelson Ferreira Costa, 1990', aceita: 'Entulho, recicláveis e volumosos' },
      { nome: 'Ecoponto Jd. Rosemary', endereco: 'R. Marcolino Bernardes, 7', aceita: 'Entulho, recicláveis e volumosos' },
      { nome: 'Ecoponto Cohab', endereco: 'Av. Pedro Paulino, 51', aceita: 'Entulho, recicláveis e volumosos' },
      { nome: 'Ecoponto Santa Rita', endereco: 'Rod. Eng. Renê B. da Silva, 1402', aceita: 'Entulho, recicláveis e volumosos' },
    ],
    outros: [
      { nome: 'Cata-bagulho (móveis e volumosos)', endereco: 'Agendamento pelo WhatsApp (11) 91237-7500 — cada bairro tem uma semana no calendário anual por região.' },
    ],
    contatos: [
      { rotulo: 'Cata-bagulho (WhatsApp)', valor: '(11) 91237-7500', href: whatsapp('11 91237-7500') },
      { rotulo: 'Serviço de Atendimento (SAU)', valor: '(11) 3181-4127', href: tel('11 3181-4127') },
      { rotulo: 'Regula Ita (agência reguladora)', valor: '(11) 4143-8888, ramal 6025', href: tel('11 4143-8888') },
    ],
    avisos: [
      'Os horários dos ecopontos divergem entre as páginas da prefeitura (seg a sáb 8h–16h numa notícia de 2026; seg a sex 7h–16h e sáb 7h–11h noutra página). Confirme antes de ir.',
      'Uma notícia de 2025 descreve a coleta seletiva das 8h às 16h, com pontos de entrega em prédios públicos além do porta a porta.',
      'O último calendário de cata-bagulho encontrado é de 2025.',
    ],
    fontes: [
      { titulo: 'Coleta de lixo — Regula Ita (PDF)', url: 'https://www.regulaita.com.br/uploads/pagina/arquivos/coleta-de-lixo.pdf', data: '2025-02', oficial: true },
      { titulo: 'Coleta seletiva (PDF)', url: 'https://itapevi.sp.gov.br/wp-content/uploads/2024/04/coleta-seletiva.pdf', data: '2024-04-19', oficial: true },
      { titulo: 'Operação cata-bagulho (PDF)', url: 'https://itapevi.sp.gov.br/wp-content/uploads/2025/01/operacao-cata-bagulho-1-1.pdf', data: '2025-01', oficial: true },
      { titulo: 'Itapevi recolhe mais de 5 mil toneladas de lixo por mês', url: 'https://noticias.itapevi.sp.gov.br/itapevi-recolhe-mais-de-5-mil-toneladas-de-lixo-por-mes/', data: '2026-05-18', oficial: true },
    ],
  },
  {
    slug: 'jandira',
    nome: 'Jandira',
    cobertura: 'sem-calendario',
    resumo:
      'A prefeitura não publica os dias de coleta por bairro. Segundo o plano municipal de resíduos (2024), o Centro e as feiras têm coleta diária e os demais bairros três vezes por semana, num turno que começa às 7h e noutro que começa às 16h.',
    operador: 'Quebec Construções e Tecnologia Ambiental (contrato 02/2023)',
    rotas: [],
    ecopontos: [
      {
        nome: 'Ecoponto Centro',
        endereco: 'Av. João Balhesteiro, ao lado da E.E. Themudo Lessa',
        aceita: 'Volumosos e entulho de construção (sem amianto). Horário não publicado.',
      },
    ],
    outros: [],
    contatos: [],
    avisos: [
      'Não há coleta seletiva municipal desde 2015.',
      'Sabe o dia da coleta no seu bairro? Conte pra gente — é assim que o calendário de Jandira vai ser montado.',
    ],
    fontes: [
      { titulo: 'Plano Municipal de Gestão Integrada de Resíduos — diagnóstico (PDF)', url: 'https://jandira.sp.gov.br/docs/Jandira-SP-PMGIRS_Relat%C3%B3rio01-Diagn%C3%B3sticoPreliminar_abr24.pdf', data: '2024-04', oficial: true },
      { titulo: 'Inauguração do primeiro ecoponto', url: 'https://jandira.sp.gov.br/noticia_completa.php?id=1843', data: '2025-07', oficial: true },
    ],
  },
  {
    slug: 'embu-das-artes',
    nome: 'Embu das Artes',
    cobertura: 'parcial',
    resumo:
      'A coleta comum passa três vezes por semana, de dia ou à noite, e todos os dias à noite no Centro e arredores. A coleta seletiva é feita por cooperativa, com cadastro por telefone.',
    operador: 'Embu Ambiental (PPP)',
    rotas: EMBU,
    ecopontos: [
      { nome: 'Ecoponto de pneus', endereco: 'R. Muni Steimberg, 260 — Centro', horario: 'Seg a sex, 8h30 às 17h' },
    ],
    outros: [
      { nome: 'PEV Parque Francisco Rizzo', endereco: 'R. Alberto Giosa, 320', horario: 'Seg a sex, 8h às 16h; sáb, 8h às 12h' },
      { nome: 'PEV de eletroeletrônicos', endereco: 'R. Oliveira, 442 — Jd. Santo Eduardo', horario: 'Seg a sex, 8h às 17h' },
    ],
    contatos: [
      { rotulo: 'Coleta seletiva (cadastro na cooperativa)', valor: '(11) 4704-5948', href: tel('11 4704-5948') },
      { rotulo: 'AMLURB (fiscalização da limpeza urbana)', valor: '(11) 4781-1072', href: tel('11 4781-1072') },
    ],
    avisos: [
      'O único calendário publicado pela prefeitura é de julho de 2015 — pode estar desatualizado.',
      'O itinerário publicado da coleta seletiva é de 2016 e diverge da página atual; por isso não o reproduzimos.',
    ],
    fontes: [
      { titulo: 'Coleta convencional (PDF)', url: 'https://cidadeembudasartes.sp.gov.br/wp-content/uploads/2021/11/coletaconvencional.pdf', data: '2015-07-07', oficial: true },
      { titulo: 'Coleta de lixo — Prefeitura de Embu das Artes', url: 'https://cidadeembudasartes.sp.gov.br/coleta-de-lixo/', oficial: true },
    ],
  },
  {
    slug: 'vargem-grande-paulista',
    nome: 'Vargem Grande Paulista',
    cobertura: 'completa',
    resumo:
      'Cinco setores em cada grupo de dias (seg/qua/sex e ter/qui/sáb). O cronograma não informa turno nem horário.',
    rotas: VARGEM_GRANDE,
    ecopontos: [],
    outros: [],
    contatos: [],
    avisos: [
      'Uma lista mais antiga (2017) ainda aparece nas buscas e difere em detalhes; vale a imagem publicada em julho de 2026.',
      'Há coleta seletiva em parte da cidade, mas os dias por bairro não foram publicados.',
      'Não encontramos ecoponto oficial.',
    ],
    fontes: [
      { titulo: 'Cronograma de Coleta Residencial (imagem)', url: 'http://www.vargemgrandepaulista.sp.gov.br/site/wp-content/uploads/2026/07/Coleta_de_Lixo.png', data: '2026-07', oficial: true },
      { titulo: 'Coleta seletiva', url: 'https://www.vargemgrandepaulista.sp.gov.br/site/coleta-seletiva/', data: '2023-05-24', oficial: true },
    ],
  },
];

export function municipioPorSlug(slug: string): Municipio | undefined {
  return MUNICIPIOS.find((m) => m.slug === slug);
}
