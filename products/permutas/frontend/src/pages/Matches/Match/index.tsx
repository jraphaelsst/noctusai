import React, { useState, useEffect, useContext } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import styled from 'styled-components'
import Container from '../../../containers/Container'
import { color, spacing, radius } from '../../../styles'
import useAxios from '../../../utils/useAxios'
import AuthContext from '../../../context/AuthContext'
import { formatCurrency } from '../../../utils/formatCurrency'
import Spinner from '../../../components/Spinner'

const PageHeader = styled.div`
  background: ${color.primary};
  border-radius: ${radius.sm};
  padding: ${spacing.xl};
  margin-bottom: ${spacing.lg};
  color: ${color.textInverse};
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: ${spacing.md};

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: flex-start;
  }
`

const HeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.md};
`

const BackButton = styled.button`
  background: transparent;
  border: 1px solid ${color.textInverse};
  color: ${color.textInverse};
  padding: ${spacing.sm} ${spacing.md};
  border-radius: ${radius.sm};
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: ${spacing.xs};

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }
`

const PageTitle = styled.h1`
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
  color: ${color.textInverse};
`

const Badge = styled.span<{ $type?: string }>`
  background: ${props => {
    switch (props.$type) {
      case 'bilateral': return color.success;
      case 'novo': return '#6c5ce7';
      case 'avaliacao': return '#00b894';
      case 'negociacao': return '#fdcb6e';
      case 'fechado': return '#2d3436';
      case 'rejeitado': return color.danger;
      default: return color.textLight;
    }
  }};
  color: ${props => props.$type === 'negociacao' ? color.primary : 'white'};
  padding: ${spacing.xs} ${spacing.sm};
  border-radius: ${radius.sm};
  font-size: 12px;
  font-weight: 600;
`

const HeaderActions = styled.div`
  display: flex;
  gap: ${spacing.sm};
  flex-wrap: wrap;
