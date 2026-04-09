import { PublicLayout } from '@/components/layout/PublicLayout';

const sections = [
  {
    title: '1. Aceitacao dos Termos',
    content: `Ao acessar e utilizar a plataforma NoctusAI Terapia ("Plataforma"), voce concorda com os presentes Termos de Uso. Caso nao concorde com alguma disposicao, nao utilize a Plataforma. O uso continuado apos alteracoes constitui aceitacao dos novos termos.`,
  },
  {
    title: '2. Descricao dos Servicos',
    content: `A Plataforma oferece servicos de intermediacao entre pacientes e terapeutas, incluindo: agendamento de sessoes online, processamento de pagamentos, geracao de resumos com inteligencia artificial, sistema de mensagens, gestao financeira e ferramentas administrativas para clinicas. A Plataforma nao presta servicos de saude diretamente — os servicos terapeuticos sao prestados exclusivamente pelos profissionais cadastrados.`,
  },
  {
    title: '3. Cadastro e Conta',
    content: `Para utilizar a Plataforma, voce deve criar uma conta fornecendo informacoes verdadeiras, completas e atualizadas. Voce e responsavel por manter a confidencialidade de suas credenciais de acesso. Terapeutas devem fornecer numero de registro profissional (CRP) valido e passar por processo de verificacao. Clinicas devem fornecer CNPJ valido.`,
  },
  {
    title: '4. Uso da Plataforma',
    content: `Voce se compromete a utilizar a Plataforma de forma etica e em conformidade com a legislacao vigente. E proibido: (i) utilizar a Plataforma para fins ilegais; (ii) compartilhar conteudo ofensivo, difamatorio ou que viole direitos de terceiros; (iii) tentar acessar dados de outros usuarios sem autorizacao; (iv) utilizar bots, scrapers ou ferramentas automatizadas nao autorizadas; (v) interferir no funcionamento da Plataforma.`,
  },
  {
    title: '5. Sessoes Terapeuticas',
    content: `As sessoes sao realizadas por meio da Plataforma em ambiente seguro e privado. A gravacao de sessoes e opcional e requer consentimento explicito do paciente. Resumos gerados por inteligencia artificial sao ferramentas auxiliares e nao substituem o julgamento profissional do terapeuta. O sigilo terapeutico e respeitado conforme o Codigo de Etica do Psicologo.`,
  },
  {
    title: '6. Pagamentos',
    content: `Os pagamentos sao processados de forma segura pela Plataforma. O valor da sessao e pre-autorizado no momento do agendamento e capturado apos a conclusao da sessao. A Plataforma cobra uma taxa de servico sobre cada transacao. Os valores sao creditados na carteira digital do terapeuta ou clinica, com opcao de saque para conta bancaria.`,
  },
  {
    title: '7. Cancelamentos e Reembolsos',
    content: `Sessoes podem ser canceladas de acordo com a politica de cancelamento vigente. Cancelamentos realizados com antecedencia suficiente nao geram cobranca. Cancelamentos tardios podem estar sujeitos a cobranca parcial ou integral. Solicitacoes de reembolso sao avaliadas caso a caso pela equipe da Plataforma.`,
  },
  {
    title: '8. Privacidade e Protecao de Dados',
    content: `O tratamento de dados pessoais e realizado em conformidade com a Lei Geral de Protecao de Dados (LGPD) e nossa Politica de Privacidade. Dados de saude sao tratados com medidas adicionais de seguranca. Para mais informacoes, consulte nossa Politica de Privacidade.`,
  },
  {
    title: '9. Propriedade Intelectual',
    content: `Todo o conteudo da Plataforma, incluindo textos, graficos, logotipos, icones, imagens, software e codigo-fonte, e de propriedade da NoctusAI ou de seus licenciadores e esta protegido pela legislacao de propriedade intelectual. O uso da Plataforma nao confere ao usuario qualquer direito sobre a propriedade intelectual.`,
  },
  {
    title: '10. Limitacao de Responsabilidade',
    content: `A Plataforma e fornecida "no estado em que se encontra". A NoctusAI nao se responsabiliza por: (i) qualidade ou adequacao dos servicos prestados pelos terapeutas; (ii) interrupcoes ou falhas tecnicas fora de seu controle; (iii) danos indiretos, incidentais ou consequenciais; (iv) perda de dados causada por terceiros. A responsabilidade total da NoctusAI e limitada ao valor pago pelo usuario nos ultimos 12 meses.`,
  },
  {
    title: '11. Alteracoes dos Termos',
    content: `A NoctusAI reserva-se o direito de alterar estes Termos a qualquer momento. As alteracoes entram em vigor apos a publicacao na Plataforma. Alteracoes significativas serao comunicadas por email ou notificacao na Plataforma com antecedencia de 30 dias.`,
  },
  {
    title: '12. Contato',
    content: `Para duvidas, reclamacoes ou solicitacoes relacionadas a estes Termos, entre em contato conosco pelo email: suporte@noctusai.com ou pelo canal de Suporte da Plataforma. Estes Termos sao regidos pela legislacao brasileira. O foro da comarca de Sao Paulo/SP e competente para resolver quaisquer controversias.`,
  },
];

export default function TermsOfUse() {
  return (
    <PublicLayout>
      <div className="max-w-3xl mx-auto py-12 px-4">
        <h1 className="text-3xl font-bold mb-2">Termos de Uso</h1>
        <p className="text-sm text-muted-foreground mb-8">
          Ultima atualizacao: {new Date().toLocaleDateString('pt-BR')}
        </p>

        <div className="space-y-8">
          {sections.map(s => (
            <div key={s.title}>
              <h2 className="text-lg font-semibold mb-2">{s.title}</h2>
              <p className="text-sm text-muted-foreground leading-relaxed">{s.content}</p>
            </div>
          ))}
        </div>
      </div>
    </PublicLayout>
  );
}
