/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav lives in `nav/navGroups.ts` (gated + derived fallback); the "Julia"
 * chatbot group (WhatsApp Conversas + Configurações) in `nav/julia.ts`.
 *
 * WhatsApp moved out of "Conexões" into the Julia group (owner decision
 * 2026-10-13): `/julia/conversas` + `/julia/configuracoes` (status_pagina keys
 * `julia_conversas` / `julia_configuracoes`, migration 252). The old
 * `/whatsapp-chat` is a back-compat redirect to `/julia/conversas` — it is
 * still the seed `whatsapp` provider card's `dashboardRoute` deep-link.
 * pt-BR copy preserved.
 */
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import { useSocialWiringLayoutEnrichment } from "@/hooks/useLayoutEnrichment";
import { NAV_GROUPS, NAV_FALLBACK } from "@/nav/navGroups";
import { JULIA_PAGES } from "@/nav/julia";
import { Share2 } from "lucide-react";

import { lazyWithReload } from "@noctusai/lib";

// Pages
const Landing = lazyWithReload(() => import("@/pages/Landing"));
const Login = lazyWithReload(() => import("@/pages/Login"));
const AcceptInvite = lazyWithReload(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazyWithReload(() => import("@/pages/ForgotPassword"));
const Chat = lazyWithReload(() => import("@/pages/Chat"));
const Dashboard = lazyWithReload(() => import("@/pages/Dashboard"));
const Equipe = lazyWithReload(() => import("@/pages/Equipe"));
const Custos = lazyWithReload(() => import("@/pages/Custos"));
const Financeiro = lazyWithReload(() => import("@/pages/Financeiro"));
const Permutas = lazyWithReload(() => import("@/pages/Permutas"));
const Condominios = lazyWithReload(() => import("@/pages/Condominios"));
const Settings = lazyWithReload(() => import("@/pages/Settings"));
const YouTube = lazyWithReload(() => import("@/pages/YouTube"));
const N8n = lazyWithReload(() => import("@/pages/N8n"));
const RedirectToMarcas = lazyWithReload(() => import("@/pages/RedirectToMarcas"));
const RedirectToMeta = lazyWithReload(() => import("@/pages/RedirectToMeta"));
const Monitor = lazyWithReload(() => import("@/pages/Monitor"));
const EmailMarketing = lazyWithReload(() => import("@/pages/EmailMarketing"));
const Contatos = lazyWithReload(() => import("@/pages/Contatos"));
const EmailListas = lazyWithReload(() => import("@/pages/EmailListas"));
const EmailTemplates = lazyWithReload(() => import("@/pages/EmailTemplates"));
const EmailCampanhas = lazyWithReload(() => import("@/pages/EmailCampanhas"));
const EmailMarketingConfig = lazyWithReload(() => import("@/pages/EmailMarketingConfig"));
const EmailMembros = lazyWithReload(() => import("@/pages/EmailMembros"));
const NotFound = lazyWithReload(() => import("@/pages/NotFound"));
const JuliaPainel = lazyWithReload(() => import("@/pages/julia/Painel"));
const JuliaConversas = lazyWithReload(() => import("@/pages/julia/Conversas"));
const JuliaConfiguracoes = lazyWithReload(() => import("@/pages/julia/Configuracoes"));
const JuliaAgente = lazyWithReload(() => import("@/pages/julia/Agente"));
const JuliaConhecimento = lazyWithReload(() => import("@/pages/julia/Conhecimento"));
const JuliaPerguntas = lazyWithReload(() => import("@/pages/julia/Perguntas"));
const JuliaHistorico = lazyWithReload(() => import("@/pages/julia/Historico"));
const JuliaVisitas = lazyWithReload(() => import("@/pages/julia/Visitas"));
const JuliaReengajamento = lazyWithReload(() => import("@/pages/julia/Reengajamento"));
const JuliaNotificacoes = lazyWithReload(() => import("@/pages/julia/Notificacoes"));
const JuliaEnvio = lazyWithReload(() => import("@/pages/julia/Envio"));
const JuliaLeads = lazyWithReload(() => import("@/pages/julia/Leads"));
const JuliaReengajamentoRegua = lazyWithReload(() => import("@/pages/julia/ReengajamentoRegua"));
const JuliaModelos = lazyWithReload(() => import("@/pages/julia/Modelos"));
const JuliaDisparos = lazyWithReload(() => import("@/pages/julia/Disparos"));
const JuliaCaptacao = lazyWithReload(() => import("@/pages/julia/Captacao"));
const JuliaProprietarios = lazyWithReload(() => import("@/pages/julia/Proprietarios"));
const JuliaAvaliacoes = lazyWithReload(() => import("@/pages/julia/Avaliacoes"));
const JuliaCredito = lazyWithReload(() => import("@/pages/julia/Credito"));
const JuliaRelatorios = lazyWithReload(() => import("@/pages/julia/Relatorios"));
const JuliaEquipes = lazyWithReload(() => import("@/pages/julia/Equipes"));
const JuliaOptOuts = lazyWithReload(() => import("@/pages/julia/OptOuts"));
const RedirectToJuliaConversas = lazyWithReload(() => import("@/pages/RedirectToJuliaConversas"));
const RedirectLegacyLais = lazyWithReload(() => import("@/pages/RedirectLegacyLais"));
const Marcas = lazyWithReload(() => import("@/pages/Marcas"));
const Imoveis = lazyWithReload(() => import("@/pages/Imoveis"));
const ImovelDetalhes = lazyWithReload(() => import("@/pages/ImovelDetalhes"));
const MetaDashboard = lazyWithReload(() => import("@/pages/MetaDashboard"));
const Simec = lazyWithReload(() => import("@/pages/simec/Simec"));
const Leads = lazyWithReload(() => import("@/pages/leads/Leads"));
const Campanhas = lazyWithReload(() => import("@/pages/campanhas/Campanhas"));
const FunilVendas = lazyWithReload(() => import("@/pages/funil/FunilVendas"));
const ProcessosVenda = lazyWithReload(() => import("@/pages/funil/ProcessosVenda"));
const PortalRoi = lazyWithReload(() => import("@/pages/PortalRoi"));
const ClientesBoard = lazyWithReload(() => import("@/pages/clientes/ClientesBoard"));
const RevisaoFila = lazyWithReload(() => import("@/pages/clientes/RevisaoFila"));
const PessoaPage = lazyWithReload(() => import("@/pages/PessoaPage"));
const Agendamentos = lazyWithReload(() => import("@/pages/scheduling/Agendamentos"));
const EmailPainel = lazyWithReload(() => import("@/pages/email/Painel"));
const EmailCampanhasNoc = lazyWithReload(() => import("@/pages/email/Campanhas"));
const EmailContatosNoc = lazyWithReload(() => import("@/pages/email/Contatos"));
const EmailListasNoc = lazyWithReload(() => import("@/pages/email/Listas"));
const EmailTemplatesNoc = lazyWithReload(() => import("@/pages/email/Templates"));
const EmailAutomacoes = lazyWithReload(() => import("@/pages/email/Automacoes"));
const EmailDominios = lazyWithReload(() => import("@/pages/email/Dominios"));
const JuliaAvisoPrivacidade = lazyWithReload(() => import("@/pages/julia/AvisoPrivacidade"));
const EmailDescadastro = lazyWithReload(() => import("@/pages/email/Descadastro"));
const EmailConfirmarEmail = lazyWithReload(() => import("@/pages/email/ConfirmarEmail"));
const Certidoes = lazyWithReload(() => import("@/pages/Certidoes"));
const Matriculas = lazyWithReload(() => import("@/pages/Matriculas"));
const AgentesFinanceiros = lazyWithReload(
  () => import("@/pages/AgentesFinanceiros"),
);
const Testemunhas = lazyWithReload(() => import("@/pages/Testemunhas"));
const Favorecidos = lazyWithReload(() => import("@/pages/Favorecidos"));
const Pesquisa = lazyWithReload(() => import("@/pages/Pesquisa"));
const ExtrairPesquisa = lazyWithReload(() => import("@/pages/ExtrairPesquisa"));
const CerebroLista = lazyWithReload(() => import("@/pages/cerebro/CerebroLista"));
const CerebroEditor = lazyWithReload(() => import("@/pages/cerebro/CerebroEditor"));
const CerebroPerguntas = lazyWithReload(() => import("@/pages/cerebro/CerebroPerguntas"));
const GeracaoDashboard = lazyWithReload(() => import("@/pages/geracao/Dashboard"));
const GeracaoChat = lazyWithReload(() => import("@/pages/geracao/Chat"));
const GeracaoBiblioteca = lazyWithReload(() => import("@/pages/geracao/Biblioteca"));
const GeracaoMeuPerfil = lazyWithReload(() => import("@/pages/geracao/MeuPerfil"));
const GeracaoMinhaBiblioteca = lazyWithReload(() => import("@/pages/geracao/MinhaBiblioteca"));
const GeracaoTreinamentos = lazyWithReload(() => import("@/pages/geracao/Treinamentos"));
const GeracaoHeadlinesGerar = lazyWithReload(() => import("@/pages/geracao/HeadlinesGerar"));
const GeracaoHeadlines = lazyWithReload(() => import("@/pages/geracao/Headlines"));
const GeracaoHeadlinesFavoritas = lazyWithReload(() => import("@/pages/geracao/HeadlinesFavoritas"));
const GeracaoHeadlinesSugeridas = lazyWithReload(() => import("@/pages/geracao/HeadlinesSugeridas"));
const GeracaoRoteiros = lazyWithReload(() => import("@/pages/geracao/Roteiros"));
const GeracaoEsteira = lazyWithReload(() => import("@/pages/geracao/Esteira"));
const GeracaoBranding = lazyWithReload(() => import("@/pages/geracao/Branding"));
const GeracaoCarrosseis = lazyWithReload(() => import("@/pages/geracao/Carrosseis"));
const RedirectMediaCreation = lazyWithReload(() => import("@/pages/RedirectMediaCreation"));
const MinhasExtracoes = lazyWithReload(() => import("@/pages/cerebro/MinhasExtracoes"));
const Imobiliarias = lazyWithReload(() => import("@/pages/Imobiliarias"));
// Edição de Fotos — W10a (plan §4/§7). Admin pages (Referências, Guias —
// W6; Regras — W7; Curadores — notify slice; Painel — W9; Modelos +
// Processamento — W8) are all shipped.
const EdicaoFotosLotes = lazyWithReload(() => import("@/pages/edicao-fotos/Lotes"));
const EdicaoFotosNovoLote = lazyWithReload(() => import("@/pages/edicao-fotos/NovoLote"));
const EdicaoFotosLoteRevisao = lazyWithReload(() => import("@/pages/edicao-fotos/LoteRevisao"));
const EdicaoFotosConfiguracoes = lazyWithReload(() => import("@/pages/edicao-fotos/Configuracoes"));
const EdicaoFotosReferencias = lazyWithReload(() => import("@/pages/edicao-fotos/Referencias"));
const EdicaoFotosGuiasEstilo = lazyWithReload(() => import("@/pages/edicao-fotos/GuiasEstilo"));
const EdicaoFotosRegras = lazyWithReload(() => import("@/pages/edicao-fotos/Regras"));
const EdicaoFotosCuradores = lazyWithReload(() => import("@/pages/edicao-fotos/Curadores"));
const EdicaoFotosPainel = lazyWithReload(() => import("@/pages/edicao-fotos/Painel"));
const EdicaoFotosModelos = lazyWithReload(() => import("@/pages/edicao-fotos/Modelos"));
const EdicaoFotosProcessamento = lazyWithReload(() => import("@/pages/edicao-fotos/Processamento"));
// Maya v1 (maya-blocks CONTRACT §4) — both seeded `desenvolvimento` in status_pagina (286).
const AtendimentoBlocos = lazyWithReload(() => import("@/pages/AtendimentoBlocos"));
const Supervisao = lazyWithReload(() => import("@/pages/Supervisao"));


const Layout = createProductLayout({
  brandIcon: Share2,
  brandTitle: "Social Wiring",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
  useLayoutEnrichment: useSocialWiringLayoutEnrichment,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/media-creation", component: RedirectMediaCreation },
    { path: "/media-creation/pesquisa", component: Pesquisa },
    { path: "/media-creation/pesquisa/extrair", component: ExtrairPesquisa },
    { path: "/media-creation/cerebro", component: CerebroLista },
    { path: "/media-creation/cerebro/extracoes", component: MinhasExtracoes },
    { path: "/media-creation/cerebro/:brainId", component: CerebroEditor },
    { path: "/media-creation/cerebro/:brainId/perguntas", component: CerebroPerguntas },
    { path: "/media-creation/dashboard", component: GeracaoDashboard },
    { path: "/media-creation/chat", component: GeracaoChat },
    { path: "/media-creation/biblioteca", component: GeracaoBiblioteca },
    { path: "/media-creation/perfil", component: GeracaoMeuPerfil },
    { path: "/media-creation/minha-biblioteca", component: GeracaoMinhaBiblioteca },
    { path: "/media-creation/treinamentos", component: GeracaoTreinamentos },
    { path: "/media-creation/headlines/gerar", component: GeracaoHeadlinesGerar },
    { path: "/media-creation/headlines", component: GeracaoHeadlines },
    { path: "/media-creation/headlines/favoritas", component: GeracaoHeadlinesFavoritas },
    { path: "/media-creation/headlines/sugeridas", component: GeracaoHeadlinesSugeridas },
    { path: "/media-creation/roteiros", component: GeracaoRoteiros },
    { path: "/media-creation/esteira", component: GeracaoEsteira },
    { path: "/media-creation/carrosseis", component: GeracaoCarrosseis },
    { path: "/media-creation/branding", component: GeracaoBranding },
    // Legacy /email-marketing repointed at EmailCampanhas (vestigial EmailMarketing.tsx stays but is unrouted)
    { path: "/email-marketing", component: EmailCampanhas },
    { path: "/contatos", component: Contatos },
    { path: "/leads", component: Leads },
    { path: "/campanhas", component: Campanhas },
    { path: "/funil", component: FunilVendas },
    { path: "/processos-venda", component: ProcessosVenda },
    { path: "/portal-roi", component: PortalRoi },
    { path: "/atendimento-blocos", component: AtendimentoBlocos },
    { path: "/supervisao", component: Supervisao },
    { path: "/certidoes", component: Certidoes },
    { path: "/matriculas", component: Matriculas },
    { path: "/agentes-financeiros", component: AgentesFinanceiros },
    { path: "/testemunhas", component: Testemunhas },
    { path: "/favorecidos", component: Favorecidos },
    { path: "/imobiliarias", component: Imobiliarias },
    { path: "/edicao-fotos", component: EdicaoFotosLotes },
    { path: "/edicao-fotos/novo", component: EdicaoFotosNovoLote },
    { path: "/edicao-fotos/lotes/:loteId/revisao", component: EdicaoFotosLoteRevisao },
    { path: "/edicao-fotos/configuracoes", component: EdicaoFotosConfiguracoes },
    { path: "/edicao-fotos/referencias", component: EdicaoFotosReferencias },
    { path: "/edicao-fotos/guias", component: EdicaoFotosGuiasEstilo },
    { path: "/edicao-fotos/regras", component: EdicaoFotosRegras },
    { path: "/edicao-fotos/curadores", component: EdicaoFotosCuradores },
    { path: "/edicao-fotos/painel", component: EdicaoFotosPainel },
    { path: "/edicao-fotos/modelos", component: EdicaoFotosModelos },
    { path: "/edicao-fotos/processamento", component: EdicaoFotosProcessamento },
    { path: "/clientes", component: ClientesBoard },
    // `/clientes/revisao` MUST stay declared before `/clientes/:id`.
    { path: "/clientes/revisao", component: RevisaoFila },
    // ONE person page, two section orders (atendimento-partes-imoveis D3).
    // Detail routes reached from lists — no nav entry (same shape as
    // `/imoveis/:codigo` next to the `imoveis` entry).
    { path: "/clientes/:id", component: PessoaPage },
    { path: "/vendedores/:id", component: PessoaPage },
    { path: "/email-marketing/listas", component: EmailListas },
    { path: "/email-marketing/templates", component: EmailTemplates },
    { path: "/email-marketing/campanhas", component: EmailCampanhas },
    { path: "/email-marketing/configuracao", component: EmailMarketingConfig },
    { path: "/email-marketing/membros", component: EmailMembros },
    { path: "/youtube", component: YouTube },
    { path: "/n8n", component: N8n },
    { path: "/meta", component: MetaDashboard },
    // SIMEC — marketing intelligence (status_pagina `simec`, migration 284)
    { path: "/simec", component: Simec },
    // Retired route — remodeled into the unified Meta dashboard (Wave 3)
    { path: "/instagram-insights", component: RedirectToMeta },
    // Retired routes — connection management now lives inside MarcaModal
    { path: "/conexoes", component: RedirectToMarcas },
    { path: "/integrations", component: RedirectToMarcas },
    { path: "/conexao", component: RedirectToMarcas },
    { path: "/marcas", component: Marcas },
    { path: "/imoveis", component: Imoveis },
    { path: "/imoveis/:codigo", component: ImovelDetalhes },
    { path: "/permutas", component: Permutas },
    { path: "/condominios", component: Condominios },
    { path: "/agendamentos", component: Agendamentos },
    { path: "/email", component: EmailPainel },
    { path: "/email/campanhas", component: EmailCampanhasNoc },
    { path: "/email/contatos", component: EmailContatosNoc },
    { path: "/email/listas", component: EmailListasNoc },
    { path: "/email/templates", component: EmailTemplatesNoc },
    { path: "/email/automacoes", component: EmailAutomacoes },
    { path: "/email/dominios", component: EmailDominios },
    { path: "/monitor", component: Monitor },
    // Julia (chatbot module) — WhatsApp conversations + connection settings
    { path: JULIA_PAGES.painel.href, component: JuliaPainel },
    { path: JULIA_PAGES.conversas.href, component: JuliaConversas },
    { path: JULIA_PAGES.configuracoes.href, component: JuliaConfiguracoes },
    { path: JULIA_PAGES.agente.href, component: JuliaAgente },
    { path: JULIA_PAGES.conhecimento.href, component: JuliaConhecimento },
    { path: JULIA_PAGES.perguntas.href, component: JuliaPerguntas },
    { path: JULIA_PAGES.visitas.href, component: JuliaVisitas },
    { path: JULIA_PAGES.reengajamento.href, component: JuliaReengajamento },
    { path: JULIA_PAGES.notificacoes.href, component: JuliaNotificacoes },
    { path: JULIA_PAGES.envio.href, component: JuliaEnvio },
    { path: JULIA_PAGES.leads.href, component: JuliaLeads },
    { path: JULIA_PAGES.equipes.href, component: JuliaEquipes },
    { path: JULIA_PAGES.optOuts.href, component: JuliaOptOuts },
    { path: `${JULIA_PAGES.reengajamento.href}/reguas/:id`, component: JuliaReengajamentoRegua },
    { path: JULIA_PAGES.modelos.href, component: JuliaModelos },
    { path: JULIA_PAGES.disparos.href, component: JuliaDisparos },
    { path: JULIA_PAGES.proprietarios.href, component: JuliaProprietarios },
    { path: JULIA_PAGES.relatorios.href, component: JuliaRelatorios },
    { path: JULIA_PAGES.captacao.href, component: JuliaCaptacao },
    { path: JULIA_PAGES.avaliacoes.href, component: JuliaAvaliacoes },
    { path: JULIA_PAGES.credito.href, component: JuliaCredito },
    // Retired route — WhatsApp moved into the Julia group (2026-10-13)
    { path: "/whatsapp-chat", component: RedirectToJuliaConversas },
    // Pre-rename URLs (Lais -> Julia, 2026-10-19). NOC-REMEDIATE[drop-lais-route-alias]
    { path: "/lais", component: RedirectLegacyLais },
    { path: "/lais/*", component: RedirectLegacyLais },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes", component: Settings },
    { path: "/custos", component: Custos },
    { path: "/financeiro/*", component: Financeiro },
  ],
  // /chat is public — the backend chat router is unauthenticated by
  // current product direction, so the frontend route matches that
  // posture. The same panel renders as YouTube → Upload → Chat.
  publicRoutes: [
    { path: "/chat", component: Chat },
    // Public e-mail unsubscribe link target (token-authenticated, no login).
    { path: "/descadastro/:token", component: EmailDescadastro },
    // Public double opt-in confirmation link target (token-authenticated, no login).
    { path: "/confirmar-email/:token", component: EmailConfirmarEmail },
    // Public per-org Julia privacy notice (LGPD; linked in the first WhatsApp message).
    { path: "/privacidade/:slug", component: JuliaAvisoPrivacidade },
  ],
  Layout,
  // Julia history link (A7): authenticated, chrome-light (no Layout).
  unwrappedRoutes: [{ path: `${JULIA_PAGES.conversas.href}/h/:contatoId`, component: JuliaHistorico }],
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