`

const ActionButton = styled.button<{ $variant?: 'success' | 'danger' | 'primary' }>`
  background: ${props => {
    switch (props.$variant) {
      case 'success': return color.success;
      case 'danger': return color.danger;
      default: return color.cardBg;
    }
  }};
  color: ${props => props.$variant ? 'white' : color.primary};
  border: none;
  padding: ${spacing.sm} ${spacing.lg};
  border-radius: ${radius.sm};
  font-weight: 500;
  cursor: pointer;
  font-size: 14px;

  &:hover {
    opacity: 0.9;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`

const Grid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: ${spacing.lg};

  @media (max-width: 1024px) {
    grid-template-columns: 1fr;
  }
`

const Section = styled.div`
  background: ${color.cardBg};
  border: 1px solid ${color.border};
  border-radius: ${radius.sm};
  margin-bottom: ${spacing.lg};
`

const SectionHeader = styled.div<{ $color?: string }>`
  background: ${props => props.$color || color.primary};
  color: white;
  padding: ${spacing.md} ${spacing.lg};
  border-radius: ${radius.sm} ${radius.sm} 0 0;
  font-weight: 600;
  font-size: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
`

const SectionBody = styled.div`
  padding: ${spacing.lg};
`

const InfoRow = styled.div`
  display: flex;
  justify-content: space-between;
  padding: ${spacing.sm} 0;
  border-bottom: 1px solid ${color.border};
  font-size: 14px;

  &:last-child {
    border-bottom: none;
  }
`

const InfoLabel = styled.span`
  color: ${color.textLight};
`

const InfoValue = styled.span`
  color: ${color.text};
  font-weight: 500;
  text-align: right;
`

const MatchCriteriaBox = styled.div`
  background: ${color.background};
  border: 2px dashed ${color.border};
  border-radius: ${radius.sm};
  padding: ${spacing.lg};
  text-align: center;
  margin-bottom: ${spacing.lg};
`

const MatchArrow = styled.div`
  font-size: 24px;
  color: ${color.success};
  margin: ${spacing.md} 0;
`

const CriteriaText = styled.div`
  font-size: 14px;
  color: ${color.text};
  margin: ${spacing.xs} 0;
`

const MatchCheck = styled.div`
  color: ${color.success};
  font-size: 14px;
  margin-top: ${spacing.md};
  display: flex;
  align-items: center;
  justify-content: center;
  gap: ${spacing.xs};
`

const FinancialBox = styled.div`
  background: ${color.background};
  border-radius: ${radius.sm};
  padding: ${spacing.lg};
`

const FinancialRow = styled.div`
  display: flex;
  justify-content: space-between;
  padding: ${spacing.sm} 0;
  font-size: 14px;
`

const FinancialTotal = styled.div`
  display: flex;
  justify-content: space-between;
  padding: ${spacing.md} 0;
  font-size: 16px;
  font-weight: 600;
  border-top: 2px solid ${color.border};
  margin-top: ${spacing.sm};
  color: ${color.primary};
`

const ClientCard = styled.div`
  background: ${color.background};
  border-radius: ${radius.sm};
  padding: ${spacing.md};
  margin-bottom: ${spacing.md};
`

const ClientName = styled.div`
  font-weight: 600;
  font-size: 16px;
  color: ${color.primary};
  margin-bottom: ${spacing.sm};
`

const ContactInfo = styled.div`
  font-size: 13px;
  color: ${color.textLight};
  display: flex;
  flex-direction: column;
  gap: ${spacing.xs};
`

const InterestsBox = styled.div`
  background: ${color.background};
  border-radius: ${radius.sm};
  padding: ${spacing.md};
  margin-top: ${spacing.md};
`

const InterestItem = styled.div`
  font-size: 13px;
  padding: ${spacing.xs} 0;
  color: ${color.text};
  border-bottom: 1px dashed ${color.border};

  &:last-child {
    border-bottom: none;
  }
`

const ObservacaoForm = styled.div`
  margin-top: ${spacing.md};
`

const TextArea = styled.textarea`
  width: 100%;
  min-height: 80px;
  padding: ${spacing.md};
  border: 1px solid ${color.border};
  border-radius: ${radius.sm};
  font-family: inherit;
  font-size: 14px;
  resize: vertical;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const ObservacaoDisplay = styled.pre`
  background: ${color.background};
  padding: ${spacing.md};
  border-radius: ${radius.sm};
  font-family: inherit;
  font-size: 13px;
  white-space: pre-wrap;
  word-wrap: break-word;
  color: ${color.text};
  margin-top: ${spacing.md};
  max-height: 200px;
  overflow-y: auto;
`

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
`

const RefLink = styled.span`
  color: ${color.primary};
  cursor: pointer;
  font-weight: 600;

  &:hover {
    opacity: 0.8;
  }
`

const RelatedMatchesGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: ${spacing.md};
`

const RelatedMatchCard = styled(Link)`
  background: ${color.background};
  border: 1px solid ${color.border};
  border-radius: ${radius.sm};
  padding: ${spacing.md};
  cursor: pointer;
  display: block;
  color: inherit;
  text-decoration: none;

  &:hover {
    border-color: ${color.primary};
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    color: inherit;
    text-decoration: none;
  }
`

const RelatedMatchHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${spacing.sm};
`

const RelatedMatchCode = styled.span`
  font-weight: 600;
  color: ${color.primary};
`

const RelatedMatchInfo = styled.div`
  font-size: 13px;
  color: ${color.textLight};
`

type DossieData = {
  match: {
    id: number
    codigo: string
    etapa_do_funil: string
    is_bilateral: boolean
    observacoes: string
    criado_em: string
    atualizado_em: string
    criado_por: string
  }
  tipo_match: string
  criterios_validacao?: {
    a_oferece: string
    a_aceita: string[]
    b_oferece: string
    b_aceita: string[]
    a_aceita_b: boolean
    b_aceita_a: boolean
    match_valido: boolean
  }
  parte_a: {
    tipo: string
    id: number
    ref?: string
    codigo?: string
    tipo_nome: string | null
    endereco: string | null
    bairro: string | null
    cidade: string | null
    estado: string | null
    cep?: string | null
    area: number | null
    valor: number | null
    zona: string | null
    quartos?: number | null
    suites?: number | null
    banheiros?: number | null
    vagas?: number | null
    descricao?: string | null
    condominio?: string | null
    marca?: string
    modelo?: string
    ano?: number
    km?: number
    cliente: {
      id: number | null
      nome: string | null
      telefone: string | null
      email: string | null
    }
    corretor: string | null
    interesses: Array<{
      tipo: string
      tipo_aceito: string
      zona_aceita?: string
      valor_minimo: number | null
      valor_maximo: number | null
    }>
  }
  parte_b: {
    tipo: string
    id: number
    ref?: string
    codigo?: string
    tipo_nome: string | null
    endereco: string | null
    bairro: string | null
    cidade: string | null
    estado: string | null
    cep?: string | null
    area: number | null
    valor: number | null
    zona: string | null
    quartos?: number | null
    suites?: number | null
    banheiros?: number | null
    vagas?: number | null
    descricao?: string | null
    condominio?: string | null
    marca?: string
    modelo?: string
    ano?: number
    km?: number
    cliente: {
      id: number | null
      nome: string | null
      telefone: string | null
      email: string | null
    }
    corretor: string | null
    interesses: Array<{
      tipo: string
      tipo_aceito: string
      zona_aceita?: string
      valor_minimo: number | null
      valor_maximo: number | null
    }>
  }
  analise_financeira: {
    valor_parte_a: number
    valor_parte_b: number
    diferenca: number
    quem_complementa: string | null
  }
  matches_relacionados?: {
    do_imovel: Array<{
      id: number
      codigo: string
      etapa_do_funil: string
      parte_b_tipo?: string
      parte_b_codigo?: string
      parte_b_valor?: number | null
    }>
    da_permuta: Array<{
      id: number
      codigo: string
      etapa_do_funil: string
      parte_a_tipo?: string
      parte_a_codigo?: string
      parte_a_valor?: number | null
    }>
  }
}

const etapaLabels: Record<string, string> = {
  novo: 'Novo Match',
  avaliacao: 'Avaliacao',
  negociacao: 'Negociacao',
  fechado: 'Fechado',
  rejeitado: 'Rejeitado',
}

const MatchDossie: React.FC = () => {
  const { matchId } = useParams<{ matchId: string }>()
  const navigate = useNavigate()
  const { user } = useContext(AuthContext)
  const api = useAxios()

  const [dossie, setDossie] = useState<DossieData | null>(null)
  const [loading, setLoading] = useState(true)
  const [novaObservacao, setNovaObservacao] = useState('')
  const [salvandoObs, setSalvandoObs] = useState(false)
  const [avanncando, setAvancando] = useState(false)

  const fetchDossie = async () => {
    if (!user || !matchId) return
    try {
      const response = await api.get(`/permuta/match/${matchId}/dossie/`)
      setDossie(response.data)
    } catch (error) {
      console.error('Erro ao carregar dossie:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDossie()
  }, [user, matchId])

  const handleAdicionarObservacao = async () => {
    if (!novaObservacao.trim()) return
    setSalvandoObs(true)
    try {
      const response = await api.post(`/permuta/match/${matchId}/adicionar_observacao/`, {
        observacao: novaObservacao,
      })
      if (dossie) {
        setDossie({
          ...dossie,
          match: { ...dossie.match, observacoes: response.data.observacoes }
        })
      }
      setNovaObservacao('')
    } catch (error) {
      console.error('Erro ao adicionar observacao:', error)
    } finally {
      setSalvandoObs(false)
    }
  }

  const handleAvancarEtapa = async () => {
    if (!confirm('Deseja avancar para a proxima etapa?')) return
    setAvancando(true)
    try {
      const response = await api.post(`/permuta/match/${matchId}/avancar_etapa/`)
      if (dossie && response.data.status === 'ok') {
        setDossie({
          ...dossie,
          match: { ...dossie.match, etapa_do_funil: response.data.nova_etapa }
        })
      }
    } catch (error) {
      console.error('Erro ao avancar etapa:', error)
    } finally {
      setAvancando(false)
    }
  }

  const handleRejeitar = async () => {
    if (!confirm('Deseja rejeitar este match? Ele será movido para a lista de rejeitados e poderá ser recuperado depois.')) return

    try {
      await api.post(`/permuta/match/${matchId}/rejeitar/`)
      alert('Match rejeitado com sucesso. Você pode recuperá-lo na lista de rejeitados.')
      navigate('/matches')
    } catch (error) {
      console.error('Erro ao rejeitar match:', error)
    }
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  }

  const getParteLabel = (parte: DossieData['parte_a'] | DossieData['parte_b']) => {
    if (parte.tipo === 'imovel') return `Imovel ${parte.ref || ''}`
    if (parte.tipo === 'permuta_imovel') return `Permuta Imovel ${parte.codigo || ''}`
    if (parte.tipo === 'permuta_automovel') return `Veiculo ${parte.codigo || ''}`
    return 'Item'
  }

  const navigateToImovel = (id: number) => {
    navigate(`/imoveis/${id}`)
  }

  const navigateToPermuta = (tipo: string, id: number) => {
    if (tipo === 'permuta_imovel') {
      navigate(`/permutas/imoveis/${id}`)
    } else if (tipo === 'permuta_automovel') {
      navigate(`/permutas/automoveis/${id}`)
    }
  }

  const renderRelatedMatches = (): JSX.Element => {
    if (!dossie?.matches_relacionados) return <></>
    
    const { do_imovel, da_permuta } = dossie.matches_relacionados
    if (do_imovel.length === 0 && da_permuta.length === 0) return <></>

    return (
      <Section>
        <SectionHeader>Matches Relacionados</SectionHeader>
        <SectionBody>
          {do_imovel.length > 0 && (
            <>
              <div style={{ fontWeight: 600, marginBottom: spacing.md, color: color.primary }}>
                Outros matches do imovel {dossie.parte_a.ref}:
              </div>
              <RelatedMatchesGrid>
                {do_imovel.map((m) => (
                  <RelatedMatchCard key={m.id} to={`/matches/${m.id}`}>
                    <RelatedMatchHeader>
                      <RelatedMatchCode>{m.codigo}</RelatedMatchCode>
                      <Badge $type={m.etapa_do_funil}>{etapaLabels[m.etapa_do_funil]}</Badge>
                    </RelatedMatchHeader>
                    <RelatedMatchInfo>
                      Com: {m.parte_b_tipo === 'permuta_imovel' ? 'Permuta' : m.parte_b_tipo === 'permuta_automovel' ? 'Veiculo' : 'Imovel'} {m.parte_b_codigo}
                    </RelatedMatchInfo>
                    {m.parte_b_valor && (
                      <RelatedMatchInfo>
                        Valor: {formatCurrency(m.parte_b_valor)}
                      </RelatedMatchInfo>
                    )}
                  </RelatedMatchCard>
                ))}
              </RelatedMatchesGrid>
            </>
          )}

          {da_permuta.length > 0 && (
            <>
              <div style={{ fontWeight: 600, marginBottom: spacing.md, marginTop: do_imovel.length > 0 ? spacing.xl : 0, color: color.primary }}>
                Outros matches da permuta {dossie.parte_b.codigo}:
              </div>
              <RelatedMatchesGrid>
                {da_permuta.map((m) => (
                  <RelatedMatchCard key={m.id} to={`/matches/${m.id}`}>
                    <RelatedMatchHeader>
                      <RelatedMatchCode>{m.codigo}</RelatedMatchCode>
                      <Badge $type={m.etapa_do_funil}>{etapaLabels[m.etapa_do_funil]}</Badge>
                    </RelatedMatchHeader>
                    <RelatedMatchInfo>
                      Com: Imovel {m.parte_a_codigo}
                    </RelatedMatchInfo>
                    {m.parte_a_valor && (
                      <RelatedMatchInfo>
                        Valor: {formatCurrency(m.parte_a_valor)}
                      </RelatedMatchInfo>
                    )}
                  </RelatedMatchCard>
                ))}
              </RelatedMatchesGrid>
            </>
          )}
        </SectionBody>
      </Section>
    )
  }

  if (loading) {
    return (
      <Container>
        <LoadingContainer>
          <Spinner size={40} />
        </LoadingContainer>
      </Container>
    )
  }

  if (!dossie) {
    return (
      <Container>
        <PageHeader>
          <HeaderLeft>
            <BackButton onClick={() => navigate('/matches')}>Voltar</BackButton>
            <PageTitle>Match nao encontrado</PageTitle>
          </HeaderLeft>
        </PageHeader>
      </Container>
    )
  }

  const { match, parte_a, parte_b, analise_financeira } = dossie

  return (
    <Container>
      <PageHeader>
        <HeaderLeft>
          <BackButton onClick={() => navigate('/matches')}>Voltar</BackButton>
          <PageTitle>{match.codigo}</PageTitle>
          <Badge $type={match.etapa_do_funil}>{etapaLabels[match.etapa_do_funil]}</Badge>
          {match.is_bilateral && <Badge $type="bilateral">Bilateral</Badge>}
        </HeaderLeft>
        <HeaderActions>
          {match.etapa_do_funil !== 'fechado' && (
            <ActionButton $variant="success" onClick={handleAvancarEtapa} disabled={avanncando}>
              {avanncando ? 'Avancando...' : 'Avancar Etapa'}
            </ActionButton>
          )}
          <ActionButton $variant="danger" onClick={handleRejeitar}>
            Rejeitar
          </ActionButton>
        </HeaderActions>
      </PageHeader>

      <MatchCriteriaBox>
        <div style={{ fontWeight: 600, marginBottom: spacing.md, color: color.primary }}>
          Criterios do Match
        </div>
        <CriteriaText>
          <strong>PARTE A oferece:</strong> {dossie.criterios_validacao?.a_oferece || parte_a.tipo_nome || 'Item'} ({getParteLabel(parte_a)})
        </CriteriaText>
        <CriteriaText>
          <strong>PARTE A aceita:</strong> {dossie.criterios_validacao?.a_aceita?.join(', ') || parte_a.interesses?.map(i => i.tipo_aceito).join(', ') || 'Nao especificado'}
        </CriteriaText>
        <MatchArrow>&#8645;</MatchArrow>
        <CriteriaText>
          <strong>PARTE B oferece:</strong> {dossie.criterios_validacao?.b_oferece || parte_b.tipo_nome || 'Item'} ({getParteLabel(parte_b)})
        </CriteriaText>
        <CriteriaText>
          <strong>PARTE B aceita:</strong> {dossie.criterios_validacao?.b_aceita?.join(', ') || parte_b.interesses?.map(i => i.tipo_aceito).join(', ') || 'Nao especificado'}
        </CriteriaText>
        
        <div style={{ marginTop: spacing.md, display: 'flex', flexDirection: 'column', gap: spacing.xs }}>
          <div style={{ color: dossie.criterios_validacao?.a_aceita_b ? color.success : color.danger }}>
            {dossie.criterios_validacao?.a_aceita_b ? '✓' : '✗'} A aceita B: {dossie.criterios_validacao?.a_aceita_b ? 'Sim' : 'Nao'}
          </div>
          <div style={{ color: dossie.criterios_validacao?.b_aceita_a ? color.success : color.danger }}>
            {dossie.criterios_validacao?.b_aceita_a ? '✓' : '✗'} B aceita A: {dossie.criterios_validacao?.b_aceita_a ? 'Sim' : 'Nao'}
          </div>
        </div>
        
        {dossie.criterios_validacao?.match_valido && (
          <MatchCheck>Match bilateral confirmado</MatchCheck>
        )}
      </MatchCriteriaBox>

      <Grid>
        <Section>
          <SectionHeader $color="#6c5ce7">
            <span>PARTE A - {parte_a.tipo === 'imovel' ? (
              <RefLink onClick={() => navigateToImovel(parte_a.id)}>
                Imovel {parte_a.ref}
              </RefLink>
            ) : getParteLabel(parte_a)}</span>
          </SectionHeader>
          <SectionBody>
            <ClientCard>
              <ClientName>{parte_a.cliente?.nome || 'Proprietario nao informado'}</ClientName>
              <ContactInfo>
                {parte_a.cliente?.telefone && <span>Tel: {parte_a.cliente.telefone}</span>}
                {parte_a.cliente?.email && <span>Email: {parte_a.cliente.email}</span>}
                {parte_a.corretor && <span>Corretor: {parte_a.corretor}</span>}
              </ContactInfo>
            </ClientCard>

            <InfoRow>
              <InfoLabel>Tipo</InfoLabel>
              <InfoValue>{parte_a.tipo_nome || '-'}</InfoValue>
            </InfoRow>
            {parte_a.endereco && (
              <InfoRow>
                <InfoLabel>Endereco</InfoLabel>
                <InfoValue>{parte_a.endereco}</InfoValue>
              </InfoRow>
            )}
            {(parte_a.cidade || parte_a.estado) && (
              <InfoRow>
                <InfoLabel>Cidade/UF</InfoLabel>
                <InfoValue>{parte_a.cidade} / {parte_a.estado}</InfoValue>
              </InfoRow>
            )}
            {parte_a.zona && (
              <InfoRow>
                <InfoLabel>Zona</InfoLabel>
                <InfoValue>{parte_a.zona}</InfoValue>
              </InfoRow>
            )}
            {parte_a.area && (
              <InfoRow>
                <InfoLabel>Area</InfoLabel>
                <InfoValue>{parte_a.area} m2</InfoValue>
              </InfoRow>
            )}
            {(parte_a.quartos || parte_a.suites || parte_a.banheiros) && (
              <InfoRow>
                <InfoLabel>Comodos</InfoLabel>
                <InfoValue>
                  {parte_a.quartos && `${parte_a.quartos}q`}
                  {parte_a.suites && ` ${parte_a.suites}s`}
                  {parte_a.banheiros && ` ${parte_a.banheiros}b`}
                  {parte_a.vagas && ` ${parte_a.vagas}v`}
                </InfoValue>
              </InfoRow>
            )}
            {parte_a.marca && (
              <InfoRow>
                <InfoLabel>Veiculo</InfoLabel>
                <InfoValue>{parte_a.marca} {parte_a.modelo} ({parte_a.ano})</InfoValue>
              </InfoRow>
            )}
            <InfoRow>
              <InfoLabel>Valor</InfoLabel>
              <InfoValue style={{ color: color.success, fontWeight: 600 }}>
                {formatCurrency(parte_a.valor)}
              </InfoValue>
            </InfoRow>

            {parte_a.interesses && parte_a.interesses.length > 0 && (
              <InterestsBox>
                <div style={{ fontWeight: 600, marginBottom: spacing.sm, fontSize: 13 }}>
                  Interesses de Permuta:
                </div>
                {parte_a.interesses.map((interesse, idx) => (
                  <InterestItem key={idx}>
                    Aceita: {interesse.tipo_aceito}
                    {interesse.zona_aceita && ` - ${interesse.zona_aceita}`}
                    {(interesse.valor_minimo || interesse.valor_maximo) && (
                      <span style={{ color: color.textLight }}>
                        {' '}({formatCurrency(interesse.valor_minimo)} - {formatCurrency(interesse.valor_maximo)})
                      </span>
                    )}
                  </InterestItem>
                ))}
              </InterestsBox>
            )}
          </SectionBody>
        </Section>

        <Section>
          <SectionHeader $color="#00b894">
            <span>PARTE B - {parte_b.tipo === 'imovel' ? (
              <RefLink onClick={() => navigateToImovel(parte_b.id)}>
                Imovel {parte_b.ref}
              </RefLink>
            ) : (parte_b.tipo === 'permuta_imovel' || parte_b.tipo === 'permuta_automovel') ? (
              <RefLink onClick={() => navigateToPermuta(parte_b.tipo, parte_b.id)}>
                {parte_b.tipo === 'permuta_imovel' ? `Permuta Imovel ${parte_b.codigo}` : `Veiculo ${parte_b.codigo}`}
              </RefLink>
            ) : getParteLabel(parte_b)}</span>
          </SectionHeader>
          <SectionBody>
            <ClientCard>
              <ClientName>{parte_b.cliente?.nome || 'Proprietario nao informado'}</ClientName>
              <ContactInfo>
                {parte_b.cliente?.telefone && <span>Tel: {parte_b.cliente.telefone}</span>}
                {parte_b.cliente?.email && <span>Email: {parte_b.cliente.email}</span>}
                {parte_b.corretor && <span>Corretor: {parte_b.corretor}</span>}
              </ContactInfo>
            </ClientCard>

            <InfoRow>
              <InfoLabel>Tipo</InfoLabel>
              <InfoValue>{parte_b.tipo_nome || '-'}</InfoValue>
            </InfoRow>
            {parte_b.endereco && (
              <InfoRow>
                <InfoLabel>Endereco</InfoLabel>
                <InfoValue>{parte_b.endereco}</InfoValue>
              </InfoRow>
            )}
            {(parte_b.cidade || parte_b.estado) && (
              <InfoRow>
                <InfoLabel>Cidade/UF</InfoLabel>
                <InfoValue>{parte_b.cidade} / {parte_b.estado}</InfoValue>
              </InfoRow>
            )}
            {parte_b.zona && (
              <InfoRow>
                <InfoLabel>Zona</InfoLabel>
                <InfoValue>{parte_b.zona}</InfoValue>
              </InfoRow>
            )}
            {parte_b.area && (
              <InfoRow>
                <InfoLabel>Area</InfoLabel>
                <InfoValue>{parte_b.area} m2</InfoValue>
              </InfoRow>
            )}
            {(parte_b.quartos || parte_b.suites || parte_b.banheiros) && (
              <InfoRow>
                <InfoLabel>Comodos</InfoLabel>
                <InfoValue>
                  {parte_b.quartos && `${parte_b.quartos}q`}
                  {parte_b.suites && ` ${parte_b.suites}s`}
                  {parte_b.banheiros && ` ${parte_b.banheiros}b`}
                  {parte_b.vagas && ` ${parte_b.vagas}v`}
                </InfoValue>
              </InfoRow>
            )}
            {parte_b.marca && (
              <InfoRow>
                <InfoLabel>Veiculo</InfoLabel>
                <InfoValue>{parte_b.marca} {parte_b.modelo} ({parte_b.ano})</InfoValue>
              </InfoRow>
            )}
            <InfoRow>
              <InfoLabel>Valor</InfoLabel>
              <InfoValue style={{ color: color.success, fontWeight: 600 }}>
                {formatCurrency(parte_b.valor)}
              </InfoValue>
            </InfoRow>

            {parte_b.interesses && parte_b.interesses.length > 0 && (
              <InterestsBox>
                <div style={{ fontWeight: 600, marginBottom: spacing.sm, fontSize: 13 }}>
                  Interesses de Permuta:
                </div>
                {parte_b.interesses.map((interesse, idx) => (
                  <InterestItem key={idx}>
                    Aceita: {interesse.tipo_aceito}
                    {interesse.zona_aceita && ` - ${interesse.zona_aceita}`}
                    {(interesse.valor_minimo || interesse.valor_maximo) && (
                      <span style={{ color: color.textLight }}>
                        {' '}({formatCurrency(interesse.valor_minimo)} - {formatCurrency(interesse.valor_maximo)})
                      </span>
                    )}
                  </InterestItem>
                ))}
              </InterestsBox>
            )}
          </SectionBody>
        </Section>
      </Grid>

      <Section>
        <SectionHeader>Analise Financeira</SectionHeader>
        <SectionBody>
          <FinancialBox>
            <FinancialRow>
              <span>Valor Parte A:</span>
              <span>{formatCurrency(analise_financeira.valor_parte_a)}</span>
            </FinancialRow>
            <FinancialRow>
              <span>Valor Parte B:</span>
              <span>{formatCurrency(analise_financeira.valor_parte_b)}</span>
            </FinancialRow>
            <FinancialTotal>
              <span>Diferenca (Torna):</span>
              <span>{formatCurrency(analise_financeira.diferenca)}</span>
            </FinancialTotal>
            {analise_financeira.quem_complementa && analise_financeira.diferenca > 0 && (
              <div style={{ textAlign: 'center', marginTop: spacing.md, color: color.textLight, fontSize: 14 }}>
                Parte {analise_financeira.quem_complementa} precisaria complementar {formatCurrency(analise_financeira.diferenca)}
              </div>
            )}
          </FinancialBox>
        </SectionBody>
      </Section>

      <Section>
        <SectionHeader>Informacoes do Match</SectionHeader>
        <SectionBody>
          <InfoRow>
            <InfoLabel>Criado em</InfoLabel>
            <InfoValue>{formatDate(match.criado_em)}</InfoValue>
          </InfoRow>
          <InfoRow>
            <InfoLabel>Atualizado em</InfoLabel>
            <InfoValue>{formatDate(match.atualizado_em)}</InfoValue>
          </InfoRow>
          <InfoRow>
            <InfoLabel>Criado por</InfoLabel>
            <InfoValue>{match.criado_por || '-'}</InfoValue>
          </InfoRow>
        </SectionBody>
      </Section>

      <Section>
        <SectionHeader>Observacoes</SectionHeader>
        <SectionBody>
          {match.observacoes && (
            <ObservacaoDisplay>{match.observacoes}</ObservacaoDisplay>
          )}
          <ObservacaoForm>
            <TextArea
              placeholder="Adicionar uma observacao..."
              value={novaObservacao}
              onChange={(e) => setNovaObservacao(e.target.value)}
            />
            <ActionButton
              style={{ marginTop: spacing.sm }}
              onClick={handleAdicionarObservacao}
              disabled={salvandoObs || !novaObservacao.trim()}
            >
              {salvandoObs ? 'Salvando...' : 'Adicionar Observacao'}
            </ActionButton>
          </ObservacaoForm>
        </SectionBody>
      </Section>

      {renderRelatedMatches()}
    </Container>
  )
}

export default MatchDossie
