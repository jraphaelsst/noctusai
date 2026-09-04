import React, { useState, useEffect, useContext, DragEvent } from 'react'
import { formatCurrency } from '../../utils/formatCurrency'
import { useNavigate } from 'react-router-dom'
import styled from 'styled-components'
import Container from '../../containers/Container'
import { color, spacing, radius } from '../../styles'
import useAxios from '../../utils/useAxios'
import AuthContext from '../../context/AuthContext'

const PageHeader = styled.div`
  background: ${color.primary};
  border-radius: ${radius.sm};
  padding: ${spacing.xl};
  margin-bottom: ${spacing.xl};
  color: ${color.textInverse};
  display: flex;
  justify-content: space-between;
  align-items: center;
`

const PageTitle = styled.h1`
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
  color: ${color.textInverse};
`

const SyncButton = styled.button`
  background: ${color.cardBg};
  color: ${color.primary};
  border: none;
  padding: ${spacing.sm} ${spacing.lg};
  border-radius: ${radius.sm};
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: ${color.background};
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`

const KanbanBoard = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: ${spacing.md};
  min-height: 70vh;

  @media (max-width: 1200px) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`

const KanbanColumn = styled.div<{ $isOver?: boolean }>`
  background: ${props => props.$isOver ? 'rgba(45, 52, 54, 0.08)' : color.background};
  border-radius: ${radius.sm};
  border: 1px solid ${props => props.$isOver ? color.primary : color.border};
  display: flex;
  flex-direction: column;
  min-height: 400px;
  transition: all 0.2s;
`

const ColumnHeader = styled.div<{ $color: string }>`
  background: ${props => props.$color};
  color: white;
  padding: ${spacing.md} ${spacing.lg};
  border-radius: ${radius.sm} ${radius.sm} 0 0;
  font-weight: 600;
  font-size: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
`

const ColumnCount = styled.span`
  background: rgba(255, 255, 255, 0.2);
  padding: ${spacing.xs} ${spacing.sm};
  border-radius: ${radius.full};
  font-size: 12px;
`

const ColumnBody = styled.div`
  flex: 1;
  padding: ${spacing.sm};
  overflow-y: auto;
  min-height: 100px;
  max-height: 85vh;
`

const MatchCardWrapper = styled.div<{ $isDragging?: boolean }>`
  background: ${color.cardBg};
  border-radius: ${radius.sm};
  border: 1px solid ${color.border};
  margin-bottom: ${spacing.sm};
  cursor: grab;
  transition: all 0.2s;
  opacity: ${props => props.$isDragging ? 0.5 : 1};

  &:hover {
    border-color: ${color.primary};
    box-shadow: 0 2px 8px ${color.shadow};
  }

  &:active {
    cursor: grabbing;
  }
`

const CardHeader = styled.div`
  padding: ${spacing.sm} ${spacing.md};
  border-bottom: 1px solid ${color.border};
  display: flex;
  justify-content: space-between;
  align-items: center;
`

const CardCode = styled.span`
  font-weight: 600;
  font-size: 13px;
  color: ${color.primary};
`

const CardBadge = styled.span<{ $type: 'imovel' | 'automovel' }>`
  background: ${props => props.$type === 'imovel' ? color.success : color.warning};
  color: white;
  padding: 2px ${spacing.sm};
  border-radius: ${radius.sm};
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
`

const CardBody = styled.div`
  padding: ${spacing.md};
`

const CardRow = styled.div`
  display: flex;
  justify-content: space-between;
  margin-bottom: ${spacing.xs};
  font-size: 12px;

  &:last-child {
    margin-bottom: 0;
  }
`

const CardLabel = styled.span`
  color: ${color.textLight};
`

const CardValue = styled.span`
  color: ${color.text};
  font-weight: 500;
`

const CardPrice = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: ${color.primary};
  margin-top: ${spacing.sm};
`

const EmptyColumn = styled.div`
  text-align: center;
  padding: ${spacing.xl};
  color: ${color.textLight};
  font-size: 13px;
`

const RejeitadosSection = styled.div`
  margin-top: ${spacing.xl};
`

const RejeitadosHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${spacing.md} ${spacing.lg};
  background: ${color.danger};
  border-radius: ${radius.sm};
  cursor: pointer;
  color: white;
  font-weight: 600;
  font-size: 14px;

  &:hover {
    opacity: 0.9;
  }
`

const RejeitadosCount = styled.span`
  background: rgba(255, 255, 255, 0.2);
  padding: ${spacing.xs} ${spacing.sm};
  border-radius: ${radius.full};
  font-size: 12px;
