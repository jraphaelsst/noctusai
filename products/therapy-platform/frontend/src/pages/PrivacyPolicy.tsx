import { PublicLayout } from '@/components/layout/PublicLayout';

const sections = [
  {
    title: '1. Dados Coletados',
    content: `Coletamos os seguintes tipos de dados pessoais:

- Dados de identificacao: nome, email, telefone, CPF/CNPJ, CRP (terapeutas)
- Dados de saude: informacoes fornecidas durante sessoes terapeuticas, resumos de sessoes, tags clinicas, notas de prontuario
- Dados financeiros: informacoes de pagamento, historico de transacoes, dados bancarios para saque
- Dados de uso: logs de acesso, interacoes com a plataforma, preferencias de configuracao
- Dados de comunicacao: mensagens trocadas na plataforma, avaliacoes, denuncias
- Dados de gravacao: audio de sessoes (apenas com consentimento explicito), transcricoes geradas por IA`,
  },
  {
    title: '2. Finalidade do Tratamento',
    content: `Os dados pessoais sao tratados para as seguintes finalidades:

- Prestacao dos servicos da plataforma (agendamento, sessoes, pagamentos)
- Verificacao e aprovacao de terapeutas e clinicas
- Geracao de resumos e insights por inteligencia artificial
- Processamento de pagamentos e operacoes financeiras
- Comunicacao entre usuarios (mensagens, notificacoes)
- Melhoria continua da plataforma e experiencia do usuario
- Cumprimento de obrigacoes legais e regulatorias
- Moderacao de conteudo e seguranca da plataforma`,
  },
  {
    title: '3. Base Legal (LGPD)',
    content: `O tratamento de dados pessoais e realizado com base em:

- Consentimento do titular (Art. 7o, I): gravacao de sessoes, envio de comunicacoes opcionais
- Execucao de contrato (Art. 7o, V): prestacao dos servicos contratados
- Exercicio regular de direitos (Art. 7o, VI): defesa em processos judiciais ou administrativos
- Protecao da saude (Art. 7o, VIII): tratamento de dados sensiveis de saude em procedimento realizado por profissional de saude
- Interesse legitimo (Art. 7o, IX): melhoria da plataforma, prevencao a fraude, seguranca
- Cumprimento de obrigacao legal (Art. 7o, II): manutencao de registros conforme legislacao aplicavel`,
  },
  {
    title: '4. Compartilhamento de Dados',
    content: `Os dados pessoais podem ser compartilhados com:

- Terapeuta/paciente envolvido na sessao (dados necessarios para o atendimento)
- Clinica vinculada ao terapeuta (dados de sessao e financeiros)
- Processadores de pagamento (dados financeiros para transacoes)
- Provedores de servicos de IA (dados anonimizados para geracao de resumos)
- Autoridades publicas (quando exigido por lei ou ordem judicial)

Nao vendemos, alugamos ou compartilhamos dados pessoais com terceiros para fins de marketing.`,
  },
  {
    title: '5. Armazenamento e Seguranca',
    content: `Os dados pessoais sao armazenados em servidores seguros com as seguintes medidas:

- Criptografia em transito (TLS/SSL) e em repouso
- Controle de acesso baseado em funcoes (RBAC)
- Isolamento de dados por organizacao (multi-tenant)
- Backups regulares com criptografia
- Monitoramento e deteccao de intrusao
- Auditorias periodicas de seguranca

Os dados de saude recebem camadas adicionais de protecao, incluindo criptografia especifica e acesso restrito.`,
  },
  {
    title: '6. Direitos do Titular',
    content: `Conforme a LGPD, voce tem os seguintes direitos:

- Confirmacao da existencia de tratamento
- Acesso aos dados pessoais
- Correcao de dados incompletos, inexatos ou desatualizados
- Anonimizacao, bloqueio ou eliminacao de dados desnecessarios
- Portabilidade dos dados a outro fornecedor de servico
- Eliminacao dos dados pessoais tratados com consentimento
- Informacao sobre compartilhamento de dados
- Informacao sobre a possibilidade de nao fornecer consentimento e consequencias
- Revogacao do consentimento

Para exercer seus direitos, entre em contato pelo email: privacidade@noctusai.com ou pela secao de Configuracoes da sua conta.`,
  },
  {
    title: '7. Cookies e Tecnologias Similares',
    content: `Utilizamos cookies e tecnologias similares para:

- Cookies essenciais: autenticacao, preferencias de sessao, seguranca
- Cookies de desempenho: analise de uso da plataforma, identificacao de problemas
- Cookies de funcionalidade: personalizacao da experiencia, preferencias do usuario

Voce pode gerenciar as preferencias de cookies nas configuracoes do seu navegador. A desativacao de cookies essenciais pode impactar o funcionamento da plataforma.`,
  },
  {
    title: '8. Retencao de Dados',
    content: `Os dados pessoais sao retidos pelo tempo necessario para cumprir as finalidades descritas nesta politica:

- Dados de conta: enquanto a conta estiver ativa + 5 anos apos inativacao
- Dados de sessao: conforme periodo de retencao configurado na plataforma
- Gravacoes de audio: conforme periodo configurado (padrao: exclusao apos processamento)
- Dados financeiros: 5 anos conforme legislacao tributaria
- Logs de acesso: 6 meses conforme Marco Civil da Internet`,
  },
  {
    title: '9. Transferencia Internacional',
    content: `Os dados podem ser processados em servidores localizados fora do Brasil, sempre com garantias adequadas de protecao conforme exigido pela LGPD, incluindo clausulas contratuais padrao e certificacoes de seguranca.`,
  },
  {
    title: '10. Encarregado de Protecao de Dados (DPO)',
    content: `Para questoes relacionadas a protecao de dados pessoais, entre em contato com nosso Encarregado (DPO):

Email: dpo@noctusai.com
Endereco: [Endereco a ser definido]

O Encarregado e responsavel por receber reclamacoes, comunicar-se com a Autoridade Nacional de Protecao de Dados (ANPD) e orientar os funcionarios sobre as melhores praticas de protecao de dados.`,
  },
  {
    title: '11. Alteracoes desta Politica',
    content: `Esta Politica de Privacidade pode ser atualizada periodicamente. Alteracoes significativas serao comunicadas por email ou notificacao na Plataforma com antecedencia minima de 30 dias. O uso continuado da Plataforma apos a publicacao das alteracoes constitui aceitacao da nova politica.`,
  },
];

export default function PrivacyPolicy() {
  return (
    <PublicLayout>
      <div className="max-w-3xl mx-auto py-12 px-4">
        <h1 className="text-3xl font-bold mb-2">Politica de Privacidade</h1>
        <p className="text-sm text-muted-foreground mb-8">
          Ultima atualizacao: {new Date().toLocaleDateString('pt-BR')} | Em conformidade com a LGPD (Lei 13.709/2018)
        </p>

        <div className="space-y-8">
          {sections.map(s => (
            <div key={s.title}>
              <h2 className="text-lg font-semibold mb-2">{s.title}</h2>
              <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
                {s.content}
              </p>
            </div>
          ))}
        </div>
      </div>
    </PublicLayout>
  );
}
