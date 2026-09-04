import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import swal from 'sweetalert2'
import styled from 'styled-components'
import { color } from '../../../styles'

import {
  Container,
  Banner,
  Icon,
  Infos,
  Titulo,
  Tipo,
  InfoItem,
  Valor,
  Sections,
  TituloSecao,
  Card,
  CardGrid,
  ActionButtons,
  ActionButton,
  MatchesContainer,
  MatchSection,
  MatchSectionTitle,
  MatchCard,
  MatchBadge,
  MatchCardTitle,
  MatchCardDetail,
  MatchCardValue,
  EmptyMessage,
  InteresseSection,
  InteresseSectionHeader,
  InteresseTable,
  InteresseActions,
  AddButton
} from './styles'

import useAxios from '../../../utils/useAxios'
import { LoadingScreen } from '../../../components/Spinner'
import { EditIcon, DeleteIcon } from '../../../components/Icons'
import Modal from '../../../components/Modal'
import PermutaAutomovelEditForm from '../../../components/ModalForms/PermutaAutomovelEditForm'
import InteressePermutaAutomovelForm, { InteressePermutaAutomovelData } from '../../../components/ModalForms/InteressePermutaAutomovelForm'

type InteressePermutaAutomovelType = {
  id: number
  tipo_imovel: number | null
  tipo_imovel_nome: string | null
  zona: number | null
  zona_nome: string | null
  valor_minimo: number | null
  valor_maximo: number | null
}

const DeleteButton = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  color: ${color.danger};
  
  &:hover {
    opacity: 0.7;
  }