`

const RejeitadosList = styled.div`
  margin-top: ${spacing.md};
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: ${spacing.md};
`

const RejeitadoCard = styled.div`
  background: ${color.cardBg};
  border: 1px solid ${color.border};
  border-radius: ${radius.sm};
  border-left: 3px solid ${color.danger};
`

const RejeitadoCardBody = styled.div`
  padding: ${spacing.md};
`

const RejeitadoCardFooter = styled.div`
  padding: ${spacing.sm} ${spacing.md};
  border-top: 1px solid ${color.border};
  display: flex;
  justify-content: space-between;
  align-items: center;
`

const RecuperarButton = styled.button`
  background: ${color.success};
  color: white;
  border: none;
  padding: ${spacing.xs} ${spacing.md};
  border-radius: ${radius.sm};
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;

  &:hover {
    opacity: 0.9;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`

const VerDossieButton = styled.button`
  background: transparent;
  color: ${color.primary};
  border: 1px solid ${color.border};
  padding: ${spacing.xs} ${spacing.md};
  border-radius: ${radius.sm};
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;

  &:hover {
    background: ${color.background};
  }
`

const LoadingState = styled.div`
  text-align: center;
  padding: ${spacing.xxl};
  color: ${color.textLight};
`

const Spinner = styled.div`
  width: 40px;
  height: 40px;
  border: 3px solid ${color.border};
  border-top-color: ${color.primary};
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto ${spacing.md};

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
`

type MatchType = {
  id: number
  codigo: string
  etapa_do_funil: string
  ordem: number
  imovel: number
  imovel_ref: string
  imovel_tipo: string
  imovel_valor: number
  imovel_corretor: string
  imovel_match: number | null
  imovel_match_ref: string | null
  imovel_match_tipo: string | null
  imovel_match_valor: number | null
  imovel_match_corretor: string | null
  imovel_match_condominio: string | null
  imovel_match_proprietario: string | null
  permuta_imovel: number | null
  permuta_imovel_codigo: string | null
  permuta_imovel_tipo: string | null
  permuta_imovel_valor: number | null
  permuta_imovel_cidade: string | null
  permuta_imovel_estado: string | null
  permuta_imovel_proprietario: string | null
  permuta_automovel: number | null
  permuta_automovel_codigo: string | null
  permuta_automovel_tipo: string | null
  permuta_automovel_valor: number | null
  permuta_automovel_marca: string | null
  permuta_automovel_modelo: string | null
  permuta_automovel_proprietario: string | null
}

const COLUMNS = [
  { id: 'novo', title: 'Novo Match', color: '#6c5ce7' },
  { id: 'avaliacao', title: 'Avaliação', color: '#00b894' },
  { id: 'negociacao', title: 'Negociação', color: '#fdcb6e' },
  { id: 'fechado', title: 'Fechado', color: '#2d3436' },
]

interface MatchCardProps {
  match: MatchType
  onDragStart: (e: DragEvent<HTMLDivElement>, matchId: number) => void
  onDragOver: (e: DragEvent<HTMLDivElement>) => void
  onDrop: (e: DragEvent<HTMLDivElement>, targetMatchId: number) => void
  onClick: () => void
  isDraggedOver: boolean
}

const MatchCard: React.FC<MatchCardProps> = ({ match, onDragStart, onDragOver, onDrop, onClick, isDraggedOver }) => {
  const isPermutaImovelMatch = match.permuta_imovel !== null
  const isImovelMatch = match.imovel_match !== null
  const isAutomovelMatch = match.permuta_automovel !== null

  const getMatchType = () => {
    if (isImovelMatch) return 'Imóvel x Imóvel'
    if (isPermutaImovelMatch) return 'Imóvel x Permuta'
    return 'Automóvel'
  }

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    onClick()
  }

  return (
    <MatchCardWrapper
      draggable
      onDragStart={(e) => onDragStart(e, match.id)}
      onDragOver={onDragOver}
      onDrop={(e) => onDrop(e, match.id)}
      onClick={handleClick}
      style={{ opacity: isDraggedOver ? 0.5 : 1, borderTop: isDraggedOver ? '3px solid #6c5ce7' : 'none' }}
    >
      <CardHeader>
        <CardCode>{match.codigo}</CardCode>
        <CardBadge $type={isAutomovelMatch ? 'automovel' : 'imovel'}>
          {getMatchType()}
        </CardBadge>
      </CardHeader>
      <CardBody>
        <CardRow>
          <CardLabel>Imóvel:</CardLabel>
          <CardValue>{match.imovel_ref}</CardValue>
        </CardRow>
        <CardRow>
          <CardLabel>Tipo:</CardLabel>
          <CardValue>{match.imovel_tipo || '-'}</CardValue>
        </CardRow>
        {isImovelMatch ? (
          <>
            <CardRow>
              <CardLabel>Match:</CardLabel>
              <CardValue>{match.imovel_match_ref} - {match.imovel_match_tipo || '-'}</CardValue>
            </CardRow>
            <CardRow>
              <CardLabel>Condomínio:</CardLabel>
              <CardValue>{match.imovel_match_condominio || '-'}</CardValue>
            </CardRow>
            <CardRow>
              <CardLabel>Proprietário:</CardLabel>
              <CardValue>{match.imovel_match_proprietario || '-'}</CardValue>
            </CardRow>
            <CardPrice>{formatCurrency(match.imovel_match_valor)}</CardPrice>
          </>
        ) : isPermutaImovelMatch ? (
          <>
            <CardRow>
              <CardLabel>Permuta:</CardLabel>
              <CardValue>{match.permuta_imovel_codigo} - {match.permuta_imovel_tipo || '-'}</CardValue>
            </CardRow>
            <CardRow>
              <CardLabel>Local:</CardLabel>
              <CardValue>{match.permuta_imovel_cidade}/{match.permuta_imovel_estado}</CardValue>
            </CardRow>
            <CardRow>
              <CardLabel>Proprietário:</CardLabel>
              <CardValue>{match.permuta_imovel_proprietario}</CardValue>
            </CardRow>
            <CardPrice>{formatCurrency(match.permuta_imovel_valor)}</CardPrice>
          </>
        ) : (
          <>
            <CardRow>
              <CardLabel>Veículo:</CardLabel>
              <CardValue>{match.permuta_automovel_codigo} - {match.permuta_automovel_tipo || '-'}</CardValue>
            </CardRow>
            <CardRow>
              <CardLabel>Modelo:</CardLabel>
              <CardValue>{match.permuta_automovel_marca} {match.permuta_automovel_modelo}</CardValue>
            </CardRow>
            <CardRow>
              <CardLabel>Proprietário:</CardLabel>
              <CardValue>{match.permuta_automovel_proprietario}</CardValue>
            </CardRow>
            <CardPrice>{formatCurrency(match.permuta_automovel_valor)}</CardPrice>
          </>
        )}
      </CardBody>
    </MatchCardWrapper>
  )
}

const Matches: React.FC = () => {
  const [matches, setMatches] = useState<MatchType[]>([])
  const [rejeitados, setRejeitados] = useState<MatchType[]>([])
  const [showRejeitados, setShowRejeitados] = useState(false)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [recuperando, setRecuperando] = useState<number | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null)
  const [dragOverMatchId, setDragOverMatchId] = useState<number | null>(null)
  const { user } = useContext(AuthContext)
  const api = useAxios()
  const navigate = useNavigate()

  const fetchMatches = async () => {
    if (!user) return
    try {
      const response = await api.get('/permuta/match/')
      const data = response.data
      if (data.results) {
        setMatches(data.results)
      } else {
        setMatches(Array.isArray(data) ? data : [])
      }
    } catch (error) {
      console.error('Error fetching matches:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchRejeitados = async () => {
    if (!user) return
    try {
      const response = await api.get('/permuta/match/?etapa=rejeitado')
      const data = response.data
      if (data.results) {
        setRejeitados(data.results)
      } else {
        setRejeitados(Array.isArray(data) ? data : [])
      }
    } catch (error) {
      console.error('Error fetching rejected matches:', error)
    }
  }

  const handleRecuperar = async (matchId: number) => {
    if (!confirm('Deseja recuperar este match? Ele voltará para a etapa "Novo Match".')) return
    setRecuperando(matchId)
    try {
      await api.post(`/permuta/match/${matchId}/recuperar/`)
      await fetchMatches()
      await fetchRejeitados()
    } catch (error) {
      console.error('Error recovering match:', error)
      alert('Erro ao recuperar match.')
    } finally {
      setRecuperando(null)
    }
  }

  useEffect(() => {
    fetchMatches()
    fetchRejeitados()
  }, [user])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const response = await api.post('/permuta/match/sync/')
      const data = response.data
      
      if (data.status === 'warning') {
        alert(data.message)
      } else if (data.created > 0) {
        alert(`${data.created} matches bilaterais criados!`)
      } else {
        alert('Sincronização concluída. Nenhum novo match bilateral encontrado.')
      }
      
      await fetchMatches()
    } catch (error) {
      console.error('Error syncing matches:', error)
      alert('Erro ao sincronizar matches. Tente novamente.')
    } finally {
      setSyncing(false)
    }
  }

  const [draggedMatchId, setDraggedMatchId] = useState<number | null>(null)

  const handleDragStart = (e: DragEvent<HTMLDivElement>, matchId: number) => {
    e.dataTransfer.setData('matchId', matchId.toString())
    e.dataTransfer.effectAllowed = 'move'
    setDraggedMatchId(matchId)
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDragEnter = (e: DragEvent<HTMLDivElement>, columnId: string) => {
    e.preventDefault()
    setDragOverColumn(columnId)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    const relatedTarget = e.relatedTarget as Node
    const currentTarget = e.currentTarget as Node
    if (!currentTarget.contains(relatedTarget)) {
      setDragOverColumn(null)
    }
  }

  const handleCardDragOver = (e: DragEvent<HTMLDivElement>, matchId: number) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOverMatchId(matchId)
  }

  const handleCardDrop = async (e: DragEvent<HTMLDivElement>, targetMatchId: number) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOverMatchId(null)
    setDragOverColumn(null)
    
    const draggedIdStr = e.dataTransfer.getData('matchId')
    if (!draggedIdStr) return
    
    const draggedId = parseInt(draggedIdStr, 10)
    if (draggedId === targetMatchId) return
    
    const draggedMatch = matches.find(m => m.id === draggedId)
    const targetMatch = matches.find(m => m.id === targetMatchId)
    
    if (!draggedMatch || !targetMatch) return
    
    const targetEtapa = targetMatch.etapa_do_funil
    const columnMatches = matches
      .filter(m => m.etapa_do_funil === targetEtapa)
      .sort((a, b) => a.ordem - b.ordem)
    
    const targetIndex = columnMatches.findIndex(m => m.id === targetMatchId)
    const newColumnMatches = columnMatches.filter(m => m.id !== draggedId)
    newColumnMatches.splice(targetIndex, 0, { ...draggedMatch, etapa_do_funil: targetEtapa })
    
    const updates = newColumnMatches.map((m, idx) => ({
      id: m.id,
      ordem: idx,
      etapa_do_funil: targetEtapa
    }))
    
    setMatches(prev => {
      const otherMatches = prev.filter(m => m.etapa_do_funil !== targetEtapa && m.id !== draggedId)
      const updatedColumnMatches = newColumnMatches.map((m, idx) => ({
        ...prev.find(pm => pm.id === m.id)!,
        ordem: idx,
        etapa_do_funil: targetEtapa
      }))
      return [...otherMatches, ...updatedColumnMatches]
    })
    
    try {
      await Promise.all(
        updates.map(u => 
          api.patch(`/permuta/match/${u.id}/`, { ordem: u.ordem, etapa_do_funil: u.etapa_do_funil })
        )
      )
    } catch (error) {
      console.error('Error updating order:', error)
      fetchMatches()
    }
    
    setDraggedMatchId(null)
  }

  const handleDrop = async (e: DragEvent<HTMLDivElement>, newEtapa: string) => {
    e.preventDefault()
    setDragOverColumn(null)
    setDragOverMatchId(null)
    
    const matchIdStr = e.dataTransfer.getData('matchId')
    if (!matchIdStr) return
    
    const matchId = parseInt(matchIdStr, 10)
    const match = matches.find(m => m.id === matchId)
    
    if (!match) return
    
    if (match.etapa_do_funil === newEtapa) {
      setDraggedMatchId(null)
      return
    }

    const columnMatches = matches
      .filter(m => m.etapa_do_funil === newEtapa)
      .sort((a, b) => a.ordem - b.ordem)
    const newOrdem = columnMatches.length > 0 ? Math.max(...columnMatches.map(m => m.ordem)) + 1 : 0

    setMatches(prev =>
      prev.map(m =>
        m.id === matchId ? { ...m, etapa_do_funil: newEtapa, ordem: newOrdem } : m
      )
    )

    try {
      await api.patch(`/permuta/match/${matchId}/`, {
        etapa_do_funil: newEtapa,
        ordem: newOrdem
      })
    } catch (error) {
      console.error('Error updating match:', error)
      setMatches(prev =>
        prev.map(m =>
          m.id === matchId ? { ...m, etapa_do_funil: match.etapa_do_funil, ordem: match.ordem } : m
        )
      )
    }
    
    setDraggedMatchId(null)
  }

  const getMatchesByEtapa = (etapa: string) => {
    return matches
      .filter(m => m.etapa_do_funil === etapa)
      .sort((a, b) => a.ordem - b.ordem)
  }

  if (loading) {
    return (
      <Container>
        <LoadingState>
          <Spinner />
        </LoadingState>
      </Container>
    )
  }

  return (
    <Container>
      <PageHeader>
        <PageTitle>Matches</PageTitle>
        <SyncButton onClick={handleSync} disabled={syncing}>
          {syncing ? 'Sincronizando...' : 'Sincronizar Matches'}
        </SyncButton>
      </PageHeader>

      <KanbanBoard>
        {COLUMNS.map(column => {
          const columnMatches = getMatchesByEtapa(column.id)
          return (
            <KanbanColumn
              key={column.id}
              $isOver={dragOverColumn === column.id}
              onDragOver={handleDragOver}
              onDragEnter={(e) => handleDragEnter(e, column.id)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, column.id)}
            >
              <ColumnHeader $color={column.color}>
                {column.title}
                <ColumnCount>{columnMatches.length}</ColumnCount>
              </ColumnHeader>
              <ColumnBody>
                {columnMatches.length > 0 ? (
                  columnMatches.map(match => (
                    <MatchCard
                      key={match.id}
                      match={match}
                      onDragStart={handleDragStart}
                      onDragOver={(e) => handleCardDragOver(e, match.id)}
                      onDrop={(e) => handleCardDrop(e, match.id)}
                      onClick={() => navigate(`/matches/${match.id}`)}
                      isDraggedOver={dragOverMatchId === match.id}
                    />
                  ))
                ) : (
                  <EmptyColumn>Nenhum match nesta etapa</EmptyColumn>
                )}
              </ColumnBody>
            </KanbanColumn>
          )
        })}
      </KanbanBoard>

      {rejeitados.length > 0 && (
        <RejeitadosSection>
          <RejeitadosHeader onClick={() => setShowRejeitados(!showRejeitados)}>
            <span>{showRejeitados ? '▼' : '▶'} Matches Rejeitados</span>
            <RejeitadosCount>{rejeitados.length}</RejeitadosCount>
          </RejeitadosHeader>
          {showRejeitados && (
            <RejeitadosList>
              {rejeitados.map(match => {
                const isPermutaImovelMatch = match.permuta_imovel !== null
                const isImovelMatch = match.imovel_match !== null
                const isAutomovelMatch = match.permuta_automovel !== null

                return (
                  <RejeitadoCard key={match.id}>
                    <RejeitadoCardBody>
                      <CardHeader>
                        <CardCode>{match.codigo}</CardCode>
                        <CardBadge $type={isAutomovelMatch ? 'automovel' : 'imovel'}>
                          {isImovelMatch ? 'Imóvel x Imóvel' : isPermutaImovelMatch ? 'Imóvel x Permuta' : 'Automóvel'}
                        </CardBadge>
                      </CardHeader>
                      <div style={{ marginTop: spacing.sm }}>
                        <CardRow>
                          <CardLabel>Imóvel:</CardLabel>
                          <CardValue>{match.imovel_ref}</CardValue>
                        </CardRow>
                        <CardRow>
                          <CardLabel>Tipo:</CardLabel>
                          <CardValue>{match.imovel_tipo || '-'}</CardValue>
                        </CardRow>
                        {isImovelMatch && (
                          <CardRow>
                            <CardLabel>Match:</CardLabel>
                            <CardValue>{match.imovel_match_ref} - {match.imovel_match_tipo || '-'}</CardValue>
                          </CardRow>
                        )}
                        {isPermutaImovelMatch && (
                          <CardRow>
                            <CardLabel>Permuta:</CardLabel>
                            <CardValue>{match.permuta_imovel_codigo} - {match.permuta_imovel_tipo || '-'}</CardValue>
                          </CardRow>
                        )}
                        {isAutomovelMatch && (
                          <CardRow>
                            <CardLabel>Veículo:</CardLabel>
                            <CardValue>{match.permuta_automovel_codigo} - {match.permuta_automovel_marca} {match.permuta_automovel_modelo}</CardValue>
                          </CardRow>
                        )}
                      </div>
                    </RejeitadoCardBody>
                    <RejeitadoCardFooter>
                      <VerDossieButton onClick={() => navigate(`/matches/${match.id}`)}>
                        Ver Dossiê
                      </VerDossieButton>
                      <RecuperarButton
                        onClick={() => handleRecuperar(match.id)}
                        disabled={recuperando === match.id}
                      >
                        {recuperando === match.id ? 'Recuperando...' : 'Recuperar'}
                      </RecuperarButton>
                    </RejeitadoCardFooter>
                  </RejeitadoCard>
                )
              })}
            </RejeitadosList>
          )}
        </RejeitadosSection>
      )}
    </Container>
  )
}

export default Matches