`

type ImovelInteressadoType = {
  id: number
  ref: string
  tipo_nome: string | null
  zona_nome: string | null
  valor_venda: number
  condominio_nome: string | null
  condominio_bairro: string | null
  proprietario_nome: string | null
}

type PermutaAutomovelType = {
  id: number
  proprietario: number
  proprietario_nome: string
  criado_por: number
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  tipo: number | null
  tipo_nome: string | null
  marca: string
  modelo: string
  motor: string
  valor: number
  imoveis_interessados: ImovelInteressadoType[]
}

const PermutaAutomovel = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useAxios()

  const [permuta, setPermuta] = useState<PermutaAutomovelType | null>(null)
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isInteresseModalOpen, setIsInteresseModalOpen] = useState(false)
  const [interesses, setInteresses] = useState<InteressePermutaAutomovelType[]>([])

  const fetchData = async () => {
    setLoading(true)
    try {
      const permutaRes = await api.get(`/permuta/automovel/${id}/`)
      setPermuta(permutaRes.data)
    } catch (error) {
      console.error('Error fetching permuta:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchInteresses = async () => {
    try {
      const res = await api.get(`/permuta/interesse-automovel/?permuta_automovel=${id}`)
      setInteresses(res.data.results || res.data)
    } catch (error) {
      console.error('Error fetching interesses:', error)
    }
  }

  useEffect(() => {
    if (id) {
      fetchData()
      fetchInteresses()
    }
  }, [id])

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const handleCloseInteresseModal = () => {
    setIsInteresseModalOpen(false)
  }

  const handleDeleteInteresse = async (interesseId: number) => {
    const result = await swal.fire({
      title: 'Confirmar exclusão',
      text: 'Tem certeza que deseja excluir este interesse?',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/permuta/interesse-automovel/${interesseId}/`)
        swal.fire('Excluído!', 'O interesse foi excluído com sucesso.', 'success')
        fetchInteresses()
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o interesse.', 'error')
      }
    }
  }

  const handleAddInteresse = async (data: InteressePermutaAutomovelData) => {
    try {
      await api.post('/permuta/interesse-automovel/', {
        permuta_automovel: id,
        tipo_imovel: data.tipo_imovel || null,
        zona: data.zona || null,
        estado: data.estado || null,
        valor_minimo: data.valor_minimo ? Number(data.valor_minimo) : null,
        valor_maximo: data.valor_maximo ? Number(data.valor_maximo) : null,
      })
      swal.fire('Sucesso!', 'Interesse adicionado com sucesso.', 'success')
      fetchInteresses()
    } catch (error) {
      swal.fire('Erro', 'Não foi possível adicionar o interesse.', 'error')
    }
  }

  const imoveisInteressados = permuta?.imoveis_interessados || []

  const handleEdit = () => {
    setIsModalOpen(true)
  }

  const handleDelete = async () => {
    const result = await swal.fire({
      title: 'Confirmar exclusão',
      text: 'Tem certeza que deseja excluir esta permuta? Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/permuta/automovel/${id}/`)
        swal.fire('Excluído!', 'A permuta foi excluída com sucesso.', 'success')
        navigate('/permutas')
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir a permuta.', 'error')
      }
    }
  }

  if (loading) {
    return (
      <Container>
        <LoadingScreen />
      </Container>
    )
  }

  if (!permuta) {
    return (
      <Container>
        <Banner>
          <p style={{ color: 'white' }}>Permuta não encontrada</p>
        </Banner>
      </Container>
    )
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value)
  }

  return (
    <Container>
      <Banner>
        <Icon>🚗</Icon>
        <Infos>
          <Tipo>{permuta.tipo_nome || '-'}</Tipo>
          <Titulo>{permuta.marca} {permuta.modelo}</Titulo>
          <InfoItem>
            <strong>Proprietário:</strong> {permuta.proprietario_nome}
          </InfoItem>
          <InfoItem>
            <strong>Motor:</strong> {permuta.motor || '-'}
          </InfoItem>
          <Valor>{formatCurrency(permuta.valor)}</Valor>
          <ActionButtons>
            <ActionButton onClick={handleEdit} title="Editar">
              <EditIcon size={18} />
            </ActionButton>
            <ActionButton $variant="delete" onClick={handleDelete} title="Excluir">
              <DeleteIcon size={18} />
            </ActionButton>
          </ActionButtons>
        </Infos>
      </Banner>

      {permuta && (
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title="Editar Permuta de Automóvel"
        >
          <PermutaAutomovelEditForm
            onSuccess={() => {
              fetchData()
              handleCloseModal()
            }}
            onClose={handleCloseModal}
            initialData={permuta}
          />
        </Modal>
      )}

      <Sections>
        <CardGrid>
          <div>
            <TituloSecao>Informações do Veículo</TituloSecao>
            <Card>
              <InfoItem>
                <strong>ID:</strong> {permuta.id}
              </InfoItem>
              <InfoItem>
                <strong>Tipo:</strong> {permuta.tipo_nome || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Marca:</strong> {permuta.marca || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Modelo:</strong> {permuta.modelo || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Motor:</strong> {permuta.motor || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Valor:</strong> {formatCurrency(permuta.valor)}
              </InfoItem>
            </Card>
          </div>

          <div>
            <TituloSecao>Informações do Proprietário</TituloSecao>
            <Card>
              <InfoItem>
                <strong>Nome:</strong> {permuta.proprietario_nome}
              </InfoItem>
              <InfoItem>
                <strong>Corretor:</strong> {permuta.corretor_nome || '-'}
              </InfoItem>
              <InfoItem>
                <strong>Criado por:</strong> {permuta.criado_por_nome || '-'}
              </InfoItem>
            </Card>
          </div>
        </CardGrid>

        <InteresseSection>
          <InteresseSectionHeader>
            <TituloSecao>Interesses em Imóveis (O que aceita em troca)</TituloSecao>
            <AddButton onClick={() => setIsInteresseModalOpen(true)}>
              + Adicionar Interesse
            </AddButton>
          </InteresseSectionHeader>

          {interesses.length > 0 ? (
            <InteresseTable>
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Zona</th>
                  <th>Valor Mínimo</th>
                  <th>Valor Máximo</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {interesses.map((interesse) => (
                  <tr key={interesse.id}>
                    <td>{interesse.tipo_imovel_nome || 'Todos'}</td>
                    <td>{interesse.zona_nome || 'Todas'}</td>
                    <td>{interesse.valor_minimo ? formatCurrency(interesse.valor_minimo) : '-'}</td>
                    <td>{interesse.valor_maximo ? formatCurrency(interesse.valor_maximo) : '-'}</td>
                    <td>
                      <InteresseActions>
                        <DeleteButton onClick={() => handleDeleteInteresse(interesse.id)}>
                          <DeleteIcon size={16} />
                        </DeleteButton>
                      </InteresseActions>
                    </td>
                  </tr>
                ))}
              </tbody>
            </InteresseTable>
          ) : (
            <EmptyMessage>
              Nenhum interesse cadastrado. Adicione interesses para que o sistema possa criar matches bilaterais.
            </EmptyMessage>
          )}
        </InteresseSection>

        <Modal
          isOpen={isInteresseModalOpen}
          onClose={handleCloseInteresseModal}
          title="Adicionar Interesse em Imóvel"
        >
          <InteressePermutaAutomovelForm
            onAdd={handleAddInteresse}
            onClose={handleCloseInteresseModal}
          />
        </Modal>

        <TituloSecao>Imóveis Interessados</TituloSecao>
        <MatchesContainer>
          <MatchSection>
            <MatchSectionTitle>
              Imóveis que buscam este automóvel ({imoveisInteressados.length})
            </MatchSectionTitle>
            {imoveisInteressados.length > 0 ? (
              imoveisInteressados.map((imovel) => (
                <MatchCard 
                  key={imovel.id}
                  onClick={() => navigate(`/imovel/${imovel.id}`)}
                >
                  <MatchBadge>Match</MatchBadge>
                  <MatchCardTitle>{imovel.ref}</MatchCardTitle>
                  <MatchCardDetail>{imovel.tipo_nome || '-'}{imovel.zona_nome ? ` - ${imovel.zona_nome}` : ''}</MatchCardDetail>
                  <MatchCardDetail>{imovel.condominio_nome || '-'}</MatchCardDetail>
                  <MatchCardDetail>{imovel.condominio_bairro || '-'}</MatchCardDetail>
                  <MatchCardDetail>
                    Proprietário: {imovel.proprietario_nome || '-'}
                  </MatchCardDetail>
                  <MatchCardValue>{formatCurrency(imovel.valor_venda)}</MatchCardValue>
                </MatchCard>
              ))
            ) : (
              <EmptyMessage>
                Nenhum imóvel interessado encontrado
              </EmptyMessage>
            )}
          </MatchSection>
        </MatchesContainer>
      </Sections>
    </Container>
  )
}

export default PermutaAutomovel
